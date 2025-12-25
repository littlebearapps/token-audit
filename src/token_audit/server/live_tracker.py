"""
Live session tracking with JSONL streaming.

This module provides real-time session tracking that writes incrementally
to JSONL files, enabling AI agents to query live metrics during a session.

Event Types:
- session_start: Written when tracking begins
- tool_call: Written for each MCP tool invocation
- smell_detected: Written when an efficiency issue is detected
- session_end: Written when tracking stops

The tracker maintains both:
1. In-memory metrics (for fast get_metrics queries)
2. JSONL file (for persistence and recovery)
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from token_audit.base_tracker import SCHEMA_VERSION
from token_audit.storage import Platform, StreamingStorage


@dataclass
class LiveSession:
    """
    Represents an active tracking session.

    Stores in-memory metrics that can be queried via get_metrics tool.
    The session data is also persisted to JSONL for durability.
    """

    session_id: str
    platform: str
    project: Optional[str]
    started_at: datetime
    file_path: Optional[Path] = None
    ended_at: Optional[datetime] = None

    # Metrics (updated as events are tracked)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0
    tool_calls: Dict[str, int] = field(default_factory=dict)
    server_calls: Dict[str, int] = field(default_factory=dict)
    model_usage: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    smells: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "platform": self.platform,
            "project": self.project,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "file_path": str(self.file_path) if self.file_path else None,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_write_tokens": self.total_cache_write_tokens,
            "total_cost_usd": self.total_cost_usd,
            "call_count": self.call_count,
            "tool_calls": self.tool_calls,
            "server_calls": self.server_calls,
            "model_usage": self.model_usage,
            "smells": self.smells,
        }


class LiveTracker:
    """
    Manages live session tracking with JSONL streaming writes.

    The tracker provides:
    - Incremental JSONL writes for each event (tool_call, smell_detected)
    - In-memory metrics for fast queries
    - Graceful completion with JSONL → JSON conversion

    Thread Safety:
        All public methods are thread-safe via internal locking.
    """

    def __init__(self, storage: Optional[StreamingStorage] = None) -> None:
        """
        Initialize the live tracker.

        Args:
            storage: StreamingStorage instance for persistence.
                     Creates a new instance if not provided.
        """
        self._storage = storage or StreamingStorage()
        self._active_session: Optional[LiveSession] = None
        self._lock = threading.Lock()

    @property
    def active_session(self) -> Optional[LiveSession]:
        """Get the currently active session, if any."""
        with self._lock:
            return self._active_session

    @property
    def has_active_session(self) -> bool:
        """Check if there is an active tracking session."""
        with self._lock:
            return self._active_session is not None

    def start_session(
        self,
        platform: str,
        project: Optional[str] = None,
    ) -> LiveSession:
        """
        Start a new tracking session.

        Creates an active session file and writes the session_start event.

        Args:
            platform: The platform being tracked (claude_code, codex_cli, etc.)
            project: Optional project name for grouping

        Returns:
            The newly created LiveSession

        Raises:
            RuntimeError: If a session is already active
        """
        with self._lock:
            if self._active_session is not None:
                raise RuntimeError(
                    f"Session already active: {self._active_session.session_id}. "
                    "Call stop_session() first."
                )

            # Generate short ID for readability
            session_id = str(uuid.uuid4())[:8]

            # Create session file
            file_path = self._storage.create_active_session(session_id)

            # Create session object
            session = LiveSession(
                session_id=session_id,
                platform=platform,
                project=project,
                started_at=datetime.now(),
                file_path=file_path,
            )

            # Write session_start event
            start_event = {
                "type": "session_start",
                "timestamp": session.started_at.isoformat(),
                "session_id": session_id,
                "platform": platform,
                "project": project,
            }
            self._storage.append_event(session_id, start_event)

            self._active_session = session
            return session

    def stop_session(self) -> Optional[LiveSession]:
        """
        Stop the active session and persist it.

        Writes the session_end event, converts JSONL to JSON, and moves
        the session to the completed directory.

        Returns:
            The stopped session, or None if no session was active
        """
        with self._lock:
            if self._active_session is None:
                return None

            session = self._active_session
            session.ended_at = datetime.now()

            # Write session_end event
            end_event = {
                "type": "session_end",
                "timestamp": session.ended_at.isoformat(),
                "total_input_tokens": session.total_input_tokens,
                "total_output_tokens": session.total_output_tokens,
                "total_cache_read_tokens": session.total_cache_read_tokens,
                "total_cache_write_tokens": session.total_cache_write_tokens,
                "total_cost_usd": session.total_cost_usd,
                "call_count": session.call_count,
            }
            self._storage.append_event(session.session_id, end_event)

            # Build final session data
            final_data = self._build_final_session_data(session)

            # Move to completed directory
            platform_typed: Platform = session.platform  # type: ignore
            completed_path = self._storage.move_to_complete(
                session_id=session.session_id,
                platform=platform_typed,
                session_date=session.started_at.date(),
                final_data=final_data,
            )
            session.file_path = completed_path

            self._active_session = None
            return session

    def _build_final_session_data(self, session: LiveSession) -> Dict[str, Any]:
        """Build the final session data for JSON persistence."""
        # Load all events from JSONL
        events = self._storage.load_all_events(session.session_id)

        return {
            "_file": {
                "schema_version": SCHEMA_VERSION,
                "created_at": datetime.now().isoformat(),
                "source": "token-audit-server",
            },
            "session_id": session.session_id,
            "platform": session.platform,
            "project": session.project,
            "started_at": session.started_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "token_usage": {
                "input_tokens": session.total_input_tokens,
                "output_tokens": session.total_output_tokens,
                "cache_read_tokens": session.total_cache_read_tokens,
                "cache_write_tokens": session.total_cache_write_tokens,
                "total_tokens": (
                    session.total_input_tokens
                    + session.total_output_tokens
                    + session.total_cache_read_tokens
                ),
            },
            "cost_usd": session.total_cost_usd,
            "call_count": session.call_count,
            "tool_calls": session.tool_calls,
            "server_calls": session.server_calls,
            "model_usage": session.model_usage,
            "smells": session.smells,
            "events": events,
        }

    def get_session(self, session_id: Optional[str] = None) -> Optional[LiveSession]:
        """
        Get a session by ID or the active session.

        Args:
            session_id: Session ID to retrieve, or None for active session

        Returns:
            The requested session, or None if not found
        """
        with self._lock:
            if session_id is None:
                return self._active_session

            if self._active_session and self._active_session.session_id == session_id:
                return self._active_session

            # Note: Looking up completed sessions is not supported in v1.0
            # This would require loading from JSON files
            return None

    def append_event(self, event: Dict[str, Any]) -> None:
        """
        Append a raw event to the active session's JSONL file.

        Low-level method for direct event writing. Prefer using
        record_tool_call() or record_smell() for structured events.

        Args:
            event: Event data to append

        Raises:
            RuntimeError: If no session is active
        """
        with self._lock:
            if self._active_session is None:
                raise RuntimeError("No active session. Call start_session() first.")

            # Ensure timestamp is present
            if "timestamp" not in event:
                event["timestamp"] = datetime.now().isoformat()

            self._storage.append_event(self._active_session.session_id, event)

    def record_tool_call(
        self,
        tool: str,
        server: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cache_read: int = 0,
        cache_write: int = 0,
        duration_ms: int = 0,
        success: bool = True,
        model: Optional[str] = None,
        cost_usd: float = 0.0,
        **kwargs: Any,
    ) -> None:
        """
        Record a tool call event.

        Updates both in-memory metrics and JSONL file.

        Args:
            tool: Tool name (e.g., "Read", "mcp__zen__chat")
            server: Server name (e.g., "builtin", "zen")
            tokens_in: Input tokens consumed
            tokens_out: Output tokens generated
            cache_read: Tokens read from cache
            cache_write: Tokens written to cache
            duration_ms: Call duration in milliseconds
            success: Whether the call succeeded
            model: Model used (if applicable)
            cost_usd: Cost of this call in USD
            **kwargs: Additional event data
        """
        with self._lock:
            if self._active_session is None:
                raise RuntimeError("No active session. Call start_session() first.")

            session = self._active_session
            timestamp = datetime.now()

            # Build event
            event = {
                "type": "tool_call",
                "timestamp": timestamp.isoformat(),
                "tool": tool,
                "server": server,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cache_read": cache_read,
                "cache_write": cache_write,
                "duration_ms": duration_ms,
                "success": success,
                **kwargs,
            }
            if model:
                event["model"] = model

            # Write to JSONL
            self._storage.append_event(session.session_id, event)

            # Update in-memory metrics
            session.total_input_tokens += tokens_in
            session.total_output_tokens += tokens_out
            session.total_cache_read_tokens += cache_read
            session.total_cache_write_tokens += cache_write
            session.total_cost_usd += cost_usd
            session.call_count += 1

            # Track per-tool calls
            session.tool_calls[tool] = session.tool_calls.get(tool, 0) + 1

            # Track per-server calls
            session.server_calls[server] = session.server_calls.get(server, 0) + 1

            # Track per-model usage
            if model:
                if model not in session.model_usage:
                    session.model_usage[model] = {
                        "tokens_in": 0,
                        "tokens_out": 0,
                        "cache_read": 0,
                        "cache_write": 0,
                        "calls": 0,
                        "cost_usd": 0.0,
                    }
                session.model_usage[model]["tokens_in"] += tokens_in
                session.model_usage[model]["tokens_out"] += tokens_out
                session.model_usage[model]["cache_read"] += cache_read
                session.model_usage[model]["cache_write"] += cache_write
                session.model_usage[model]["calls"] += 1
                session.model_usage[model]["cost_usd"] += cost_usd

    def record_smell(
        self,
        pattern: str,
        severity: str,
        tool: Optional[str] = None,
        description: str = "",
        **evidence: Any,
    ) -> None:
        """
        Record a smell detection event.

        Updates both in-memory metrics and JSONL file.

        Args:
            pattern: Smell pattern identifier (e.g., "CHATTY", "LOW_CACHE_HIT")
            severity: Severity level ("critical", "high", "medium", "low", "info")
            tool: Tool involved (if applicable)
            description: Human-readable description
            **evidence: Additional evidence data
        """
        with self._lock:
            if self._active_session is None:
                raise RuntimeError("No active session. Call start_session() first.")

            session = self._active_session
            timestamp = datetime.now()

            # Build event
            event: Dict[str, Any] = {
                "type": "smell_detected",
                "timestamp": timestamp.isoformat(),
                "pattern": pattern,
                "severity": severity,
                "description": description,
            }
            if tool:
                event["tool"] = tool
            if evidence:
                event["evidence"] = evidence

            # Write to JSONL
            self._storage.append_event(session.session_id, event)

            # Add to in-memory smells list
            smell_record: Dict[str, Any] = {
                "pattern": pattern,
                "severity": severity,
                "tool": tool,
                "description": description,
                "timestamp": timestamp.isoformat(),
            }
            if evidence:
                smell_record["evidence"] = evidence
            session.smells.append(smell_record)

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics from the active session.

        Returns metrics from in-memory state for speed.

        Returns:
            Dictionary with current session metrics

        Raises:
            RuntimeError: If no session is active
        """
        with self._lock:
            if self._active_session is None:
                raise RuntimeError("No active session. Call start_session() first.")

            session = self._active_session
            now = datetime.now()
            duration_seconds = (now - session.started_at).total_seconds()
            duration_minutes = duration_seconds / 60.0

            total_tokens = (
                session.total_input_tokens
                + session.total_output_tokens
                + session.total_cache_read_tokens
            )

            # Calculate rates
            tokens_per_min = total_tokens / duration_minutes if duration_minutes > 0 else 0.0
            calls_per_min = session.call_count / duration_minutes if duration_minutes > 0 else 0.0

            # Calculate cache hit ratio
            total_input = session.total_input_tokens + session.total_cache_read_tokens
            cache_hit_ratio = (
                session.total_cache_read_tokens / total_input if total_input > 0 else 0.0
            )

            return {
                "session_id": session.session_id,
                "platform": session.platform,
                "project": session.project,
                "started_at": session.started_at.isoformat(),
                "duration_minutes": round(duration_minutes, 2),
                "tokens": {
                    "input": session.total_input_tokens,
                    "output": session.total_output_tokens,
                    "cache_read": session.total_cache_read_tokens,
                    "cache_write": session.total_cache_write_tokens,
                    "total": total_tokens,
                },
                "cost_usd": round(session.total_cost_usd, 4),
                "rates": {
                    "tokens_per_min": round(tokens_per_min, 2),
                    "calls_per_min": round(calls_per_min, 2),
                },
                "cache": {
                    "hit_ratio": round(cache_hit_ratio, 3),
                    "savings_tokens": session.total_cache_read_tokens,
                },
                "call_count": session.call_count,
                "tool_count": len(session.tool_calls),
                "tool_calls": session.tool_calls,
                "server_calls": session.server_calls,
                "model_usage": session.model_usage,
                "smells": session.smells,
            }

    def cleanup(self) -> None:
        """
        Clean up the active session without completing it.

        Use this for error recovery. The session data will be lost.
        """
        with self._lock:
            if self._active_session is not None:
                self._storage.cleanup_active_session(self._active_session.session_id)
                self._active_session = None
