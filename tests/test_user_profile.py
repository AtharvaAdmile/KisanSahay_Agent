"""
Unit tests for shared/utils/user_profile.py
Run: python -m pytest tests/test_user_profile.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config.pmfby import PMFBY_CONFIG


@pytest.fixture
def tmp_profile(tmp_path):
    """Provide a UserProfile instance backed by a temporary directory."""
    from shared.utils.user_profile import UserProfile
    profile_path = tmp_path / "profile.json"
    profile = UserProfile(
        profile_path=profile_path,
        sensitive_keys=PMFBY_CONFIG.sensitive_keys,
        keyring_service=PMFBY_CONFIG.keyring_service,
    )
    yield profile, tmp_path


class TestUserProfileGetSet:
    def test_get_missing_returns_default(self, tmp_profile):
        profile, _ = tmp_profile
        assert profile.get("personal.mobile") is None
        assert profile.get("personal.mobile", "fallback") == "fallback"

    def test_set_and_get_flat(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("personal.mobile", "9876543210")
        assert profile.get("personal.mobile") == "9876543210"

    def test_set_and_get_nested(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("address.state", "Rajasthan")
        profile.set("address.district", "Jaipur")
        assert profile.get("address.state") == "Rajasthan"
        assert profile.get("address.district") == "Jaipur"

    def test_set_overwrites_existing(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("crop.season", "Kharif")
        profile.set("crop.season", "Rabi")
        assert profile.get("crop.season") == "Rabi"

    def test_has_returns_false_for_missing(self, tmp_profile):
        profile, _ = tmp_profile
        assert not profile.has("personal.mobile")

    def test_has_returns_true_for_set(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("personal.mobile", "9876543210")
        assert profile.has("personal.mobile")

    def test_has_returns_false_for_empty_string(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("personal.mobile", "")
        assert not profile.has("personal.mobile")


class TestUserProfilePersistence:
    def test_data_survives_reload(self, tmp_path):
        """Writing to profile and creating a new instance reads the same data."""
        from shared.utils.user_profile import UserProfile
        profile_path = tmp_path / "profile.json"

        p1 = UserProfile(
            profile_path=profile_path,
            sensitive_keys=PMFBY_CONFIG.sensitive_keys,
            keyring_service=PMFBY_CONFIG.keyring_service,
        )
        p1.set("personal.full_name", "Ram Kumar")
        p1.set("address.state", "Haryana")

        p2 = UserProfile(
            profile_path=profile_path,
            sensitive_keys=PMFBY_CONFIG.sensitive_keys,
            keyring_service=PMFBY_CONFIG.keyring_service,
        )
        assert p2.get("personal.full_name") == "Ram Kumar"
        assert p2.get("address.state") == "Haryana"

    def test_json_file_is_valid(self, tmp_profile):
        profile, tmp_path = tmp_profile
        profile.set("personal.mobile", "1234567890")
        profile_file = tmp_path / "profile.json"
        data = json.loads(profile_file.read_text(encoding="utf-8"))
        assert data["personal"]["mobile"] == "1234567890"


class TestUserProfileToParams:
    def test_to_params_empty(self, tmp_profile):
        profile, _ = tmp_profile
        assert profile.to_params() == {}

    def test_to_params_has_leaf_keys(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("personal.mobile", "9876543210")
        profile.set("crop.season", "Kharif")
        params = profile.to_params()
        assert params.get("mobile") == "9876543210"
        assert params.get("season") == "Kharif"

    def test_to_params_has_namespaced_keys(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("personal.mobile", "9876543210")
        params = profile.to_params()
        assert "personal_mobile" in params

    def test_to_params_skips_empty_values(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("personal.mobile", "")
        params = profile.to_params()
        assert "mobile" not in params

    def test_to_params_full_profile(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("personal.full_name", "Sita Devi")
        profile.set("personal.mobile", "9876543210")
        profile.set("address.state", "Madhya Pradesh")
        profile.set("crop.season", "Rabi")
        profile.set("crop.crop_name", "Wheat")
        profile.set("bank.account_no", "12345678")

        params = profile.to_params()
        assert params["full_name"] == "Sita Devi"
        assert params["mobile"] == "9876543210"
        assert params["state"] == "Madhya Pradesh"
        assert params["season"] == "Rabi"
        assert params["crop_name"] == "Wheat"


class TestUserProfileIsEmpty:
    def test_is_empty_on_new_profile(self, tmp_profile):
        profile, _ = tmp_profile
        assert profile.is_empty()

    def test_not_empty_after_set(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("personal.mobile", "9876543210")
        assert not profile.is_empty()


class TestUserProfileSummary:
    def test_summary_contains_field_names(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("personal.mobile", "9876543210")
        profile.set("address.state", "Punjab")
        summary = profile.summary()
        assert "mobile" in summary
        assert "state" in summary
        assert "Punjab" in summary

    def test_summary_masks_aadhaar(self, tmp_profile):
        profile, _ = tmp_profile
        profile.set("personal.aadhaar", "123456789012")
        summary = profile.summary()
        assert "123456789012" not in summary
        assert "****" in summary
