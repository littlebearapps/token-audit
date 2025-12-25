"""
Pytest configuration for benchmark tests.

Provides fixtures that isolate benchmark tests from polluting the
user's real token-audit session storage.
"""

import contextlib
from pathlib import Path
from typing import Generator

import pytest

import token_audit.server.tools as tools_module
from token_audit.server.live_tracker import LiveTracker
from token_audit.storage import StreamingStorage


@pytest.fixture(autouse=True)
def isolated_tracker(tmp_path: Path) -> Generator[LiveTracker, None, None]:
    """Replace the global tracker with one using temp storage.

    This fixture is auto-used for all benchmark tests to prevent
    test sessions from polluting the user's real session browser.

    The original tracker is restored after each test.
    """
    # Save the original tracker
    original_tracker = tools_module._tracker

    # Create isolated storage in temp directory
    storage = StreamingStorage(base_dir=tmp_path / "sessions")
    isolated = LiveTracker(storage=storage)

    # Replace the global tracker
    tools_module._tracker = isolated

    yield isolated

    # Stop any active session before cleanup
    if isolated._active_session:
        with contextlib.suppress(Exception):
            isolated.stop_session()

    # Restore the original tracker
    tools_module._tracker = original_tracker
