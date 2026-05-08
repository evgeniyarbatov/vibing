"""
Unit tests for recorder.py.

Hardware is stubbed in conftest.py; these tests cover pure logic only.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

import recorder


# ---------------------------------------------------------------------------
# _load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_returns_all_defaults_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(recorder, "_CONFIG_PATH", str(tmp_path / "missing.json"))
        cfg = recorder._load_config()
        assert cfg["whisper_model"] == "small"
        assert cfg["ollama_model"] == "mistral-nemo"
        assert "{transcription}" in cfg["ollama_prompt"]
        assert cfg["output_dir"] == "~/Documents/vibing"
        assert cfg["hotkey"] == "alt_r"

    def test_user_values_override_defaults(self, tmp_path, monkeypatch):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({
            "ollama_model": "llama3",
            "output_dir": "/tmp/audio",
            "hotkey": "f13",
        }))
        monkeypatch.setattr(recorder, "_CONFIG_PATH", str(p))
        cfg = recorder._load_config()
        assert cfg["ollama_model"] == "llama3"
        assert cfg["output_dir"] == "/tmp/audio"
        assert cfg["hotkey"] == "f13"

    def test_partial_override_preserves_other_defaults(self, tmp_path, monkeypatch):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"ollama_model": "gemma"}))
        monkeypatch.setattr(recorder, "_CONFIG_PATH", str(p))
        cfg = recorder._load_config()
        assert cfg["ollama_model"] == "gemma"
        assert cfg["output_dir"] == "~/Documents/vibing"   # default intact
        assert cfg["hotkey"] == "alt_r"                    # default intact

    def test_unknown_keys_are_passed_through(self, tmp_path, monkeypatch):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"future_option": True}))
        monkeypatch.setattr(recorder, "_CONFIG_PATH", str(p))
        cfg = recorder._load_config()
        assert cfg["future_option"] is True


# ---------------------------------------------------------------------------
# _resolve_output_dir
# ---------------------------------------------------------------------------

class TestResolveOutputDir:
    def test_tilde_expands_to_home(self):
        result = recorder._resolve_output_dir("~/Documents/vibing")
        assert result == os.path.expanduser("~/Documents/vibing")
        assert not result.startswith("~")

    def test_absolute_path_returned_unchanged(self):
        result = recorder._resolve_output_dir("/absolute/custom/path")
        assert result == "/absolute/custom/path"

    def test_relative_path_joined_with_project_dir(self):
        result = recorder._resolve_output_dir("data")
        assert result == os.path.join(recorder.PROJECT_DIR, "data")

    def test_relative_subdirectory(self):
        result = recorder._resolve_output_dir("outputs/audio")
        assert result == os.path.join(recorder.PROJECT_DIR, "outputs/audio")


# ---------------------------------------------------------------------------
# _parse_hotkey
# ---------------------------------------------------------------------------

class TestParseHotkey:
    def test_valid_key_name_returns_enum_member(self):
        result = recorder._parse_hotkey("alt_r")
        # conftest _MockKey is wired as keyboard.Key
        assert result.value == "alt_r"

    def test_unknown_key_name_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown hotkey 'not_a_key'"):
            recorder._parse_hotkey("not_a_key")

    def test_error_message_contains_examples(self):
        with pytest.raises(ValueError, match="alt_r"):
            recorder._parse_hotkey("bogus")


# ---------------------------------------------------------------------------
# clean_with_ollama
# ---------------------------------------------------------------------------

class TestCleanWithOllama:
    def _fake_resp(self, text: str) -> MagicMock:
        m = MagicMock()
        m.json.return_value = {"response": text}
        return m

    def test_uses_model_from_cfg(self):
        with patch("recorder.requests.post", return_value=self._fake_resp("ok")) as mock_post, \
             patch.dict(recorder.cfg, {"ollama_model": "llama3", "ollama_prompt": "{transcription}"}):
            recorder.clean_with_ollama("hello")
        assert mock_post.call_args.kwargs["json"]["model"] == "llama3"

    def test_substitutes_transcription_in_prompt(self):
        with patch("recorder.requests.post", return_value=self._fake_resp("ok")) as mock_post, \
             patch.dict(recorder.cfg, {"ollama_model": "m", "ollama_prompt": "Fix: {transcription}"}):
            recorder.clean_with_ollama("raw text here")
        prompt = mock_post.call_args.kwargs["json"]["prompt"]
        assert "raw text here" in prompt
        assert "{transcription}" not in prompt

    def test_strips_whitespace_from_response(self):
        with patch("recorder.requests.post", return_value=self._fake_resp("  clean text  \n")), \
             patch.dict(recorder.cfg, {"ollama_model": "m", "ollama_prompt": "{transcription}"}):
            result = recorder.clean_with_ollama("x")
        assert result == "clean text"

    def test_propagates_http_errors(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")
        with patch("recorder.requests.post", return_value=mock_resp), \
             patch.dict(recorder.cfg, {"ollama_model": "m", "ollama_prompt": "{transcription}"}):
            with pytest.raises(Exception, match="HTTP 500"):
                recorder.clean_with_ollama("x")

