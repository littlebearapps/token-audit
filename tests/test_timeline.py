"""
Tests for the Session Timeline View (v0.8.0 - task-106.8).

Tests cover:
- TimelineBucket dataclass
- TimelineData dataclass
- Timeline computation (bucketing, spike detection)
- Timeline graph rendering
- Timeline AI export
"""

from datetime import date, datetime, timedelta, timezone

from token_audit.display.session_browser import (
    BrowserMode,
    SessionBrowser,
    TimelineBucket,
    TimelineData,
)

# ============================================================================
# TimelineBucket Tests
# ============================================================================


class TestTimelineBucket:
    """Tests for TimelineBucket dataclass."""

    def test_default_values(self) -> None:
        """Test default values for TimelineBucket."""
        bucket = TimelineBucket(
            bucket_index=0,
            start_seconds=0.0,
            duration_seconds=60.0,
        )

        assert bucket.bucket_index == 0
        assert bucket.start_seconds == 0.0
        assert bucket.duration_seconds == 60.0
        assert bucket.mcp_tokens == 0
        assert bucket.builtin_tokens == 0
        assert bucket.total_tokens == 0
        assert bucket.call_count == 0
        assert bucket.is_spike is False
        assert bucket.spike_magnitude == 0.0

    def test_with_all_fields(self) -> None:
        """Test TimelineBucket with all fields specified."""
        bucket = TimelineBucket(
            bucket_index=5,
            start_seconds=300.0,
            duration_seconds=60.0,
            mcp_tokens=1000,
            builtin_tokens=500,
            total_tokens=1500,
            call_count=10,
            is_spike=True,
            spike_magnitude=2.5,
        )

        assert bucket.bucket_index == 5
        assert bucket.start_seconds == 300.0
        assert bucket.mcp_tokens == 1000
        assert bucket.builtin_tokens == 500
        assert bucket.total_tokens == 1500
        assert bucket.call_count == 10
        assert bucket.is_spike is True
        assert bucket.spike_magnitude == 2.5


# ============================================================================
# TimelineData Tests
# ============================================================================


class TestTimelineData:
    """Tests for TimelineData dataclass."""

    def test_default_values(self) -> None:
        """Test default values for TimelineData."""
        data = TimelineData(
            session_date=date(2025, 1, 15),
            duration_seconds=3600.0,
            bucket_duration_seconds=60.0,
        )

        assert data.session_date == date(2025, 1, 15)
        assert data.duration_seconds == 3600.0
        assert data.bucket_duration_seconds == 60.0
        assert data.buckets == []
        assert data.spikes == []
        assert data.max_tokens_per_bucket == 0
        assert data.avg_tokens_per_bucket == 0.0
        assert data.total_tokens == 0
        assert data.total_mcp_tokens == 0
        assert data.total_builtin_tokens == 0

    def test_with_buckets_and_spikes(self) -> None:
        """Test TimelineData with buckets and spikes."""
        bucket1 = TimelineBucket(0, 0.0, 60.0, mcp_tokens=100, total_tokens=100)
        bucket2 = TimelineBucket(1, 60.0, 60.0, mcp_tokens=5000, total_tokens=5000, is_spike=True)

        data = TimelineData(
            session_date=date(2025, 1, 15),
            duration_seconds=120.0,
            bucket_duration_seconds=60.0,
            buckets=[bucket1, bucket2],
            spikes=[bucket2],
            max_tokens_per_bucket=5000,
            avg_tokens_per_bucket=2550.0,
            total_tokens=5100,
            total_mcp_tokens=5100,
        )

        assert len(data.buckets) == 2
        assert len(data.spikes) == 1
        assert data.max_tokens_per_bucket == 5000


# ============================================================================
# Timeline Computation Tests
# ============================================================================


