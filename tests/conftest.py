"""
Stub hardware-dependent modules before recorder.py is imported.

sounddevice  — needs a real audio device
pynput       — needs macOS Accessibility permission + Quartz
scipy.io.wavfile — fine to stub; we test logic, not file I/O format
"""

import enum
import sys
from unittest.mock import MagicMock


# pynput.keyboard.Key must behave like a real Enum so that _parse_hotkey
# can look up names via Key["alt_r"] and raise KeyError for unknown names.
class _MockKey(enum.Enum):
    alt_r = "alt_r"
    alt_l = "alt_l"
    cmd = "cmd"
    ctrl = "ctrl"
    f13 = "f13"


_mock_keyboard = MagicMock()
_mock_keyboard.Key = _MockKey

_mock_pynput = MagicMock()
_mock_pynput.keyboard = _mock_keyboard

sys.modules["sounddevice"] = MagicMock()
sys.modules["pynput"] = _mock_pynput
sys.modules["pynput.keyboard"] = _mock_keyboard
sys.modules["scipy"] = MagicMock()
sys.modules["scipy.io"] = MagicMock()
sys.modules["scipy.io.wavfile"] = MagicMock()
