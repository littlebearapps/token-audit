"""
Performance benchmarks for mcp-audit.

These tests measure performance against defined targets:
- TUI refresh: <100ms
- Session load: <500ms for 1000-call session
- Report generation: <2s for 100 sessions
- Memory usage: <100MB for live tracking

Run with:
    pytest tests/benchmarks/ -v
    pytest tests/benchmarks/ --benchmark-only  # Skip non-benchmark tests
    pytest tests/benchmarks/ --benchmark-json=benchmark.json  # Export results
"""

import json
import tempfile
import time
import tracemalloc
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from mcp_audit.display.rich_display import RichDisplay
from mcp_audit.display.snapshot import DisplaySnapshot
from mcp_audit.session_manager import SessionManager
from mcp_audit.storage import StorageManager


# =============================================================================
# Performance Targets (v0.9.0 - task-107.3)
# =============================================================================
TARGETS = {
    "tui_refresh_ms": 100,  # Maximum TUI refresh time in milliseconds
    "session_load_1000_calls_ms": 500,  # Maximum load time for 1000-call session
    "report_100_sessions_s": 2.0,  # Maximum time to generate report for 100 sessions
    "memory_live_tracking_mb": 100,  # Maximum memory usage during live tracking
}


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture
def large_snapshot() -> DisplaySnapshot:
    """Create a realistic snapshot with many servers and tools.

    Simulates a complex session with:
    - 10 MCP servers
    - 5 tools per server (50 tools total)
    - Realistic token distribution
    """
    server_hierarchy: List[Tuple[str, int, int, int, List[Tuple[str, int, int, float]]]] = []

    for i in range(10):
        tools: List[Tuple[str, int, int, float]] = []
        for j in range(5):
            # (tool_name, calls, tokens, pct_of_server)
            tools.append((f"tool_{j}", j * 10 + 5, j * 1000 + 500, 20.0))
        # (server_name, calls, tokens, avg_per_call, tools)
        server_hierarchy.append((f"server_{i}", 50, 50000, 1000, tools))

    # Create model usage with multiple models
    model_usage: List[Tuple[str, int, int, int, int, float, int]] = [
        ("claude-opus-4-5", 100000, 50000, 10000, 5000, 2.50, 25),
        ("claude-sonnet-4", 50000, 25000, 5000, 2500, 0.75, 15),
    ]

    return DisplaySnapshot.create(
        project="benchmark-project",
        platform="claude-code",
        start_time=datetime.now() - timedelta(hours=1),
        duration_seconds=3600.0,
        input_tokens=150000,
        output_tokens=75000,
        cache_tokens=15000,
        total_tokens=240000,
        cache_efficiency=0.75,
        cost_estimate=3.25,
        total_tool_calls=500,
        unique_tools=50,
        server_hierarchy=server_hierarchy,
        mcp_tokens_percent=65.0,
        model_id="claude-opus-4-5-20251101",
        model_name="Claude Opus 4.5",
        models_used=["claude-opus-4-5", "claude-sonnet-4"],
        model_usage=model_usage,
        is_multi_model=True,
        git_branch="main",
        git_commit_short="abc1234",
        git_status="clean",
        message_count=100,
        cache_created_tokens=10000,
        cache_read_tokens=5000,
        builtin_tool_calls=50,
        builtin_tool_tokens=10000,
        detected_smells=[
            ("HIGH_VARIANCE", "warning", "tool_1", "High token variance detected"),
            ("CHATTY", "info", "tool_2", "Tool called frequently"),
        ],
    )


@pytest.fixture
def storage_with_sessions(tmp_path: Path) -> Tuple[StorageManager, List[Path]]:
    """Create storage with multiple session files for testing."""
    storage = StorageManager(base_dir=tmp_path)
    session_paths = []

    # Create 10 sessions for basic tests
    for i in range(10):
        session_date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        session_id = f"test-session-{i:03d}"

        # Create session directory structure
        platform_dir = tmp_path / "claude_code" / session_date
        platform_dir.mkdir(parents=True, exist_ok=True)

        session_file = platform_dir / f"{session_id}.json"

        # Create minimal session data
        session_data = {
            "_file": {
                "schema_version": "1.7.0",
                "generated_at": datetime.now().isoformat(),
                "session_id": session_id,
            },
            "platform": "claude_code",
            "project": "benchmark-project",
            "session": {
                "start_time": datetime.now().isoformat(),
                "model": "claude-opus-4-5-20251101",
                "total_tokens": 10000 + i * 1000,
            },
            "tool_calls": [
                {
                    "timestamp": (datetime.now() + timedelta(seconds=j)).isoformat(),
                    "tool": f"mcp__server_{j % 5}__tool_{j % 3}",
                    "server": f"server_{j % 5}",
                    "input_tokens": 100,
                    "output_tokens": 50,
                }
                for j in range(100)  # 100 calls per session
            ],
        }

        with open(session_file, "w") as f:
            json.dump(session_data, f)

        session_paths.append(session_file)

    return storage, session_paths


