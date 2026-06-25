# Roadmap

**North star:** Turn spoken thought into paste-ready text as fast and reliably as possible — locally, from the terminal, with no account and no cloud.

This project does one thing: **voice → text you can actually use.** Everything else (note apps, LLM fine-tuning, a native app) is downstream of that loop working well every time.

---

## Principles

1. **Terminal first.** The recorder runs in a terminal session you control. No hidden daemons, no mystery state. If a macOS app ships later, it must be at least as dependable as `make run` — including clipboard delivery.
2. **Local by default.** Audio and transcripts stay on your machine. Cloud APIs are opt-in, never required.
3. **Paste is the product.** The cleaned transcript on the clipboard (and saved to disk) is the deliverable. Optimise for “I spoke, I pasted, I moved on.”
4. **Faithful, not clever.** Cleanup fixes grammar and fillers; it does not summarise, invent, or restructure your ideas unless you change the prompt.
5. **Composable, not monolithic.** Small scripts, clear pipeline stages, config in `config.json`. Easy to swap whisper model, skip Ollama, or batch-process old files.

---

## Current state

What works today:

```
mic → raw WAV → ffmpeg loudnorm → faster-whisper → ollama → clipboard + saved .txt
```

| Capability | Status |
|------------|--------|
| Live recording (`make run`) | ✅ Enter to start/stop |
| Batch import (`make process`) | ✅ WAV, MP3, M4A, FLAC, OGG, AAC |
| LLM cleanup + smart filenames | ✅ Ollama, chunked for long text |
| Russian transcripts | ✅ Auto-switches to `qwen3` when Cyrillic detected |
| Unit tests for pipeline logic | ✅ |
| Global hotkey (right Option) | ⚠️ Removed in favour of Enter; README still describes Option |
| Background / always-on | ❌ Must keep terminal open |

Known gaps to close before new features:

- **Docs drift:** README describes `pynput` + right Option; code uses Enter in the foreground terminal.
- **Activation friction:** Enter requires the terminal focused; global hotkey needs Accessibility permission and was dropped for reliability.
- **Latency:** First run downloads whisper; full pipeline (normalize → transcribe → two Ollama calls) can feel slow for short memos.
- **Ollama hard dependency:** No fast path to “raw whisper only” when Ollama is down or you want speed over polish.

---

## Phase 0 — Make the core loop bulletproof

*Goal: You trust it for daily note-taking. No new features until this feels boringly reliable.*

### 0.1 Activation model (pick one, document it)

| Option | Pros | Cons |
|--------|------|------|
| **A. Terminal + Enter** (current) | Simple, no Accessibility permission | Terminal must be focused |
| **B. Global hotkey** (`pynput` / `alt_r`) | Works from any app | Accessibility permission, edge-case bugs |
| **C. Hybrid** | Hotkey when daemon runs; Enter as fallback | Two code paths to maintain |

**Recommendation:** Ship **C** with `hotkey` in `config.json` (`null` = Enter-only). Default to Enter until hotkey path passes a manual test checklist on your machine. Update README to match.

### 0.2 Speed modes

Add `cleanup_mode` to config:

| Mode | Pipeline | When to use |
|------|----------|-------------|
| `full` | whisper → ollama cleanup → filename → clipboard | Default; polished prose |
| `fast` | whisper → clipboard | Ollama offline or quick capture |
| `raw-only` | whisper → save raw transcript | Archival / re-process later |

Target: **fast mode under ~3s** for a 30-second memo on Apple Silicon with `small` (or `base`).

### 0.3 Feedback you can see

- Terminal status line: `● REC` / `○ idle` / `… transcribing` / `✓ copied (142 words)`
- Optional macOS notification on completion (already partially explored in history; bring back behind `notify_on_complete: true`)
- Clear error messages: “Ollama refused — saved raw transcript to …”

### 0.4 Resilience

- [ ] Ollama optional: save raw transcript and copy it if cleanup fails
- [ ] Keep raw audio when processing fails (today audio is deleted on success only — good; extend to “delete only on full success”)
- [ ] `make doctor` — check ffmpeg, whisper model, ollama, mic permissions, Accessibility if hotkey enabled
- [ ] Align README, `config.json` schema, and tests (hotkey tests exist but code path was removed)

**Exit criteria:** Record 20 memos in a week without reaching for a different tool. Clipboard always has the right text.

---

## Phase 1 — Note-taking automation

*Goal: Capture thought without thinking about the tool. Your voice memos become a searchable personal corpus.*

### 1.1 Ingest without live recording

You already have `make process`. Extend it:

- **Watch mode:** `make watch` — `fswatch` on `recordings_dir`; process new files as they land (Voice Memos export, iPhone sync folder, QuickTime exports).
- **Voice Memos path:** Document a one-time setup: export / sync folder → `recordings_dir` in config.
- **Idempotency:** Skip files already in `clean-transcript/` (track by hash or filename manifest).

### 1.2 Output that fits your notes

- **Prompt presets** in config: `journal`, `meeting`, `todo`, `code-dictation` — each a different `ollama_prompt`.
- **Front matter** on saved transcripts (optional YAML header):

  ```yaml
  ---
  created: 2026-06-25T14:32:00
  duration_sec: 47
  model: small
  preset: journal
  ---
  ```

- **Append vs new file:** `output_mode: new | daily` — one file per day (`2026-06-25.md`) for journal-style capture.

### 1.3 Find old notes

- Simple `make search "keyword"` — ripgrep across `clean-transcript/`.
- Optional symlink or copy target: `notes_export_dir` for Obsidian / Bear / plain Markdown vault.

**Exit criteria:** iPhone voice memo → text in your notes folder within minutes, unattended.

---

## Phase 2 — Faster and sharper transcription

