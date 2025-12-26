# API Reference

Token Audit is primarily a CLI tool. This document covers programmatic usage for advanced integrations.

> **Stability Policy (v0.9.0+):** All APIs now have explicit stability tiers. See [api-stability.md](api-stability.md) for the full policy, deprecation timeline, and migration guides.

## Stability Tiers

| Tier | Meaning |
|------|---------|
| **Stable** | Guaranteed backward compatible through v1.x |
| **Evolving** | Interface stable, implementation may change |
| **Deprecated** | Scheduled for removal, use alternative |

---

## Quick Start

### Loading Sessions

```python
from token_audit.storage import StorageManager

# Initialize storage manager
storage = StorageManager()

# List all Claude Code sessions
sessions = storage.list_sessions(platform="claude_code")

for session in sessions:
    print(f"{session.session_id}: {session.total_tokens} tokens")
```

### Loading a Specific Session

```python
from token_audit.storage import load_session_file
from pathlib import Path

session_path = Path("~/.token-audit/sessions/claude_code/2025-01-15/session-abc123.json")
session_data = load_session_file(session_path.expanduser())

if session_data:
    print(f"Total tokens: {session_data['token_usage']['total']}")
    print(f"Cost: ${session_data['cost']['total_usd']:.4f}")
```

---

## Key Classes

### StorageManager `[Stable]`

Manages session storage and indexing.

```python
from token_audit.storage import StorageManager

storage = StorageManager(base_dir="~/.token-audit")
```

**Methods:**

| Method | Description |
|--------|-------------|
| `list_sessions(platform=None)` | List sessions, optionally filtered by platform |
| `get_session(session_id)` | Get a specific session by ID |
| `query_sessions(start_date=None, end_date=None)` | Query sessions by date range |

**Platform values:** `"claude_code"`, `"codex_cli"`, `"gemini_cli"`, `"ollama_cli"`, `"custom"`

### SessionIndex `[Stable]`

Lightweight session entry for efficient queries.

```python
from token_audit.storage import SessionIndex

# SessionIndex fields
session.session_id       # Unique identifier
session.platform         # Platform name
session.project          # Project name
session.start_time       # Session start (datetime)
session.end_time         # Session end (datetime)
session.total_tokens     # Total token count
session.total_cost       # Estimated cost (USD)
session.model            # Primary model used
```

---

## Example: Custom Report Generator

Generate a custom weekly report:

```python
from token_audit.storage import StorageManager
from datetime import datetime, timedelta

def weekly_report():
    storage = StorageManager()

    # Get sessions from last 7 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    sessions = storage.query_sessions(
        start_date=start_date,
        end_date=end_date
    )

    # Aggregate stats
    total_tokens = sum(s.total_tokens for s in sessions)
    total_cost = sum(s.total_cost for s in sessions)

    print(f"Weekly Summary ({start_date.date()} to {end_date.date()})")
    print(f"  Sessions: {len(sessions)}")
    print(f"  Tokens: {total_tokens:,}")
    print(f"  Cost: ${total_cost:.2f}")

    # By platform
    by_platform = {}
    for s in sessions:
        by_platform.setdefault(s.platform, []).append(s)

    for platform, platform_sessions in by_platform.items():
        platform_cost = sum(s.total_cost for s in platform_sessions)
        print(f"  {platform}: ${platform_cost:.2f}")

if __name__ == "__main__":
    weekly_report()
```

---

## Example: CI/CD Integration

Check session cost against a threshold:

```python
#!/usr/bin/env python3
"""CI script to check session costs against budget."""

import sys
from token_audit.storage import get_latest_session, load_session_file

MAX_COST_USD = 1.00  # Budget per session

def check_session_cost():
    session_path = get_latest_session()

    if not session_path:
        print("No sessions found")
        sys.exit(0)

    session = load_session_file(session_path)

    if not session:
        print(f"Could not load session: {session_path}")
        sys.exit(1)

    cost = session.get("cost", {}).get("total_usd", 0)

    print(f"Session cost: ${cost:.4f}")
    print(f"Budget: ${MAX_COST_USD:.2f}")

    if cost > MAX_COST_USD:
        print(f"FAILED: Cost ${cost:.4f} exceeds budget ${MAX_COST_USD:.2f}")
        sys.exit(1)
    else:
        print("PASSED: Within budget")
        sys.exit(0)

if __name__ == "__main__":
    check_session_cost()
```

