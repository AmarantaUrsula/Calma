"""Which states' Medicaid programs pay for abortion care.

Source: Guttmacher Institute, "State Funding of Abortion Under Medicaid"
https://www.guttmacher.org/state-policy/explore/state-insurance-coverage-abortion-under-medicaid
(as of July 16, 2026). Column: "Uses state Medicaid funds to cover all or most abortions legal under
state law". Review this list when Guttmacher updates the page.

Used by clinic funds that don't pay for patients whose Medicaid should cover the abortion.
"""

AS_OF = "2026-07-16"
SOURCE = "https://www.guttmacher.org/state-policy/explore/state-insurance-coverage-abortion-under-medicaid"

# Cover all abortions for Medicaid enrollees.
COVERS_ALL = {"CA", "CO", "DE", "HI", "ME", "MN", "OR", "PA", "RI", "WA"}
# Cover all or most abortions but require a designation of medical necessity.
COVERS_WITH_MEDICAL_NECESSITY = {"AK", "CT", "IL", "MD", "MA", "MT", "NV", "NJ", "NM", "NY", "VT"}

COVERS_ABORTION = COVERS_ALL | COVERS_WITH_MEDICAL_NECESSITY  # 21 states


def covers(state: str | None) -> bool:
    return bool(state) and state in COVERS_ABORTION