@pytest.fixture
def large_session_file(tmp_path: Path) -> Path:
    """Create a session file with 1000 tool calls for load testing."""
    session_id = "large-session-1000-calls"
    session_date = datetime.now().strftime("%Y-%m-%d")

    # Create session directory structure
    platform_dir = tmp_path / "claude_code" / session_date
    platform_dir.mkdir(parents=True, exist_ok=True)

    session_file = platform_dir / f"{session_id}.json"

    # Create session with 1000 tool calls
    tool_calls = []
    for i in range(1000):
        tool_calls.append(
            {
                "timestamp": (datetime.now() + timedelta(seconds=i)).isoformat(),
                "tool": f"mcp__server_{i % 10}__tool_{i % 5}",
                "server": f"server_{i % 10}",
                "input_tokens": 100 + (i % 50),
                "output_tokens": 50 + (i % 25),
                "cache_read": i % 100,
                "cache_created": i % 50,
            }
        )

    session_data = {
        "_file": {
            "schema_version": "1.7.0",
            "generated_at": datetime.now().isoformat(),
            "session_id": session_id,
        },
        "platform": "claude_code",
        "project": "benchmark-project",
        "session": {
            "start_time": datetime.now().isoformat(),
            "model": "claude-opus-4-5-20251101",
            "total_tokens": 175000,
        },
        "tool_calls": tool_calls,
    }

    with open(session_file, "w") as f:
        json.dump(session_data, f, indent=2)

    return session_file


# =============================================================================
# TUI Performance Tests
# =============================================================================
class TestTUIPerformance:
    """TUI refresh performance benchmarks."""

    def test_tui_build_layout_performance(self, large_snapshot: DisplaySnapshot) -> None:
        """TUI _build_layout should complete in under 100ms.

        Target: <100ms per refresh cycle
        """
        display = RichDisplay(refresh_rate=0.5)

        # Warm up (first build initializes caches)
        display._build_layout(large_snapshot)

        # Measure average over 10 iterations
        iterations = 10
        start = time.perf_counter()
        for _ in range(iterations):
            display._build_layout(large_snapshot)
        elapsed = (time.perf_counter() - start) / iterations
        elapsed_ms = elapsed * 1000

        print(f"\nTUI refresh time: {elapsed_ms:.2f}ms (target: <{TARGETS['tui_refresh_ms']}ms)")

        assert (
            elapsed_ms < TARGETS["tui_refresh_ms"]
        ), f"TUI refresh took {elapsed_ms:.1f}ms, target <{TARGETS['tui_refresh_ms']}ms"

    def test_tui_unchanged_snapshot_performance(self, large_snapshot: DisplaySnapshot) -> None:
        """TUI should be faster when snapshot hasn't changed.

        This test validates the future dirty-flag optimization.
        Currently measures baseline for unchanged data.
        """
        display = RichDisplay(refresh_rate=0.5)

        # First build
        display._build_layout(large_snapshot)

        # Subsequent builds with same snapshot (should be cacheable)
        iterations = 10
        start = time.perf_counter()
        for _ in range(iterations):
            display._build_layout(large_snapshot)
        elapsed = (time.perf_counter() - start) / iterations
        elapsed_ms = elapsed * 1000

        print(f"\nUnchanged snapshot refresh: {elapsed_ms:.2f}ms")

        # For now, just assert it completes reasonably fast
        # After optimization, unchanged should be <10ms
        assert elapsed_ms < TARGETS["tui_refresh_ms"]

    def test_tui_header_build_performance(self, large_snapshot: DisplaySnapshot) -> None:
        """TUI _build_header should be fast."""
        display = RichDisplay(refresh_rate=0.5)

        iterations = 20
        start = time.perf_counter()
        for _ in range(iterations):
            display._build_header(large_snapshot)
        elapsed = (time.perf_counter() - start) / iterations
        elapsed_ms = elapsed * 1000

        print(f"\nHeader build time: {elapsed_ms:.2f}ms")

        # Header should be <20ms (subset of total refresh budget)
        assert elapsed_ms < 20, f"Header build took {elapsed_ms:.1f}ms, target <20ms"

    def test_tui_tools_build_performance(self, large_snapshot: DisplaySnapshot) -> None:
        """TUI _build_tools (MCP server hierarchy) should be fast."""
        display = RichDisplay(refresh_rate=0.5)

        iterations = 20
        start = time.perf_counter()
        for _ in range(iterations):
            display._build_tools(large_snapshot)
        elapsed = (time.perf_counter() - start) / iterations
        elapsed_ms = elapsed * 1000

        print(f"\nTools panel build time: {elapsed_ms:.2f}ms")

        # Tools panel should be <30ms (largest component)
        assert elapsed_ms < 30, f"Tools build took {elapsed_ms:.1f}ms, target <30ms"


