"""
conftest.py — Shared pytest fixtures and configuration.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock

# Ensure backend is importable from all test files
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Shim optional SDKs so the suite runs locally without installing them.
# Real CI / prod deploys have them installed via requirements.txt, in
# which case these shims are harmless no-ops because the real modules
# get imported first.
if "anthropic" not in sys.modules:
    _anthropic_stub = MagicMock()
    _anthropic_stub.Anthropic = MagicMock()
    sys.modules["anthropic"] = _anthropic_stub

if "google.cloud.firestore" not in sys.modules:
    _google_stub = MagicMock()
    _google_stub.cloud = MagicMock()
    _firestore_stub = MagicMock()
    _google_stub.cloud.firestore = _firestore_stub
    sys.modules.setdefault("google", _google_stub)
    sys.modules.setdefault("google.cloud", _google_stub.cloud)
    sys.modules["google.cloud.firestore"] = _firestore_stub
