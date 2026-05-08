"""
Unit tests for recorder.py.

Hardware is stubbed in conftest.py; these tests cover pure logic only.
"""

import json
import os
import subprocess
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
import requests

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
# _ollama_post
# ---------------------------------------------------------------------------

class TestOllamaPost:
    def _fake_resp(self, data: dict) -> MagicMock:
        m = MagicMock()
        m.json.return_value = data
        return m

    def test_returns_json_on_success(self):
        with patch("recorder.requests.post", return_value=self._fake_resp({"response": "ok"})):
            result = recorder._ollama_post({"model": "m", "prompt": "p", "stream": False}, timeout=30)
        assert result == {"response": "ok"}

    def test_retries_on_timeout(self):
        good = self._fake_resp({"response": "ok"})
        with patch("recorder.requests.post", side_effect=[
            requests.exceptions.Timeout(), good,
        ]) as mock_post, patch("time.sleep"):
            result = recorder._ollama_post({"model": "m", "prompt": "p", "stream": False}, timeout=30)
        assert result == {"response": "ok"}
        assert mock_post.call_count == 2

    def test_retries_on_connection_error(self):
        good = self._fake_resp({"response": "ok"})
        with patch("recorder.requests.post", side_effect=[
            requests.exceptions.ConnectionError(), good,
        ]) as mock_post, patch("time.sleep"):
            result = recorder._ollama_post({"model": "m", "prompt": "p", "stream": False}, timeout=30)
        assert result == {"response": "ok"}
        assert mock_post.call_count == 2

    def test_raises_after_max_retries(self):
        with patch("recorder.requests.post", side_effect=requests.exceptions.Timeout()), \
             patch("time.sleep"):
            with pytest.raises(requests.exceptions.Timeout):
                recorder._ollama_post({"model": "m", "prompt": "p", "stream": False}, timeout=30)

    def test_max_retries_attempts(self):
        with patch("recorder.requests.post", side_effect=requests.exceptions.Timeout()) as mock_post, \
             patch("time.sleep"):
            with pytest.raises(requests.exceptions.Timeout):
                recorder._ollama_post({"model": "m", "prompt": "p", "stream": False}, timeout=30)
        assert mock_post.call_count == recorder._MAX_RETRIES

    def test_does_not_retry_http_errors(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")
        with patch("recorder.requests.post", return_value=mock_resp) as mock_post:
            with pytest.raises(Exception, match="HTTP 500"):
                recorder._ollama_post({"model": "m", "prompt": "p", "stream": False}, timeout=30)
        assert mock_post.call_count == 1

    def test_exponential_backoff_delays(self):
        with patch("recorder.requests.post", side_effect=requests.exceptions.Timeout()), \
             patch("time.sleep") as mock_sleep:
            with pytest.raises(requests.exceptions.Timeout):
                recorder._ollama_post({"model": "m", "prompt": "p", "stream": False}, timeout=30)
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_args == [1, 2]  # 1s then 2s; no sleep after final attempt


# ---------------------------------------------------------------------------
# _chunk_text
# ---------------------------------------------------------------------------

class TestChunkText:
    def test_short_text_returns_single_chunk(self):
        text = "Hello world. How are you?"
        result = recorder._chunk_text(text, max_words=100)
        assert result == [text]

    def test_splits_at_sentence_boundary(self):
        sentence_a = "First sentence here."
        sentence_b = " ".join(["word"] * 5)
        text = f"{sentence_a} {sentence_b}"
        result = recorder._chunk_text(text, max_words=4)
        assert len(result) == 2
        assert sentence_a in result[0]
        assert sentence_b in result[1]

    def test_preserves_all_words(self):
        text = "One two three. Four five six. Seven eight nine."
        chunks = recorder._chunk_text(text, max_words=4)
        rejoined = " ".join(chunks)
        for word in ["One", "two", "three", "Four", "five", "six", "Seven", "eight", "nine"]:
            assert word in rejoined

    def test_single_long_sentence_stays_as_one_chunk(self):
        text = " ".join(["word"] * 500)
        result = recorder._chunk_text(text, max_words=50)
        assert len(result) == 1


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

    def test_chunks_long_text_into_multiple_calls(self):
        long_text = ". ".join(["word " * 50] * 10) + "."  # ~500 words in 10 sentences
        responses = iter(["chunk_clean"] * 20)

        def fake_ollama_post(payload, timeout):
            return {"response": next(responses)}

        with patch("recorder._ollama_post", side_effect=fake_ollama_post) as mock_post, \
             patch.dict(recorder.cfg, {"ollama_model": "m", "ollama_prompt": "{transcription}"}):
            result = recorder.clean_with_ollama(long_text)

        assert mock_post.call_count > 1
        assert "chunk_clean" in result

    def test_short_text_makes_single_call(self):
        short_text = "Just a short sentence."
        with patch("recorder._ollama_post", return_value={"response": "cleaned"}) as mock_post, \
             patch.dict(recorder.cfg, {"ollama_model": "m", "ollama_prompt": "{transcription}"}):
            recorder.clean_with_ollama(short_text)
        assert mock_post.call_count == 1


# ---------------------------------------------------------------------------
# process_recording
# ---------------------------------------------------------------------------

class TestProcessRecording:
    def _frames(self, seconds: float) -> list[np.ndarray]:
        n = int(seconds * recorder.SAMPLE_RATE)
        return [np.zeros((n, 1), dtype="float32")]

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
        patch("recorder.copy_to_clipboard") as mock_clip:
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
        patch("recorder.copy_to_clipboard") as mock_clip:
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
             patch("recorder.os.remove") as mock_remove:
            recorder.process_recording("20240101_000000", frames)

        mock_remove.assert_not_called()


# ---------------------------------------------------------------------------
# toggle_recording
# ---------------------------------------------------------------------------

class TestToggleRecording:
    def setup_method(self):
        recorder.is_recording = False
        recorder.audio_buffer = []

    def test_first_call_sets_recording_true_and_clears_buffer(self):
        recorder.audio_buffer = [np.zeros((100, 1))]  # stale data
        recorder.toggle_recording()
        assert recorder.is_recording is True
        assert recorder.audio_buffer == []

    def test_second_call_stops_recording_and_spawns_thread(self):
        recorder.is_recording = True
        recorder.audio_buffer = [np.zeros((100, 1), dtype="float32")]
        with patch("threading.Thread") as mock_thread:
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

        with patch("threading.Thread", side_effect=fake_thread):
            recorder.toggle_recording()

        assert len(captured_frames) == 1
        assert np.array_equal(captured_frames[0], sentinel)