Usage in GitHub Actions:

```yaml
- name: Check Token Audit costs
  run: python scripts/check_session_cost.py
```

---

## Example: Smell Analysis

Analyze smells across sessions:

```python
from token_audit.storage import StorageManager, load_session_file
from collections import Counter

def analyze_smells():
    storage = StorageManager()
    sessions = storage.list_sessions()

    smell_counts = Counter()

    for session_index in sessions:
        # Load full session data
        session_path = storage.get_session_path(session_index.session_id)
        session = load_session_file(session_path)

        if session and "smells" in session:
            for smell in session["smells"]:
                smell_counts[smell["pattern"]] += 1

    print("Smell frequency across all sessions:")
    for pattern, count in smell_counts.most_common():
        print(f"  {pattern}: {count}")

if __name__ == "__main__":
    analyze_smells()
```

---

## Session Data Format

Sessions are stored as JSON. Key fields:

```python
{
    "schema_version": "1.7.0",
    "session_id": "abc123",
    "platform": "claude_code",
    "project": "my-project",

    "token_usage": {
        "input": 45231,
        "output": 12345,
        "cache_created": 0,
        "cache_read": 125000,
        "total": 182576
    },

    "cost": {
        "total_usd": 0.42,
        "input_cost": 0.30,
        "output_cost": 0.12
    },

    "mcp_servers": {
        "zen": {
            "calls": 28,
            "tokens": 234000
        }
    },

    "smells": [
        {
            "pattern": "CHATTY",
            "severity": "warning",
            "tool": "mcp__zen__chat",
            "description": "Called 25 times"
        }
    ],

    "recommendations": [
        {
            "type": "BATCH_OPERATIONS",
            "confidence": 0.85,
            "evidence_summary": "..."
        }
    ]
}
```

See [Data Contract](data-contract.md) for the complete schema specification.

---

## Importing Modules

Available imports by stability tier:

```python
# === STABLE APIs ===
# Storage
from token_audit import StorageManager, SessionIndex

# Pricing
from token_audit import PricingConfig, load_pricing_config, get_model_cost

# Normalization
from token_audit import normalize_tool_name, normalize_server_name

# Token estimation
from token_audit import TokenEstimator, count_tokens, get_estimator_for_platform

# Display
from token_audit import DisplayAdapter, DisplaySnapshot, create_display

# API stability helpers
from token_audit import get_api_stability, API_STABILITY

# === EVOLVING APIs ===
# Data classes
from token_audit import Session, Call, TokenUsage, MCPToolCalls

# Platform adapters
from token_audit import ClaudeCodeAdapter, CodexCLIAdapter, GeminiCLIAdapter

# Smell analysis
from token_audit import SmellAggregator

# === DEPRECATED (remove in v1.1.0) ===
# from token_audit import estimate_tool_tokens  # Use TokenEstimator instead
```

---

## Stability Commitment

| Component | Tier | Notes |
|-----------|------|-------|
| **CLI** | Stable | Breaking changes require major version |
| **Session JSON format** | Stable | Backward compatible with schema_version |
| **Stable Python APIs** | Stable | 16 exports guaranteed through v1.x |
| **Evolving Python APIs** | Evolving | Interface stable, implementation may change |

For maximum stability:
1. Use CLI with `--format json` output
2. Parse session JSON files directly
3. Use only Stable-tier Python APIs
4. Check `get_api_stability()` before depending on an API

---

*For CLI usage, see [Getting Started](getting-started.md). For session format details, see [Data Contract](data-contract.md).*
