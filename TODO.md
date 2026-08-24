# TODO

- README is wrong about the core interaction: it says "Press the right Option key to start recording" and has a whole "Grant Accessibility access" / `pynput` section, but the hotkey was replaced with Enter-to-toggle (`refactor: replace pynput hotkey with Enter-to-toggle`) — the recorder now just does `input()`. ROADMAP.md already flags this exact drift as the #1 priority item ("Fix README / hotkey / Enter drift", effort S) but it was never done.
- No CI — there's a real `tests/` suite (`make test`) but nothing runs it on push.

See ROADMAP.md (already in the repo) for the fuller backlog — Phase 0 is specifically about closing gaps like this before any new features.