class TestTimelineComputation:
    """Tests for timeline computation logic."""

    def test_bucket_duration_short_session(self) -> None:
        """Test bucket duration for sessions under 10 minutes."""
        # Sessions < 10 min should use 30-second buckets
        browser = SessionBrowser()
        browser._detail_data = {
            "session": {
                "duration_seconds": 300,  # 5 minutes
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "start_time": datetime.now(timezone.utc).isoformat(),
            },
            "server_sessions": {},
            "token_usage": {"total_tokens": 1000},
        }

        result = browser._compute_timeline_data()

        assert result is not None
        assert result.bucket_duration_seconds == 30.0  # 30-second buckets

    def test_bucket_duration_medium_session(self) -> None:
        """Test bucket duration for sessions 10-60 minutes."""
        browser = SessionBrowser()
        browser._detail_data = {
            "session": {
                "duration_seconds": 1800,  # 30 minutes
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "start_time": datetime.now(timezone.utc).isoformat(),
            },
            "server_sessions": {},
            "token_usage": {"total_tokens": 5000},
        }

        result = browser._compute_timeline_data()

        assert result is not None
        assert result.bucket_duration_seconds == 60.0  # 1-minute buckets

    def test_bucket_duration_long_session(self) -> None:
        """Test bucket duration for sessions 1-4 hours."""
        browser = SessionBrowser()
        browser._detail_data = {
            "session": {
                "duration_seconds": 7200,  # 2 hours
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "start_time": datetime.now(timezone.utc).isoformat(),
            },
            "server_sessions": {},
            "token_usage": {"total_tokens": 50000},
        }

        result = browser._compute_timeline_data()

        assert result is not None
        assert result.bucket_duration_seconds == 300.0  # 5-minute buckets

    def test_bucket_duration_very_long_session(self) -> None:
        """Test bucket duration for sessions over 4 hours."""
        browser = SessionBrowser()
        browser._detail_data = {
            "session": {
                "duration_seconds": 18000,  # 5 hours
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "start_time": datetime.now(timezone.utc).isoformat(),
            },
            "server_sessions": {},
            "token_usage": {"total_tokens": 100000},
        }

        result = browser._compute_timeline_data()

        assert result is not None
        assert result.bucket_duration_seconds == 900.0  # 15-minute buckets

    def test_spike_detection(self) -> None:
        """Test spike detection with Z-score threshold."""
        browser = SessionBrowser()
        start_time = datetime.now(timezone.utc)

        # Create session with one spike bucket (much higher than others)
        # Need enough data points with consistent values to detect the spike
        browser._detail_data = {
            "session": {
                "duration_seconds": 300,  # 5 minutes
                "timestamp": start_time.isoformat(),
                "start_time": start_time.isoformat(),
            },
            "server_sessions": {
                "test_server": {
                    "tools": {
                        "test_tool": {
                            "call_history": [
                                {
                                    "timestamp": (start_time + timedelta(seconds=10)).isoformat(),
                                    "total_tokens": 100,
                                },
                                {
                                    "timestamp": (start_time + timedelta(seconds=40)).isoformat(),
                                    "total_tokens": 100,
                                },
                                {
                                    "timestamp": (start_time + timedelta(seconds=70)).isoformat(),
                                    "total_tokens": 100,
                                },
                                {
                                    "timestamp": (start_time + timedelta(seconds=100)).isoformat(),
                                    "total_tokens": 100,
                                },
                                {
                                    "timestamp": (start_time + timedelta(seconds=130)).isoformat(),
                                    "total_tokens": 50000,  # HUGE SPIKE!
                                },
                                {
                                    "timestamp": (start_time + timedelta(seconds=160)).isoformat(),
                                    "total_tokens": 100,
                                },
                                {
                                    "timestamp": (start_time + timedelta(seconds=190)).isoformat(),
                                    "total_tokens": 100,
                                },
                                {
                                    "timestamp": (start_time + timedelta(seconds=220)).isoformat(),
                                    "total_tokens": 100,
                                },
                            ],
                        },
                    },
                },
            },
            "token_usage": {"total_tokens": 50700},
        }

        result = browser._compute_timeline_data()

        assert result is not None
        assert len(result.spikes) >= 1
        # The spike should be the bucket containing the 50000 token call
        spike = result.spikes[0]
        assert spike.is_spike is True
        assert spike.spike_magnitude > 2.0  # Z-score threshold

    def test_no_duration_returns_none(self) -> None:
        """Test that zero duration returns None."""
        browser = SessionBrowser()
        browser._detail_data = {
            "session": {
                "duration_seconds": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

        result = browser._compute_timeline_data()
        assert result is None

    def test_no_detail_data_returns_none(self) -> None:
        """Test that missing detail data returns None."""
        browser = SessionBrowser()
        browser._detail_data = None

        result = browser._compute_timeline_data()
        assert result is None


# ============================================================================
# Timeline Graph Rendering Tests
# ============================================================================


class TestTimelineGraphRendering:
    """Tests for timeline graph rendering."""

    def test_empty_buckets_shows_message(self) -> None:
        """Test that empty buckets shows 'No data' message."""
        browser = SessionBrowser()
        timeline = TimelineData(
            session_date=date.today(),
            duration_seconds=300.0,
            bucket_duration_seconds=60.0,
            buckets=[],
            max_tokens_per_bucket=0,
        )

        result = browser._generate_timeline_graph(timeline)

        assert "No data to display" in result.plain

    def test_graph_has_bars(self) -> None:
        """Test that graph generates bars for buckets."""
        browser = SessionBrowser()
        buckets = [
            TimelineBucket(i, i * 60.0, 60.0, mcp_tokens=1000, total_tokens=1000) for i in range(5)
        ]

        timeline = TimelineData(
            session_date=date.today(),
            duration_seconds=300.0,
            bucket_duration_seconds=60.0,
            buckets=buckets,
            max_tokens_per_bucket=1000,
            total_tokens=5000,
            total_mcp_tokens=5000,
        )

        result = browser._generate_timeline_graph(timeline)
        plain_text = result.plain

        # Should have Unicode box-drawing characters
        assert "\u2502" in plain_text  # Vertical bar
        assert "\u2514" in plain_text  # Bottom-left corner

    def test_spike_marker_in_graph(self) -> None:
        """Test that spike markers appear in the graph."""
        browser = SessionBrowser()
        spike_bucket = TimelineBucket(
            0, 0.0, 60.0, mcp_tokens=5000, total_tokens=5000, is_spike=True
        )

        timeline = TimelineData(
            session_date=date.today(),
            duration_seconds=60.0,
            bucket_duration_seconds=60.0,
            buckets=[spike_bucket],
            spikes=[spike_bucket],
            max_tokens_per_bucket=5000,
        )

        result = browser._generate_timeline_graph(timeline)

        # Should have spike marker triangle
        assert "\u25b2" in result.plain


# ============================================================================
# Helper Method Tests
# ============================================================================


class TestTimelineHelperMethods:
    """Tests for timeline helper methods."""

    def test_format_bucket_time_seconds(self) -> None:
        """Test bucket time formatting for seconds."""
        browser = SessionBrowser()

        assert browser._format_bucket_time(0) == "0:00"
        assert browser._format_bucket_time(30) == "0:30"
        assert browser._format_bucket_time(90) == "1:30"
        assert browser._format_bucket_time(600) == "10:00"

    def test_format_bucket_time_hours(self) -> None:
        """Test bucket time formatting for hours."""
        browser = SessionBrowser()

        assert browser._format_bucket_time(3600) == "1:00"
        assert browser._format_bucket_time(3900) == "1:05"
        assert browser._format_bucket_time(7200) == "2:00"

    def test_format_bucket_duration_seconds(self) -> None:
        """Test bucket duration formatting for seconds."""
        browser = SessionBrowser()

        assert browser._format_bucket_duration(30) == "30s"
        assert browser._format_bucket_duration(45) == "45s"

    def test_format_bucket_duration_minutes(self) -> None:
        """Test bucket duration formatting for minutes."""
        browser = SessionBrowser()

        assert browser._format_bucket_duration(60) == "1min"
        assert browser._format_bucket_duration(300) == "5min"
        assert browser._format_bucket_duration(900) == "15min"

    def test_format_bucket_duration_hours(self) -> None:
        """Test bucket duration formatting for hours."""
        browser = SessionBrowser()

        assert browser._format_bucket_duration(3600) == "1hr"
        assert browser._format_bucket_duration(7200) == "2hr"


# ============================================================================
# Timeline Mode Integration Tests
# ============================================================================


class TestTimelineModeIntegration:
    """Integration tests for timeline mode."""

    def test_browser_mode_enum_has_timeline(self) -> None:
        """Test that BrowserMode enum includes TIMELINE."""
        assert hasattr(BrowserMode, "TIMELINE")
        assert BrowserMode.TIMELINE.value is not None

    def test_handle_timeline_key_back(self) -> None:
        """Test that ESC returns to detail view."""
        browser = SessionBrowser()
        browser.state.mode = BrowserMode.TIMELINE
        browser._timeline_data = TimelineData(
            session_date=date.today(),
            duration_seconds=300.0,
            bucket_duration_seconds=60.0,
        )
        browser._detail_data = {"session": {}}

        result = browser._handle_timeline_key("\x1b")  # ESC

        assert result is False  # Don't exit
        assert browser.state.mode == BrowserMode.DETAIL
        assert browser._timeline_data is None

    def test_open_timeline_view_requires_detail_data(self) -> None:
        """Test that opening timeline requires detail data."""
        browser = SessionBrowser()
        browser._detail_data = None

        browser._open_timeline_view()

        assert browser.state.mode == BrowserMode.DASHBOARD  # Unchanged (v1.0.0 default)
        assert browser._timeline_data is None
