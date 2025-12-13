# MCP Audit Architecture

**Version**: 1.0.0
**Last Updated**: 2025-12-13

This document describes the internal architecture of MCP Audit, including the storage system, data schemas, and platform adapter interface.

---

## Table of Contents

1. [Overview](#overview)
2. [Storage Architecture](#storage-architecture)
3. [Core Data Model](#core-data-model)
4. [BaseTracker Abstraction](#basetracker-abstraction)
5. [Platform Adapter Interface](#platform-adapter-interface)
6. [Event Schema](#event-schema)
7. [Optional Dependencies](#optional-dependencies)
8. [Migration Guide](#migration-guide)

---

## Overview

MCP Audit is designed with three core principles:

1. **Platform-Agnostic**: Works with any MCP-enabled CLI tool
2. **Privacy-First**: No raw prompts/responses stored by default
3. **Extensible**: Easy to add new platform adapters

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Interface                          │
│                   (mcp-audit collect/report)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     BaseTracker                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │   Session   │ │  Recording  │ │  Duplicate          │   │
│  │  Lifecycle  │ │   APIs      │ │  Detection          │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Claude Code    │ │   Codex CLI     │ │   Gemini CLI    │
│    Adapter      │ │    Adapter      │ │    Adapter      │
└─────────────────┘ └─────────────────┘ └─────────────────┘
              │               │               │
              ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                   Storage Manager                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │   JSONL     │ │   Index     │ │   Migration         │   │
│  │   Files     │ │   System    │ │   Helpers           │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Storage Architecture

### Directory Structure

MCP Audit stores session data in a standardized directory structure:

```
~/.mcp-audit/
├── sessions/                          # All session data
│   ├── claude_code/                   # Claude Code sessions
│   │   ├── .index.json                # Platform-level index
│   │   ├── 2025-11-24/               # Date directory
│   │   │   ├── .index.json           # Daily index
│   │   │   ├── session-20251124T103045-a1b2c3.jsonl
│   │   │   └── session-20251124T143022-d4e5f6.jsonl
│   │   └── 2025-11-25/
│   │       └── ...
│   ├── codex_cli/                     # Codex CLI sessions
│   │   └── ...
│   ├── gemini_cli/                    # Gemini CLI sessions
│   │   └── ...
│   ├── ollama_cli/                    # Ollama CLI sessions
│   │   └── ...
│   └── custom/                        # Custom platform sessions
│       └── ...
└── config/
    └── mcp-audit.toml               # User configuration
```

### Session File Format

Each session is stored as a **JSONL (JSON Lines)** file with one event per line:

```
~/.mcp-audit/sessions/<platform>/<YYYY-MM-DD>/<session-id>.jsonl
```

**Example**: `~/.mcp-audit/sessions/claude_code/2025-11-25/session-20251125T103045-a1b2c3.jsonl`

**JSONL Format** (one JSON object per line):

```jsonl
{"type":"session_start","timestamp":"2025-11-25T10:30:45","platform":"claude_code","project":"my-project"}
{"type":"tool_call","timestamp":"2025-11-25T10:31:00","tool":"mcp__zen__chat","input_tokens":500,"output_tokens":200}
{"type":"tool_call","timestamp":"2025-11-25T10:32:15","tool":"mcp__brave-search__web","input_tokens":300,"output_tokens":1000}
{"type":"session_end","timestamp":"2025-11-25T11:00:00","total_tokens":2000,"cost_estimate":0.10}
```

**Why JSONL?**
- Append-only writes (safe for crashes)
- Memory-efficient streaming reads
- Human-readable for debugging
- Standard format with wide tool support

### Session ID Format

Session IDs follow a predictable format:

```
session-{YYYYMMDD}T{HHMMSS}-{random}
```

**Example**: `session-20251125T103045-a1b2c3`

- **Timestamp**: When session started (local time)
- **Random**: 6 hex characters for uniqueness

### Index Files

Index files enable fast cross-session queries without parsing every JSONL file.

#### Daily Index (`.index.json`)

Located at: `<platform>/<YYYY-MM-DD>/.index.json`

```json
{
  "schema_version": "1.0.0",
  "platform": "claude_code",
  "date": "2025-11-25",
  "sessions": [
    {
      "session_id": "session-20251125T103045-a1b2c3",
      "started_at": "2025-11-25T10:30:45",
      "ended_at": "2025-11-25T11:00:00",
      "project": "my-project",
      "total_tokens": 2000,
      "total_cost": 0.10,
      "tool_count": 5,
      "server_count": 2,
      "is_complete": true,
      "file_path": "claude_code/2025-11-25/session-20251125T103045-a1b2c3.jsonl",
      "file_size_bytes": 4096
    }
  ],
  "total_tokens": 2000,
  "total_cost": 0.10,
  "session_count": 1,
  "last_updated": "2025-11-25T11:00:05"
}
```

#### Platform Index (`.index.json`)

Located at: `<platform>/.index.json`

```json
{
  "schema_version": "1.0.0",
  "platform": "claude_code",
  "dates": ["2025-11-24", "2025-11-25"],
  "total_sessions": 5,
  "total_tokens": 50000,
  "total_cost": 2.50,
  "first_session_date": "2025-11-24",
  "last_session_date": "2025-11-25",
  "last_updated": "2025-11-25T11:00:05"
}
```

### Supported Platforms

| Platform | Directory | Status |
|----------|-----------|--------|
| Claude Code | `claude_code/` | ✅ Stable |
| Codex CLI | `codex_cli/` | ✅ Stable |
| Gemini CLI | `gemini_cli/` | ✅ Stable |
| Ollama CLI | `ollama_cli/` | ⏳ Experimental |
| Custom | `custom/` | ✅ Available |

---

## Core Data Model

### Session

Top-level container for tracking data. See [CORE-SCHEMA-SPEC.md](CORE-SCHEMA-SPEC.md) for full specification.

```python
@dataclass
class Session:
    schema_version: str          # "1.0.0"
    session_id: str              # Unique identifier
    platform: str                # "claude_code", "codex_cli", etc.
    project: str                 # Project name
    timestamp: datetime          # Start time
    end_timestamp: datetime      # End time (if complete)

    token_usage: TokenUsage      # Aggregate token stats
    cost_estimate: float         # Estimated cost in USD
    mcp_tool_calls: MCPToolCalls # MCP tool statistics
    server_sessions: Dict[str, ServerSession]  # Per-server data

    redundancy_analysis: Optional[RedundancyAnalysis]
    anomalies: List[Anomaly]
```

### Call

Individual tool call record with token/timing data.

```python
@dataclass
class Call:
    schema_version: str          # "1.0.0"
    timestamp: datetime          # When call occurred
    tool_name: str               # Normalized tool name

    input_tokens: int            # Tokens sent to model
    output_tokens: int           # Tokens received
    cache_created_tokens: int    # Cache tokens created
    cache_read_tokens: int       # Cache tokens read
    total_tokens: int            # Sum of all tokens

    duration_ms: Optional[int]   # Call duration (for time-based tracking)
    content_hash: Optional[str]  # For duplicate detection
    platform_data: Optional[dict]  # Platform-specific metadata
```

### ServerSession

Per-server aggregation of tool statistics.

```python
@dataclass
class ServerSession:
    schema_version: str
    server: str                  # Server name (e.g., "zen", "brave-search")
    tools: Dict[str, ToolStats]  # Per-tool statistics
    total_calls: int
    total_tokens: int
    metadata: Optional[dict]
```

---

## BaseTracker Abstraction

The `BaseTracker` class provides the core tracking logic that all platform adapters inherit.

### Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Session Lifecycle** | Start/stop sessions, manage timestamps |
| **Recording API** | `record_tool_call()`, `record_model_call()` |
| **Normalization** | Server name and tool name normalization |
| **Duplicate Detection** | Content hashing, redundancy analysis |
| **Persistence** | Save sessions via StorageManager |
| **Signal Handling** | Graceful Ctrl+C handling |

### Key Methods

```python
class BaseTracker(ABC):
    """Abstract base class for platform-specific trackers."""

    # Lifecycle
    def start_session(self, project: str) -> str: ...
    def finalize_session(self) -> Session: ...

    # Recording
    def record_tool_call(
        self,
        tool_name: str,
        input_tokens: int,
        output_tokens: int,
        cache_created: int = 0,
        cache_read: int = 0,
        duration_ms: Optional[int] = None,
        content_hash: Optional[str] = None,
    ) -> None: ...

    # Normalization (static)
    @staticmethod
    def normalize_server_name(tool_name: str) -> str: ...

    @staticmethod
    def normalize_tool_name(tool_name: str) -> str: ...

    # Abstract methods (must implement)
    @abstractmethod
    def start_tracking(self) -> None: ...

    @abstractmethod
    def parse_event(self, raw_event: Any) -> Optional[dict]: ...

    @abstractmethod
    def get_platform_metadata(self) -> dict: ...
```

### Inheritance Hierarchy

```
BaseTracker (abstract)
├── ClaudeCodeAdapter    # File watcher (debug.log)
├── CodexCLIAdapter      # File watcher (session JSONL)
├── GeminiCLIAdapter     # File watcher (session JSON)
└── OllamaCliAdapter     # Process wrapper (stdout)
```

---

## Platform Adapter Interface

Each platform adapter must implement the abstract methods from `BaseTracker`.

### Required Methods

```python
class MyPlatformAdapter(BaseTracker):
    """Adapter for MyPlatform CLI."""

    def __init__(self):
        super().__init__(platform="my_platform")

    def start_tracking(self) -> None:
        """
        Start monitoring the platform for events.

        Implementations:
        - File watcher: Monitor log files
        - Process wrapper: Capture stdout/stderr
        - API polling: Query platform APIs
        """
        pass

    def parse_event(self, raw_event: Any) -> Optional[dict]:
        """
        Parse raw platform event into normalized format.

        Returns:
            dict with keys: tool_name, input_tokens, output_tokens, etc.
            None if event should be ignored
        """
        pass

    def get_platform_metadata(self) -> dict:
        """
        Return platform-specific metadata.

        Examples: model version, CLI args, working directory
        """
        return {
            "version": "1.0.0",
            "cli_args": sys.argv[1:],
        }
```

### Interception Mechanisms

Different platforms require different interception approaches:

| Platform | Mechanism | Details |
|----------|-----------|---------|
| Claude Code | File Watcher | Monitor `~/.claude/cache/*/debug.log` |
| Codex CLI | File Watcher | Parse `~/.codex/sessions/YYYY/MM/DD/*.jsonl` |
| Gemini CLI | File Watcher | Parse `~/.gemini/tmp/<hash>/chats/session-*.json` |
| Ollama CLI | Process Wrapper | Capture stdout with timing |

See [INTERCEPTION-MECHANISM-SPEC.md](INTERCEPTION-MECHANISM-SPEC.md) for detailed specifications.

### Tool Name Normalization

All adapters use shared normalization to ensure consistent tool names:

```python
# Input variations
"mcp__zen-mcp__chat"      # Codex format
"mcp__zen__chat"          # Claude Code format
"zen.chat"                # Alternative format

# Normalized output
"mcp__zen__chat"          # Consistent format

# Server extraction
server = normalize_server_name("mcp__zen__chat")  # "zen"
```

---

## Event Schema

### Event Types

The JSONL files contain events of the following types:

#### session_start

```json
{
  "type": "session_start",
  "timestamp": "2025-11-25T10:30:45",
  "schema_version": "1.0.0",
  "platform": "claude_code",
  "project": "my-project",
  "metadata": {
    "model": "claude-sonnet-4",
    "working_dir": "/path/to/project"
  }
}
```

#### tool_call

```json
{
  "type": "tool_call",
  "timestamp": "2025-11-25T10:31:00",
  "tool_name": "mcp__zen__chat",
  "server": "zen",
  "input_tokens": 500,
  "output_tokens": 200,
  "cache_created_tokens": 0,
  "cache_read_tokens": 100,
  "total_tokens": 800,
  "duration_ms": 1500,
  "content_hash": "abc123"
}
```

#### model_call

```json
{
  "type": "model_call",
  "timestamp": "2025-11-25T10:30:50",
  "model": "claude-sonnet-4",
  "input_tokens": 1000,
  "output_tokens": 500,
  "cache_read_tokens": 2000
}
```

#### session_end

```json
{
  "type": "session_end",
  "timestamp": "2025-11-25T11:00:00",
  "total_tokens": 50000,
  "total_cost": 0.25,
  "tool_count": 15,
  "duration_seconds": 1800,
  "summary": {
    "top_tools": ["mcp__zen__chat", "mcp__brave-search__web"],
    "warnings": []
  }
}
```

#### unrecognized

For graceful degradation when encountering unknown formats:

```json
{
  "type": "unrecognized",
  "timestamp": "2025-11-25T10:35:00",
  "raw_content": "...",
  "reason": "Unknown event format"
}
```

---

## Optional Dependencies

MCP Audit uses optional dependency groups for extended functionality:

### Installation Options

```bash
# Core only (minimal dependencies)
pip install mcp-audit

# With analytics (pandas, numpy)
pip install mcp-audit[analytics]

# With visualization (matplotlib, plotly)
pip install mcp-audit[viz]

# With export formats (openpyxl, tabulate)
pip install mcp-audit[export]

# Everything
pip install mcp-audit[all]
```

### Dependency Groups

| Group | Dependencies | Features |
|-------|-------------|----------|
| `[analytics]` | pandas, numpy | DataFrame analysis, statistics |
| `[viz]` | matplotlib, plotly | Charts, graphs, HTML reports |
| `[export]` | openpyxl, tabulate | Excel, formatted tables |
| `[all]` | All of the above | Full feature set |

### Configuration in pyproject.toml

```toml
[project.optional-dependencies]
analytics = ["pandas>=2.0.0", "numpy>=1.24.0"]
viz = ["matplotlib>=3.7.0", "plotly>=5.15.0"]
export = ["openpyxl>=3.1.0", "tabulate>=0.9.0"]
all = ["mcp-audit[analytics,viz,export]"]
```

### Feature Detection

```python
from mcp_audit.utils import has_analytics, has_viz

if has_analytics():
    import pandas as pd
    df = pd.DataFrame(sessions)
else:
    # Fallback to built-in analysis
    pass
```

---

## Migration Guide

### v0.x to v1.x Migration

The storage format changed significantly between v0.x and v1.x:

| Aspect | v0.x | v1.x |
|--------|------|------|
| Location | `logs/sessions/` (project-relative) | `~/.mcp-audit/sessions/` (global) |
| Structure | `{project}-{timestamp}/` | `<platform>/<date>/<session-id>.jsonl` |
| Files | Multiple JSON files | Single JSONL file |
| Indexes | None | Daily + Platform indexes |

### Automatic Migration

```bash
# Migrate all sessions from v0.x location
mcp-audit migrate --from logs/sessions/ --platform claude-code

# Dry run (preview without changes)
mcp-audit migrate --from logs/sessions/ --dry-run
```

### Programmatic Migration

```python
from storage import StorageManager, migrate_all_v0_sessions
from pathlib import Path

# Create v1.x storage
storage = StorageManager()

# Migrate v0.x sessions
results = migrate_all_v0_sessions(
    v0_base_dir=Path("logs/sessions"),
    storage=storage,
    platform="claude_code"
)

print(f"Migrated: {results['migrated']}")
print(f"Failed: {results['failed']}")
```

### What Gets Migrated

- ✅ Event stream (`events.jsonl`)
- ✅ Session metadata (from `summary.json`)
- ✅ Index entries (regenerated)
- ⚠️ Per-server files (`mcp-*.json`) - Data extracted, not copied verbatim

### Backward Compatibility

MCP Audit v1.x can read v0.x session data but stores new sessions in v1.x format only.

---

## See Also

- [CORE-SCHEMA-SPEC.md](CORE-SCHEMA-SPEC.md) - Detailed schema specification
- [INTERCEPTION-MECHANISM-SPEC.md](INTERCEPTION-MECHANISM-SPEC.md) - Platform interception details
- [PRICING-CONFIGURATION.md](PRICING-CONFIGURATION.md) - Cost calculation setup
- [contributing.md](contributing.md) - How to add new platform adapters
