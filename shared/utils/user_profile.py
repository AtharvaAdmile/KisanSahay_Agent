"""
UserProfile — secure local storage of farmer details for pre-filling forms.

Stores non-sensitive structured data as JSON at a config-specified path.
Sensitive fields (Aadhaar-like) are masked in summaries. Users must
explicitly opt in by running --setup-profile.

Usage:
    profile = UserProfile(config)
    state = profile.get("address.state")     # dot-notation get
    profile.set("personal.mobile", "9876543210")
    params = profile.to_params()             # flatten for task pre-fill
"""

import json
from pathlib import Path
from typing import Optional, Any, Set

from . import logger


def _try_keyring():
    """Return the keyring module if available, else None."""
    try:
        import keyring  # noqa: F401
        return keyring
    except ImportError:
        return None


class UserProfile:
    """
    Local farmer profile for pre-filling forms with minimal user prompts.

    Profile sections:
        personal  — full_name, mobile, aadhaar, age, gender, caste,
                    relationship, relative_name, passbook_name
        address   — state, district, sub_district, block, village, pincode
        bank      — state, district, name, branch, account_no, ifsc
        crop      — (PMFBY only) season, crop_name, area_ha, year
        portals   — (PMFBY only) lms_mobile, cropic_mobile, passwords via keyring
    """

    def __init__(
        self,
        profile_path: Path,
        sensitive_keys: Set[str],
        keyring_service: str,
    ):
        self._profile_path = profile_path
        self._sensitive_keys = sensitive_keys
        self._keyring_service = keyring_service
        self._data: dict = self._load()

    def _load(self) -> dict:
        """Load profile from disk, return empty dict if missing."""
        if self._profile_path.exists():
            try:
                return json.loads(self._profile_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"UserProfile: could not load profile — {e}")
        return {}

    def save(self) -> None:
        """Write profile to disk (creates directory if needed)."""
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)
        self._profile_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.debug(f"Profile saved to {self._profile_path}", verbose=False)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Dot-notation read.  e.g. profile.get('address.state')
        Returns `default` if the key path does not exist.
        """
        if key in self._sensitive_keys:
            kr = _try_keyring()
            if kr:
                val = kr.get_password(self._keyring_service, key)
                if val is not None:
                    return val

        parts = key.split(".")
        node = self._data
        for part in parts:
            if not isinstance(node, dict):
                return default
            node = node.get(part, {})
        return node if node != {} else default

    def set(self, key: str, value: Any) -> None:
        """
        Dot-notation write.  e.g. profile.set('personal.mobile', '9876543210')
        Sensitive keys are stored in keyring (if available) and excluded from JSON.
        """
        if key in self._sensitive_keys:
            kr = _try_keyring()
            if kr:
                kr.set_password(self._keyring_service, key, str(value))
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
                    if v:
                        flat[k] = v
                        flat[f"{section}_{k}"] = v
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


def run_setup_wizard(
    profile_path: Path,
    sensitive_keys: Set[str],
    keyring_service: str,
    site_name: str,
    include_crop_fields: bool = False,
    include_portal_credentials: bool = False,
) -> UserProfile:
    """
    Interactive CLI wizard that walks the user through filling out their
    farmer profile. Called by entry point --setup-profile.
    """
    profile = UserProfile(profile_path, sensitive_keys, keyring_service)
    print(f"\n═══ {site_name} Agent — Profile Setup ═══")
    print("Your details will be saved locally and used to auto-fill forms.")
    print("Press Enter to skip any field.\n")

    def _ask(label: str, key: str, mask: bool = False) -> None:
        current = profile.get(key)
        hint = f" [{'****' + str(current)[-4:] if mask and current else (current or 'not set')}]"
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
    _ask("Passbook Name (as in bank records)", "personal.passbook_name")

    print("\n── Address ──")
    _ask("State", "address.state")
    _ask("District", "address.district")
    _ask("Sub-District / Tehsil", "address.sub_district")
    _ask("Block", "address.block")
    _ask("Village / Town", "address.village")
    _ask("PIN Code", "address.pincode")

    if include_crop_fields:
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

    if include_portal_credentials:
        print("\n── Portal Credentials (LMS / CROPIC) ──")
        print("  (Passwords stored securely via system keyring if available)")
        _ask("LMS Mobile", "portals.lms_mobile")
        _ask("LMS Password", "portals.lms_password", mask=True)
        _ask("CROPIC Mobile", "portals.cropic_mobile")
        _ask("CROPIC Password", "portals.cropic_password", mask=True)
        _ask("WINDS Mobile", "portals.winds_mobile")
        _ask("WINDS Password", "portals.winds_password", mask=True)

    print(f"\n✅ Profile saved to: {profile_path}")
    print(profile.summary())
    return profile
