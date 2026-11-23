"""Scheduled website check for fund eligibility pages.

Every ~60 days (CALMA_CHECK_INTERVAL_DAYS) each fund's eligibility page is fetched:
  * page text the same as last time   -> 'unchanged' (no AI call, no cost)
  * page changed                      -> the Rules Extractor reads it
      - suggested rules same as now   -> 'rules_same' (nothing for a person to do)
      - something changed / unclear   -> 'proposal_created' (shows up in Admin for review)
  * fund already has a suggestion waiting for review -> 'skipped_pending_review'
  * fetch problems                    -> 'error' (with a plain-English note)

Nothing here changes live rules. A person always approves.

Being a good citizen: identifies itself honestly, respects robots.txt, checks rarely,
and refuses to fetch private/internal addresses.

    python -m backend.website_check            # check funds that are due
    python -m backend.website_check --all      # check every fund now
    python -m backend.website_check --fund 3   # check one fund now
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import socket
import sqlite3
from dataclasses import dataclass
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from . import clock
from .db import audit
from .proposals import create_proposal

USER_AGENT = "CalmaRulesBot/0.1 (checks public abortion fund eligibility pages about every 2 months)"
MAX_BYTES = 2_000_000
MIN_TEXT_CHARS = 200
SNAPSHOT_CHARS = 20_000
DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "demo_pages"


def interval_days() -> int:
    return int(os.environ.get("CALMA_CHECK_INTERVAL_DAYS", "60"))


class CheckError(Exception):
    """A problem worth showing to the admin as-is."""


# ---------- HTML -> readable text ----------

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
    BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "ul", "ol", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in "".join(p.parts).split("\n")]
    return "\n".join(ln for ln in lines if ln)


def content_hash(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().lower().encode()).hexdigest()


# ---------- safe fetching ----------

def _check_public_host(host: str) -> None:
    if os.environ.get("CALMA_ALLOW_PRIVATE_FETCH") == "1":
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise CheckError(f"Couldn't find the website {host}.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise CheckError("That link points to a private or internal address, so Calma won't fetch it.")


def validate_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme == "demo":
        if not re.fullmatch(r"[a-z0-9-]+", u.netloc):
            raise CheckError("Demo links look like demo://fund-name.")
        return
    if u.scheme not in ("http", "https") or not u.hostname:
        raise CheckError("Use a full web link starting with https://")


async def _robots_allows(client: httpx.AsyncClient, url: str) -> bool:
    u = urlparse(url)
    robots_url = f"{u.scheme}://{u.netloc}/robots.txt"
    try:
        r = await client.get(robots_url)
    except httpx.HTTPError:
        return True  # no robots.txt reachable: allowed
    if r.status_code >= 400:
        return True
    rp = RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(USER_AGENT, url)


async def fetch_text(url: str) -> str:
    validate_url(url)
    u = urlparse(url)
    if u.scheme == "demo":
        path = DEMO_DIR / f"{u.netloc}.html"
        if not path.exists():
            raise CheckError(f"No demo page named {u.netloc}.")
        return html_to_text(path.read_text(encoding="utf-8"))

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=False) as client:
        _check_public_host(u.hostname)
        if not await _robots_allows(client, url):
            raise CheckError("The fund's robots.txt asks bots not to read this page. Ask the fund for its rules instead.")
        current = url
        for _ in range(4):  # follow up to 3 redirects, re-checking each address
            async with client.stream("GET", current) as r:
                if r.is_redirect:
                    nxt = urljoin(current, r.headers.get("location", ""))
                    validate_url(nxt)
                    _check_public_host(urlparse(nxt).hostname)
                    current = nxt
                    continue
                if r.status_code >= 400:
                    raise CheckError(f"The website answered with an error ({r.status_code}).")
                ctype = r.headers.get("content-type", "")
                if "html" not in ctype and "text" not in ctype:
                    raise CheckError(f"The link isn't a web page ({ctype or 'unknown type'}). PDFs aren't supported yet.")
                body = b""
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise CheckError("The page is too large.")
                text = body.decode(r.encoding or "utf-8", errors="replace")
                return html_to_text(text) if "html" in ctype else text.strip()
        raise CheckError("Too many redirects.")


# ---------- the check ----------

@dataclass
class CheckResult:
    fund_id: int
    fund_name: str
    status: str
    note: str
    criteria_id: int | None = None


def _last_baseline(db: sqlite3.Connection, fund_id: int, url: str) -> str | None:
    r = db.execute(
        """SELECT content_hash FROM page_checks WHERE fund_id = ? AND url = ? AND content_hash IS NOT NULL
           ORDER BY id DESC LIMIT 1""",
        (fund_id, url),
    ).fetchone()
    return r[0] if r else None


def _record(db, fund_id, url, trigger, status, note, text=None, baseline=None, criteria_id=None) -> None:
    db.execute(
        """INSERT INTO page_checks (fund_id, url, checked_at, trigger, status, content_hash, page_text, note, criteria_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fund_id, url, clock.now_iso(), trigger, status, baseline,
         text[:SNAPSHOT_CHARS] if text else None, note, criteria_id),
    )