*Goal: Reduce time-to-clipboard. Quality gains without new product surface area.*

### 2.1 Model and hardware tuning

- Document whisper model tradeoffs (`tiny` / `base` / `small` / `medium`) with your hardware.
- Evaluate **MLX Whisper** on Apple Silicon for lower latency.
- Config: `whisper_device`, `compute_type` — already partially there; expose in `config.json` with sane defaults.

### 2.2 Pipeline efficiency

- **Parallelise:** Start Ollama filename generation only after cleanup (or skip in `fast` mode).
- **Skip normalize** for live recordings already at 16 kHz mono (keep normalize for batch imports).
- **Warm models:** Load whisper at startup; optional `ollama run` warm-up in `make run`.

### 2.3 Audio smarts (optional, behind flags)

- Voice activity detection — trim trailing silence before whisper.
- `min_duration` / `max_duration` guards with clear user feedback.
- Optional: keep normalized audio for re-runs with a better model later (`retain_audio: true`).

**Exit criteria:** Sub-5s end-to-end for typical 1-minute memo in `fast` mode.

---

## Phase 3 — Always-on terminal workflow

*Goal: It runs like a utility, not a project you babysit.*

- **`make install`** — venv, deps, pull default models, print Accessibility checklist.
- **Login item (optional):** `launchd` plist template that runs `make run` in a dedicated Terminal window or `tmux` session.
- **Single instance lock** — prevent two recorders fighting for the mic.
- **Log rotation** — `logs/recorder.log` capped or dated.

Still terminal. Still one process you can `Ctrl-C` and reason about.

---

## Phase 4 — macOS app (only if it earns its place)

*Explicitly secondary. Do not pursue until Phases 0–2 are solid.*

A menu-bar or hotkey app is worth building **only if**:

1. Global activation works without flaky Accessibility behaviour.
2. Clipboard delivery is 100% reliable (same as `pbcopy` today).
3. You can copy-paste from it without thinking.
4. It does not fork the pipeline — thin wrapper over the same Python core or a shared library.

### If pursued, scope minimally

- Menu bar icon: idle / recording / processing.
- Global hotkey (right Option or configurable).
- Click to copy last transcript.
- Preferences mirror `config.json` — same file, no second source of truth.

### If not pursued

- Terminal + global hotkey daemon (Phase 0) may be enough forever.
- Shortcuts.app wrapper: run a shell script that triggers recording — zero native code.

**Decision gate:** Revisit after 30 days of daily Phase 0–1 usage. If you never think about the terminal window, stop. If hotkey + Accessibility still annoys you, prototype the app.

---

## Phase 5 — Personal training data (exploratory)

*Not the core product. A natural by-product of faithful transcription over time.*

If you keep speaking instead of typing, you accumulate paired data:

| Asset | Use |
|-------|-----|
| Raw whisper output | ASR ground truth approximations |
| Cleaned transcript | Target style / vocabulary |
| Audio (opt-in retention) | Fine-tune whisper or train adapters |

Possible future commands (no commitment to build):

- `make export-corpus` → JSONL / ShareGPT format for fine-tuning.
- `make stats` — word count, speaking time, vocabulary drift over months.
- Privacy guardrails: local-only export, no upload helpers, explicit `retain_audio` default `false`.

This stays **open-ended**. The roadmap does not depend on it. Phases 0–1 deliver value even if you never export a training set.

---

## Non-goals (for now)

To keep the project sharp:

- **Cloud transcription** as default (breaks local-first trust).
- **Real-time streaming UI** with partial results — nice someday, not before core loop is fast enough.
- **Collaboration / multi-user** — single operator, single machine.
- **Built-in note editor** — output goes to clipboard and files; your editor stays your editor.
- **Summarisation as default** — contradicts faithful capture; keep as an optional prompt preset only.
- **Windows / Linux port** — macOS-first until core is done; pipeline is mostly portable if needed later.

---

## Suggested priority order

```
Phase 0  ████████████████████  now
Phase 1  ████████████░░░░░░░░  next
Phase 2  ████████░░░░░░░░░░░░  when 0–1 feel easy
Phase 3  ████░░░░░░░░░░░░░░░░  when you want always-on
Phase 4  ██░░░░░░░░░░░░░░░░░░  only if terminal path fails you
Phase 5  █░░░░░░░░░░░░░░░░░░░  whenever corpus is large enough to matter
```

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1 | Fix README / hotkey / Enter drift | S | Trust |
| 2 | `cleanup_mode: fast \| full` | S | Speed |
| 3 | Visible recording/processing status | S | UX |
| 4 | Ollama-failure fallback to raw | S | Reliability |
| 5 | `make doctor` | S | Setup |
| 6 | Watch folder (`make watch`) | M | Automation |
| 7 | Prompt presets + daily append | M | Note-taking |
| 8 | MLX / model tuning docs | M | Speed |
| 9 | launchd always-on template | M | Convenience |
| 10 | macOS app prototype | L | Only if justified |

*Effort: S = hours, M = days, L = weeks*

---

## How we know it’s working

| Metric | Target |
|--------|--------|
| Time to paste (30s memo, fast mode) | < 5 seconds |
| Failed runs per week | 0 |
| Times you use a different transcription tool | → 0 |
| Voice memos processed without manual intervention | > 80% (after watch mode) |
| Transcripts you actually paste or file | > 90% of recordings |

---

## Contributing to the roadmap

Open an issue with:

1. **Which phase** it belongs to (or why it needs a new phase).
2. **Which principle** it serves — especially “paste is the product” and “faithful, not clever.”
3. **What it does not do** — scope cuts are as important as features.

Features that make transcription faster, more reliable, or easier to route into your notes belong here. Features that turn vibing into a general AI assistant do not.