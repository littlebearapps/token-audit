"""
Pytest configuration for token-audit tests.

This conftest.py ensures the package can be imported during testing
by installing it in editable mode or adding src to the path.
"""

import sys
from pathlib import Path

# Add src directory to path for imports during development
src_path = Path(__file__).parent.parent / "src"
if src_path.exists() and str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