async def check_fund(db: sqlite3.Connection, fund_id: int, model: Any, trigger: str = "schedule") -> CheckResult:
    fund = db.execute("SELECT id, name, policy_url FROM funds WHERE id = ?", (fund_id,)).fetchone()
    if not fund or not fund["policy_url"]:
        raise CheckError("This fund has no website link to check.")
    url, name = fund["policy_url"], fund["name"]

    def done(status, note, **kw) -> CheckResult:
        _record(db, fund_id, url, trigger, status, note, **kw)
        audit(db, trigger if trigger.startswith("user:") else "system", f"website_check_{status}",
              detail={"fund_id": fund_id})
        return CheckResult(fund_id, name, status, note, kw.get("criteria_id"))

    try:
        text = await fetch_text(url)
    except CheckError as e:
        return done("error", str(e))
    except httpx.HTTPError as e:
        return done("error", f"Couldn't reach the website ({type(e).__name__}).")

    h = content_hash(text)
    previous = _last_baseline(db, fund_id, url)
    what = "Page changed" if previous else "First check of this page"
    if h == previous:
        return done("unchanged", "Page is the same as last time.", baseline=h)
    if len(text) < MIN_TEXT_CHARS:
        return done("error", "The page had almost no text. It may need a real browser to load, or the rules may be in a PDF.", text=text)
    pending = db.execute("SELECT 1 FROM fund_criteria WHERE fund_id = ? AND status = 'proposed'", (fund_id,)).fetchone()
    if pending:
        return done("skipped_pending_review", f"{what}, but a suggestion is already waiting for review. Will check again next time.", text=text)

    try:
        criteria_id = await create_proposal(db, fund_id, text, url, trigger, model)
    except Exception as e:
        from .llm import explain_ai_error
        return done("error", f"{what}, but the AI helper failed: {explain_ai_error(e)} Will retry next time.", text=text)

    ev = json.loads(db.execute("SELECT evidence FROM fund_criteria WHERE id = ?", (criteria_id,)).fetchone()[0])
    needs_review = [k for k, v in ev.items() if not k.startswith("_") and v.get("status") in ("changed", "needs_manual")]
    if not needs_review:
        db.execute("DELETE FROM fund_criteria WHERE id = ?", (criteria_id,))
        return done("rules_same", f"{what}: the rules on it match what Calma already has.", text=text, baseline=h)
    return done("proposal_created", f"Rules may have changed ({', '.join(needs_review)}). Review in Admin.",
                text=text, baseline=h, criteria_id=criteria_id)


def due_fund_ids(db: sqlite3.Connection) -> list[int]:
    cutoff = (clock.now() - timedelta(days=interval_days())).isoformat(timespec="seconds")
    rows = db.execute(
        """SELECT f.id FROM funds f
           WHERE f.policy_url IS NOT NULL AND f.policy_url != ''
             AND COALESCE((SELECT MAX(checked_at) FROM page_checks pc WHERE pc.fund_id = f.id), '') < ?
           ORDER BY f.id""",
        (cutoff,),
    ).fetchall()
    return [r[0] for r in rows]


async def run(db: sqlite3.Connection, model: Any, fund_ids: list[int] | None = None, trigger: str = "schedule") -> list[CheckResult]:
    ids = fund_ids if fund_ids is not None else due_fund_ids(db)
    results = []
    for fid in ids:
        results.append(await check_fund(db, fid, model, trigger))
        db.commit()
    return results


def main() -> None:
    from . import llm
    from .db import connect, init_schema

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="check every fund with a link, even if not due")
    ap.add_argument("--fund", type=int, help="check one fund now")
    args = ap.parse_args()
    conn = connect()
    init_schema(conn)
    try:
        if args.fund:
            ids = [args.fund]
        elif args.all:
            ids = [r[0] for r in conn.execute("SELECT id FROM funds WHERE policy_url IS NOT NULL AND policy_url != ''")]
        else:
            ids = None
        results = asyncio.run(run(conn, llm.get_model(), ids))
        conn.commit()
    finally:
        conn.close()
    if not results:
        print("No funds due for a check.")
    for r in results:
        print(f"{r.fund_name}: {r.status} — {r.note}")


if __name__ == "__main__":
    main()
