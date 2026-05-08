"""
Unit tests for recorder.py.

Hardware is stubbed in conftest.py; these tests cover pure logic only.
"""

import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import recorder


# ---------------------------------------------------------------------------
# _load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_returns_all_defaults_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(recorder, "_CONFIG_PATH", str(tmp_path / "missing.json"))
        cfg = recorder._load_config()
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


# ---------------------------------------------------------------------------
# process_recording
# ---------------------------------------------------------------------------

class TestProcessRecording:
    def _frames(self, seconds: float) -> list[np.ndarray]:
        n = int(seconds * recorder.SAMPLE_RATE)
        return [np.zeros((n, 1), dtype="float32")]

    def test_skips_recording_shorter_than_minimum(self):
        frames = self._frames(0.1)
        with patch("recorder.notify") as mock_notify, \
             patch("recorder.normalize_audio") as mock_norm:
            recorder.process_recording("20240101_000000", frames)
        mock_norm.assert_not_called()
        msgs = [call.args[1] for call in mock_notify.call_args_list]
        assert any("short" in m.lower() for m in msgs)

    def test_happy_path_runs_full_pipeline(self, tmp_path):
        frames = self._frames(2.0)
        transcript_file = tmp_path / "20240101_000000.txt"
        transcript_file.write_text("raw whisper output")

        with patch.multiple(
            "recorder",
            RAW_AUDIO_DIR=str(tmp_path),
            NORM_AUDIO_DIR=str(tmp_path),
            RAW_TRANSCRIPT_DIR=str(tmp_path),
            CLEAN_TRANSCRIPT_DIR=str(tmp_path),
        ), \
        patch("recorder.normalize_audio") as mock_norm, \
        patch("recorder.transcribe", return_value=str(transcript_file)) as mock_tr, \
        patch("recorder.clean_with_ollama", return_value="clean output") as mock_clean, \
        patch("recorder.copy_to_clipboard") as mock_clip, \
        patch("recorder.notify"):
            recorder.process_recording("20240101_000000", frames)

        mock_norm.assert_called_once()
        mock_tr.assert_called_once()
        mock_clean.assert_called_once_with("raw whisper output")
        mock_clip.assert_called_once_with("clean output")

    def test_empty_transcript_skips_ollama_and_clipboard(self, tmp_path):
        frames = self._frames(2.0)
        transcript_file = tmp_path / "20240101_000000.txt"
        transcript_file.write_text("   ")  # whitespace only

        with patch.multiple(
            "recorder",
            RAW_AUDIO_DIR=str(tmp_path),
            NORM_AUDIO_DIR=str(tmp_path),
            RAW_TRANSCRIPT_DIR=str(tmp_path),
            CLEAN_TRANSCRIPT_DIR=str(tmp_path),
        ), \
        patch("recorder.normalize_audio"), \
        patch("recorder.transcribe", return_value=str(transcript_file)), \
        patch("recorder.clean_with_ollama") as mock_clean, \
        patch("recorder.copy_to_clipboard") as mock_clip, \
        patch("recorder.notify"):
            recorder.process_recording("20240101_000000", frames)

        mock_clean.assert_not_called()
        mock_clip.assert_not_called()

    def test_audio_files_removed_after_successful_transcription(self, tmp_path):
        frames = self._frames(2.0)
        raw_dir = tmp_path / "raw"
        norm_dir = tmp_path / "norm"
        transcript_dir = tmp_path / "transcripts"
        for d in (raw_dir, norm_dir, transcript_dir):
            d.mkdir()

        transcript_file = transcript_dir / "20240101_000000.txt"
        transcript_file.write_text("raw whisper output")

        with patch.multiple(
            "recorder",
            RAW_AUDIO_DIR=str(raw_dir),
            NORM_AUDIO_DIR=str(norm_dir),
            RAW_TRANSCRIPT_DIR=str(transcript_dir),
            CLEAN_TRANSCRIPT_DIR=str(transcript_dir),
        ), \
        patch("recorder.normalize_audio"), \
        patch("recorder.transcribe", return_value=str(transcript_file)), \
        patch("recorder.clean_with_ollama", return_value="clean output"), \
        patch("recorder.copy_to_clipboard"), \
        patch("recorder.notify"), \
        patch("recorder.os.remove") as mock_remove:
            recorder.process_recording("20240101_000000", frames)

        removed = [call.args[0] for call in mock_remove.call_args_list]
        assert os.path.join(str(raw_dir), "20240101_000000.wav") in removed
        assert os.path.join(str(norm_dir), "20240101_000000.wav") in removed
        assert len(removed) == 2

    def test_audio_files_not_removed_on_pipeline_error(self, tmp_path):
        frames = self._frames(2.0)
        with patch.multiple("recorder", RAW_AUDIO_DIR=str(tmp_path), NORM_AUDIO_DIR=str(tmp_path)), \
             patch("recorder.normalize_audio", side_effect=subprocess.CalledProcessError(
                 1, "ffmpeg", stderr=b"codec error"
             )), \
             patch("recorder.notify"), \
             patch("recorder.os.remove") as mock_remove:
            recorder.process_recording("20240101_000000", frames)

        mock_remove.assert_not_called()

    def test_subprocess_error_notifies_without_raising(self, tmp_path):
        frames = self._frames(2.0)
        with patch.multiple("recorder", RAW_AUDIO_DIR=str(tmp_path), NORM_AUDIO_DIR=str(tmp_path)), \
             patch("recorder.normalize_audio", side_effect=subprocess.CalledProcessError(
                 1, "ffmpeg", stderr=b"codec error"
             )), \
             patch("recorder.notify") as mock_notify:
            recorder.process_recording("20240101_000000", frames)  # must not raise

        error_calls = [c for c in mock_notify.call_args_list if "error" in c.args[1].lower()]
        assert len(error_calls) == 1
        assert "codec error" in error_calls[0].args[1]


# ---------------------------------------------------------------------------
# toggle_recording
# ---------------------------------------------------------------------------

class TestToggleRecording:
    def setup_method(self):
        recorder.is_recording = False
        recorder.audio_buffer = []

    def test_first_call_sets_recording_true_and_clears_buffer(self):
        recorder.audio_buffer = [np.zeros((100, 1))]  # stale data
        with patch("recorder.notify"):
            recorder.toggle_recording()
        assert recorder.is_recording is True
        assert recorder.audio_buffer == []

    def test_second_call_stops_recording_and_spawns_thread(self):
        recorder.is_recording = True
        recorder.audio_buffer = [np.zeros((100, 1), dtype="float32")]
        with patch("recorder.notify"), \
             patch("threading.Thread") as mock_thread:
            recorder.toggle_recording()
        assert recorder.is_recording is False
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_stop_passes_buffer_snapshot_to_thread(self):
        recorder.is_recording = True
        sentinel = np.zeros((50, 1), dtype="float32")
        recorder.audio_buffer = [sentinel]
        captured_frames = []

        def fake_thread(target, args, daemon):
            captured_frames.extend(args[1])
            return MagicMock()

        with patch("recorder.notify"), \
             patch("threading.Thread", side_effect=fake_thread):
            recorder.toggle_recording()

        assert len(captured_frames) == 1
        assert np.array_equal(captured_frames[0], sentinel)
