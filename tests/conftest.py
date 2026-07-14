"""
Stub hardware-dependent modules before recorder.py is imported.

sounddevice  — needs a real audio device
scipy.io.wavfile — fine to stub; we test logic, not file I/O format
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

sys.modules["sounddevice"] = MagicMock()
sys.modules["scipy"] = MagicMock()
sys.modules["scipy.io"] = MagicMock()
sys.modules["scipy.io.wavfile"] = MagicMock()
sys.modules["faster_whisper"] = MagicMock()
