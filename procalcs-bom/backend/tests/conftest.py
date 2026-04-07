"""
conftest.py — Shared pytest fixtures and configuration.
"""

import pytest
import sys
import os

# Ensure backend is importable from all test files
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
