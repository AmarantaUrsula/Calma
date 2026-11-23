// Small fetch wrapper. Staff session token lives in sessionStorage (cleared when the tab closes).

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
  }
}

export function getToken(): string | null {
  return sessionStorage.getItem("calma_token");
}

export function setSession(token: string | null, user?: unknown) {
  if (token) {
    sessionStorage.setItem("calma_token", token);
    sessionStorage.setItem("calma_user", JSON.stringify(user));
  } else {
    sessionStorage.removeItem("calma_token");
    sessionStorage.removeItem("calma_user");
  }
}

export function getUser<T>(): T | null {
  const u = sessionStorage.getItem("calma_user");
  return u ? (JSON.parse(u) as T) : null;
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const tok = getToken();
  if (tok) headers.Authorization = `Bearer ${tok}`;
  const res = await fetch(path, {
    method: opts.method ?? (opts.body ? "POST" : "GET"),
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && tok) {
      setSession(null);
      navigate("/login");
    }
    throw new ApiError(res.status, data?.detail ?? data);
  }
  return data as T;
}

export function navigate(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export const money = (n: number | null | undefined) =>
  n == null ? "—" : `$${n.toLocaleString("en-US")}`;

export function errText(e: unknown): string {
  if (e instanceof ApiError) {
    if (typeof e.detail === "string") return e.detail;
    if (Array.isArray(e.detail)) return "Please check the form and try again.";
  }
  return e instanceof Error ? e.message : "Something went wrong.";
}