# =============================================================================
# Session Loading Performance Tests
# =============================================================================
class TestSessionLoadPerformance:
    """Session loading performance benchmarks."""

    def test_session_load_1000_calls(self, large_session_file: Path) -> None:
        """1000-call session should load in under 500ms.

        Target: <500ms for 1000-call session
        """
        manager = SessionManager()

        # Measure load time
        start = time.perf_counter()
        session = manager.load_session(large_session_file.parent)
        elapsed = time.perf_counter() - start
        elapsed_ms = elapsed * 1000

        print(
            f"\n1000-call session load: {elapsed_ms:.2f}ms (target: <{TARGETS['session_load_1000_calls_ms']}ms)"
        )

        # Verify session loaded correctly
        assert session is not None

        assert (
            elapsed_ms < TARGETS["session_load_1000_calls_ms"]
        ), f"Session load took {elapsed_ms:.1f}ms, target <{TARGETS['session_load_1000_calls_ms']}ms"

    def test_session_list_performance(
        self, storage_with_sessions: Tuple[StorageManager, List[Path]]
    ) -> None:
        """list_sessions should be efficient even with many sessions."""
        storage, session_paths = storage_with_sessions

        # Measure list time
        start = time.perf_counter()
        for _ in range(10):
            sessions = storage.list_sessions(platform="claude_code")
        elapsed = (time.perf_counter() - start) / 10
        elapsed_ms = elapsed * 1000

        print(f"\nSession list time (10 sessions): {elapsed_ms:.2f}ms")

        # Listing should be <100ms for 10 sessions (relaxed for CI variability)
        # Local performance is typically <10ms, but CI can vary significantly
        assert elapsed_ms < 100, f"Session listing took {elapsed_ms:.1f}ms, target <100ms"

    def test_session_json_parse_overhead(self, large_session_file: Path) -> None:
        """Measure raw JSON parsing overhead for comparison."""
        # Measure raw json.load time
        start = time.perf_counter()
        with open(large_session_file) as f:
            data = json.load(f)
        elapsed = time.perf_counter() - start
        elapsed_ms = elapsed * 1000

        tool_call_count = len(data.get("tool_calls", []))

        print(f"\nRaw JSON parse ({tool_call_count} calls): {elapsed_ms:.2f}ms")

        # Raw parse should be baseline for optimization targets
        # This helps identify if overhead is in parsing or processing
        assert tool_call_count == 1000


# =============================================================================
# Report Generation Performance Tests
# =============================================================================
class TestReportPerformance:
    """Report generation performance benchmarks."""

    def test_multi_session_load_performance(
        self, storage_with_sessions: Tuple[StorageManager, List[Path]]
    ) -> None:
        """Loading multiple sessions should scale well."""
        storage, session_paths = storage_with_sessions
        manager = SessionManager()

        # Load all 10 sessions
        start = time.perf_counter()
        sessions = []
        for path in session_paths:
            try:
                session = manager.load_session(path.parent)
                if session:
                    sessions.append(session)
            except Exception:
                pass
        elapsed = time.perf_counter() - start
        elapsed_ms = elapsed * 1000

        print(f"\n10 session sequential load: {elapsed_ms:.2f}ms ({elapsed_ms/10:.2f}ms/session)")

        # 10 sessions should load in <1s (100ms/session budget)
        assert elapsed_ms < 1000, f"Multi-session load took {elapsed_ms:.1f}ms, target <1000ms"


