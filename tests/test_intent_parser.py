"""
Unit tests for shared intent parser.
Run: python -m pytest tests/test_intent_parser.py -v

Uses unittest.mock to avoid real LLM API calls.
"""

import json
import os
import sys
import pytest
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config.pmkisan import PMKISAN_CONFIG


@pytest.fixture
def parser():
    """Create an IntentParser with mocked LLM client."""
    with mock.patch("shared.agent.intent_parser.OpenAI"):
        from shared.agent.intent_parser import IntentParser
        p = IntentParser(PMKISAN_CONFIG, verbose=False)
    return p


def _make_llm_response(intent: str, params: dict = None, confidence: float = 0.95):
    """Create a mock OpenAI chat completion response."""
    content = json.dumps({
        "intent": intent,
        "params": params or {},
        "confidence": confidence,
    })
    mock_msg = mock.MagicMock()
    mock_msg.content = content
    mock_choice = mock.MagicMock()
    mock_choice.message = mock_msg
    mock_response = mock.MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


class TestIntentParser:
    def _parse_with_mock(self, parser, response_content: str) -> dict:
        parser.client.chat.completions.create.return_value = (
            _make_llm_response("placeholder")
        )
        mock_msg = mock.MagicMock()
        mock_msg.content = response_content
        mock_choice = mock.MagicMock()
        mock_choice.message = mock_msg
        mock_response = mock.MagicMock()
        mock_response.choices = [mock_choice]
        parser.client.chat.completions.create.return_value = mock_response
        return parser.parse("test prompt")

    def test_register_pmkisan(self, parser):
        result = self._parse_with_mock(
            parser,
            json.dumps({"intent": "register_pmkisan", "params": {}, "confidence": 0.97})
        )
        assert result["intent"] == "register_pmkisan"
        assert result["confidence"] >= 0.9

    def test_check_beneficiary_status_with_reg_no(self, parser):
        result = self._parse_with_mock(
            parser,
            json.dumps({
                "intent": "check_beneficiary_status",
                "params": {"registration_no": "1234567890"},
                "confidence": 0.98,
            })
        )
        assert result["intent"] == "check_beneficiary_status"
        assert result["params"].get("registration_no") == "1234567890"

    def test_check_farmer_status(self, parser):
        result = self._parse_with_mock(
            parser,
            json.dumps({
                "intent": "check_farmer_status",
                "params": {"aadhaar": "123456789012"},
                "confidence": 0.95,
            })
        )
        assert result["intent"] == "check_farmer_status"
        assert result["params"].get("aadhaar") == "123456789012"

    def test_know_registration_number(self, parser):
        result = self._parse_with_mock(
            parser,
            json.dumps({
                "intent": "know_registration_number",
                "params": {"mobile": "9876543210"},
                "confidence": 0.96,
            })
        )
        assert result["intent"] == "know_registration_number"
        assert result["params"].get("mobile") == "9876543210"

    def test_get_beneficiary_list(self, parser):
        result = self._parse_with_mock(
            parser,
            json.dumps({
                "intent": "get_beneficiary_list",
                "params": {
                    "state": "Maharashtra",
                    "district": "Pune",
                    "block": "Haveli",
                },
                "confidence": 0.95,
            })
        )
        assert result["intent"] == "get_beneficiary_list"
        assert result["params"]["state"] == "Maharashtra"
        assert result["params"]["district"] == "Pune"

    def test_access_kcc(self, parser):
        result = self._parse_with_mock(
            parser,
            json.dumps({"intent": "access_kcc", "params": {}, "confidence": 0.96})
        )
        assert result["intent"] == "access_kcc"

    def test_access_aif(self, parser):
        result = self._parse_with_mock(
            parser,
            json.dumps({"intent": "access_aif", "params": {}, "confidence": 0.93})
        )
        assert result["intent"] == "access_aif"

    def test_raise_helpdesk(self, parser):
        result = self._parse_with_mock(
            parser,
            json.dumps({"intent": "raise_helpdesk", "params": {}, "confidence": 0.94})
        )
        assert result["intent"] == "raise_helpdesk"

    def test_unknown_intent_defaults_to_get_info(self, parser):
        result = self._parse_with_mock(
            parser,
            json.dumps({"intent": "does_not_exist", "params": {}, "confidence": 0.9})
        )
        assert result["intent"] == "get_info"

    def test_low_confidence_still_returns(self, parser):
        result = self._parse_with_mock(
            parser,
            json.dumps({"intent": "navigate_page", "params": {}, "confidence": 0.35})
        )
        assert result["intent"] == "navigate_page"
        assert result["confidence"] == 0.35

    def test_invalid_json_raises_error(self, parser):
        """Invalid JSON should cause an error now (no keyword fallback)."""
        with mock.patch.object(parser.client.chat.completions, "create") as mock_create:
            mock_msg = mock.MagicMock()
            mock_msg.content = "NOT JSON AT ALL !!!"
            mock_choice = mock.MagicMock()
            mock_choice.message = mock_msg
            mock_response = mock.MagicMock()
            mock_response.choices = [mock_choice]
            mock_create.return_value = mock_response
            
            with pytest.raises(SystemExit):
                parser.parse("some query")
