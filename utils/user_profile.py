"""
UserProfile — secure local storage of farmer details for pre-filling forms.

Stores non-sensitive structured data as JSON at:
    ~/.pmfby_agent/profile.json

Sensitive fields (LMS/CROPIC passwords) are stored via the system keyring
if the 'keyring' package is available; otherwise they are stored in the JSON
(with a warning). Users must explicitly opt in when running --setup-profile.

Usage:
    profile = UserProfile()
    state = profile.get("address.state")     # dot-notation get
    profile.set("personal.mobile", "9876543210")
    params = profile.to_params()             # flatten for task pre-fill
"""

import json
import os
from pathlib import Path

from utils import logger

PROFILE_PATH = Path.home() / ".pmfby_agent" / "profile.json"

# Sensitive keys stored via keyring (if available)
_KEYRING_SERVICE = "pmfby_agent"
_SENSITIVE_KEYS = {
    "portals.lms_password",
    "portals.cropic_password",
    "portals.winds_password",
}


def _try_keyring():
    """Return the keyring module if available, else None."""
    try:
        import keyring  # noqa: F401
        return keyring
    except ImportError:
        return None


class UserProfile:
    """
    Local farmer profile for pre-filling PMFBY forms with minimal user prompts.

    Profile sections:
        personal  — name, mobile, aadhaar, age, gender, caste, relationship
        address   — state, district, sub_district, village, address, pincode
        crop      — season, crop_name, area_ha, year
        bank      — state, district, name, branch, account_no, ifsc
        portals   — lms_mobile, cropic_mobile (passwords via keyring)
    """

    def __init__(self):
        self._data: dict = self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load profile from disk, return empty dict if missing."""
        if PROFILE_PATH.exists():
            try:
                return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"UserProfile: could not load profile — {e}")
        return {}

    def save(self) -> None:
        """Write profile to disk (creates directory if needed)."""
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_PATH.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.debug(f"Profile saved to {PROFILE_PATH}", verbose=False)

    # ── Dot-notation access ──────────────────────────────────────────────────

    def get(self, key: str, default=None):
        """
        Dot-notation read.  e.g. profile.get('address.state')
        Returns `default` if the key path does not exist.
        """
        # Sensitive values may live in keyring
        if key in _SENSITIVE_KEYS:
            kr = _try_keyring()
            if kr:
                val = kr.get_password(_KEYRING_SERVICE, key)
                if val is not None:
                    return val

        parts = key.split(".")
        node = self._data
        for part in parts:
            if not isinstance(node, dict):
                return default
            node = node.get(part, {})
        return node if node != {} else default

    def set(self, key: str, value) -> None:
        """
        Dot-notation write.  e.g. profile.set('personal.mobile', '9876543210')
        Sensitive keys are stored in keyring (if available) and excluded from JSON.
        """
        if key in _SENSITIVE_KEYS:
            kr = _try_keyring()
            if kr:
                kr.set_password(_KEYRING_SERVICE, key, str(value))
                logger.debug(f"Stored {key} in system keyring", verbose=False)
                return
            else:
                logger.warning(
                    f"keyring not installed — storing '{key}' in plain JSON. "
                    "Run: pip install keyring"
                )

        parts = key.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        self.save()

    def has(self, key: str) -> bool:
        """Return True if `key` is set and non-empty."""
        val = self.get(key)
        return bool(val)

    # ── Flat params dict ─────────────────────────────────────────────────────

    def to_params(self) -> dict:
        """
        Flatten all profile sections into a single dict so task handlers
        can pick up values by name.

        The flat key is the leaf key name (e.g., 'state', 'mobile').
        Namespaced duplicates (e.g., address.state vs bank.state) are
        also available as 'address_state' and 'bank_state'.
        """
        flat: dict = {}
        for section, vals in self._data.items():
            if isinstance(vals, dict):
                for k, v in vals.items():
                    if v:  # skip empty values
                        flat[k] = v
                        flat[f"{section}_{k}"] = v  # namespaced alias
            else:
                if vals:
                    flat[section] = vals
        return flat

    def summary(self) -> str:
        """Return a human-readable summary of stored fields."""
        lines = ["Stored profile fields:"]
        for section, vals in self._data.items():
            if isinstance(vals, dict):
                for k, v in vals.items():
                    # Mask sensitive-looking values
                    if any(s in k for s in ("aadhaar", "account", "password")):
                        display = "****" + str(v)[-4:] if v else "(not set)"
                    else:
                        display = str(v) if v else "(not set)"
                    lines.append(f"  {section}.{k}: {display}")
            else:
                lines.append(f"  {section}: {vals}")
        return "\n".join(lines)

    def is_empty(self) -> bool:
        return not bool(self._data)


# ── Interactive setup helper ─────────────────────────────────────────────────

def run_setup_wizard() -> UserProfile:
    """
    Interactive CLI wizard that walks the user through filling out their
    farmer profile.  Called by pmfby_agent.py --setup-profile.
    """
    profile = UserProfile()
    print("\n═══ PMFBY Agent — Profile Setup ═══")
    print("Your details will be saved locally and used to auto-fill forms.")
    print("Press Enter to skip any field.\n")

    def _ask(label: str, key: str, mask: bool = False) -> None:
        current = profile.get(key)
        hint = f" [{('****' + str(current)[-4:]) if mask and current else (current or 'not set')}]"
        val = input(f"  {label}{hint}: ").strip()
        if val:
            profile.set(key, val)

    print("── Personal Details ──")
    _ask("Full Name", "personal.full_name")
    _ask("Mobile Number (10 digits)", "personal.mobile")
    _ask("Aadhaar Number (12 digits)", "personal.aadhaar", mask=True)
    _ask("Age", "personal.age")
    _ask("Gender (Male/Female/Other)", "personal.gender")
    _ask("Caste (GENERAL/OBC/SC/ST)", "personal.caste")
    _ask("Relationship (S/O / D/O / W/O / C/O)", "personal.relationship")
    _ask("Relative Name (Father/Husband)", "personal.relative_name")
    _ask("Passbook Name (as in bank passbook)", "personal.passbook_name")

    print("\n── Address ──")
    _ask("State", "address.state")
    _ask("District", "address.district")
    _ask("Sub-District / Tehsil", "address.sub_district")
    _ask("Village / Town", "address.village")
    _ask("Full Address", "address.address")
    _ask("PIN Code", "address.pincode")

    print("\n── Crop Details ──")
    _ask("Default Season (Kharif/Rabi/Zaid)", "crop.season")
    _ask("Crop Name", "crop.crop_name")
    _ask("Area (hectares)", "crop.area_ha")
    _ask("Year (e.g. 2025)", "crop.year")

    print("\n── Bank Details ──")
    _ask("Bank State", "bank.state")
    _ask("Bank District", "bank.district")
    _ask("Bank Name", "bank.name")
    _ask("Bank Branch", "bank.branch")
    _ask("Account Number", "bank.account_no", mask=True)
    _ask("IFSC Code", "bank.ifsc")

    print("\n── Portal Credentials (LMS / CROPIC) ──")
    print("  (Passwords stored securely via system keyring if available)")
    _ask("LMS Mobile", "portals.lms_mobile")
    _ask("LMS Password", "portals.lms_password", mask=True)
    _ask("CROPIC Mobile", "portals.cropic_mobile")
    _ask("CROPIC Password", "portals.cropic_password", mask=True)
    _ask("WINDS Mobile", "portals.winds_mobile")
    _ask("WINDS Password", "portals.winds_password", mask=True)

    print(f"\n✅ Profile saved to: {PROFILE_PATH}")
    print(profile.summary())
    return profile