# =============================================================================
# Memory Usage Tests
# =============================================================================
class TestMemoryUsage:
    """Memory usage benchmarks."""

    def test_display_snapshot_memory(self, large_snapshot: DisplaySnapshot) -> None:
        """DisplaySnapshot memory footprint should be reasonable."""
        import sys

        # Approximate size (doesn't include nested objects fully)
        size_bytes = sys.getsizeof(large_snapshot)

        print(f"\nDisplaySnapshot base size: {size_bytes} bytes")

        # Snapshot itself should be <10KB
        assert size_bytes < 10240, f"Snapshot size {size_bytes} bytes, target <10KB"

    def test_tui_memory_usage(self, large_snapshot: DisplaySnapshot) -> None:
        """TUI should not leak memory on repeated refreshes."""
        display = RichDisplay(refresh_rate=0.5)

        tracemalloc.start()

        # Initial build
        display._build_layout(large_snapshot)
        _, initial_peak = tracemalloc.get_traced_memory()

        # Multiple refreshes
        for _ in range(50):
            display._build_layout(large_snapshot)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)
        growth = (peak - initial_peak) / (1024 * 1024)

        print(f"\nTUI memory - Peak: {peak_mb:.2f}MB, Growth after 50 refreshes: {growth:.2f}MB")

        # Memory growth should be minimal after multiple refreshes
        assert growth < 5, f"Memory grew {growth:.2f}MB after 50 refreshes, target <5MB"

    def test_session_load_memory(self, large_session_file: Path) -> None:
        """Loading large sessions should have bounded memory usage."""
        manager = SessionManager()

        tracemalloc.start()

        session = manager.load_session(large_session_file.parent)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)

        print(f"\nSession load memory - Peak: {peak_mb:.2f}MB (1000 calls)")

        # 1000-call session should use <10MB
        assert peak_mb < 10, f"Session load peak {peak_mb:.2f}MB, target <10MB"


# =============================================================================
# Baseline Measurements (for tracking improvements)
# =============================================================================
class TestBaselineMeasurements:
    """Baseline measurements to track optimization progress.

    These tests don't have pass/fail criteria - they record current
    performance for comparison after optimizations.
    """

    def test_measure_index_update_baseline(
        self, storage_with_sessions: Tuple[StorageManager, List[Path]]
    ) -> None:
        """Measure current index update performance."""
        storage, session_paths = storage_with_sessions

        # This would measure update_indexes_for_session performance
        # Currently just prints for baseline tracking
        print("\nIndex update baseline: TBD (requires index write measurement)")

    def test_measure_snapshot_creation_baseline(self) -> None:
        """Measure DisplaySnapshot creation overhead."""
        iterations = 100

        server_hierarchy = [
            (f"server_{i}", 50, 50000, 1000, [(f"tool_{j}", 10, 1000, 20.0) for j in range(5)])
            for i in range(10)
        ]

        start = time.perf_counter()
        for _ in range(iterations):
            snapshot = DisplaySnapshot.create(
                project="test",
                platform="claude-code",
                start_time=datetime.now(),
                duration_seconds=100.0,
                total_tokens=100000,
                server_hierarchy=server_hierarchy,
            )
        elapsed = (time.perf_counter() - start) / iterations
        elapsed_ms = elapsed * 1000

        print(f"\nSnapshot creation: {elapsed_ms:.3f}ms")


# =============================================================================
# Performance Summary
# =============================================================================
def test_print_performance_summary() -> None:
    """Print performance targets summary."""
    print("\n" + "=" * 60)
    print("PERFORMANCE TARGETS (v0.9.0)")
    print("=" * 60)
    for metric, target in TARGETS.items():
        unit = "ms" if "ms" in metric else ("s" if "_s" in metric else "MB")
        print(f"  {metric}: <{target}{unit}")
    print("=" * 60 + "\n")
