# Token Audit Implementation Plan

**Version**: 1.0.0
**Last Updated**: 2025-12-24

---

## Executive Summary

Evolve token-audit into a cross-agent token audit tool with historical reporting (daily/weekly/monthly views). This plan covers v1.0.0 scope only.

**v1.0.0 Deliverables**:
- Aggregation engine with comprehensive tests
- CLI commands (daily, weekly, monthly)
- Documentation

**Explicitly NOT in v1.0.0**: TUI views (deferred to v1.1.0)

---

## Current State (token-audit v0.9.1)

### Existing Infrastructure

**Storage Layer** (`storage.py:85-170`):
- `DailyIndex` dataclass with session aggregates
- `PlatformIndex` dataclass with date ranges
- Directory structure: `~/.token-audit/sessions/<platform>/<YYYY-MM-DD>/<session>.jsonl`
- Index files already track `total_tokens`, `total_cost`, `session_count`

**Data Structures** (`base_tracker.py:191-212`):
- `TokenUsage` dataclass with input/output/cache/reasoning tokens
- `DataQuality` dataclass with accuracy_level, token_source, confidence
- Schema v1.7.0 with comprehensive token/cost tracking

**Token Sources**:
| Platform | Source | Accuracy | Notes |
|----------|--------|----------|-------|
| Claude Code | Native (debug.log) | Exact | From Anthropic API |
| Codex CLI | tiktoken o200k_base | ~95% | Estimated via tiktoken |
| Gemini CLI | sentencepiece gemma | ~90% | Estimated, requires download |

---

## Data Model

### DailyAggregate

```python
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class ModelUsage:
    """Token usage breakdown per model."""
    model: str
    input_tokens: int
    output_tokens: int
    cache_created_tokens: int
    cache_read_tokens: int
    total_tokens: int
    cost_micros: int  # Cost in microdollars (1/1,000,000 USD)
    call_count: int

@dataclass
class DailyAggregate:
    """Aggregated metrics for a single day."""
    date: str  # YYYY-MM-DD
    platform: str  # claude_code, codex_cli, gemini_cli

    # Token totals
    input_tokens: int = 0
    output_tokens: int = 0
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0

    # Cost in microdollars (avoids float precision issues)
    cost_micros: int = 0

    # Session info
    session_count: int = 0

    # Model breakdown (single source of truth)
    model_breakdowns: Dict[str, ModelUsage] = field(default_factory=dict)

    # Optional project breakdown
    project_breakdowns: Optional[Dict[str, 'ProjectAggregate']] = None

    @property
    def cost_usd(self) -> Decimal:
        """Cost in USD as Decimal."""
        return Decimal(self.cost_micros) / Decimal(1_000_000)
```

### Session Bucketing

Sessions are bucketed by their **start timestamp** (stored in `started_at` field):
- A session that starts at 23:50 and ends at 00:10 belongs to the start date only
- This matches how sessions are already stored in the directory structure

### Project Identification

Project is determined at **session write time** using this priority:
1. Git repository root path (if cwd is in a git repo)
2. Current working directory (cwd) as fallback

Stored in `SessionIndex.project` field (already exists in `storage.py:65`).

---

## PR Breakdown

### PR 1: Aggregation Engine + Tests ✅ (v1.0.0)

**Files to create/modify**:
- `src/token_audit/aggregation.py` (new)
- `tests/test_aggregation.py` (new)
- `src/token_audit/storage.py` (extend list_sessions for date ranges)

**New module `aggregation.py`**:
```python
def aggregate_daily(
    platform: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    group_by_project: bool = False
) -> List[DailyAggregate]:
    """Aggregate sessions by day."""

def aggregate_weekly(
    platform: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    start_of_week: int = 0  # 0=Monday, 6=Sunday
) -> List[WeeklyAggregate]:
    """Aggregate sessions by week."""

def aggregate_monthly(
    platform: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> List[MonthlyAggregate]:
    """Aggregate sessions by month."""
```

**Test coverage requirements**:
- Date range filtering
- Platform filtering
- Project grouping
- Cross-midnight session handling
- Empty date ranges
- Mixed platform aggregation
- Cost calculation accuracy (verify microdollars)

### PR 2: CLI Commands ✅ (v1.0.0)

**Files to modify**:
- `src/token_audit/cli.py`

**New commands**:
```bash
# Daily usage
token-audit daily [--platform PLATFORM] [--days N] [--json]
token-audit daily --instances  # Group by project

# Weekly usage
token-audit weekly [--platform PLATFORM] [--weeks N] [--json]
token-audit weekly --start-of-week monday|sunday

# Monthly usage
token-audit monthly [--platform PLATFORM] [--months N] [--json]
```

**Flags**:
- `--platform`: Filter to specific platform (claude-code, codex-cli, gemini-cli, all)
- `--days N` / `--weeks N` / `--months N`: Number of periods (default: 7/4/3)
- `--json`: Machine-readable JSON output (pipe to `jq` for filtering)
- `--instances`: Group by project (inspired by ccusage)
- `--breakdown`: Show per-model breakdown

**NOT implementing**: `--jq` flag - users can pipe to `jq` themselves

### PR 3: Documentation ✅ (v1.0.0)

**Files to create**:
- `docs/token-audit/README.md` - Product definition
- `docs/token-audit/capabilities-matrix.md` - Per-agent feature matrix
- `docs/token-audit/ccusage-notes.md` - Investigation findings
- `docs/token-audit/implementation-plan.md` - This plan
- `docs/token-audit/open-questions.md` - Unresolved items

### PR 4: TUI Historical Views (v1.1.0)

**Deferred to v1.1.0**. Will include:
- Daily/weekly/monthly view panels
- Keyboard shortcuts (d/w/m)
- Rich table formatting

---

## Key Design Decisions

### 1. Microdollars for Cost

Using `int` microdollars (1/1,000,000 USD) instead of `float`:
- Avoids floating-point precision issues in aggregation
- Standard practice in billing systems
- `cost_usd` property provides `Decimal` when needed

### 2. Single Source of Truth for Models

`model_breakdowns: Dict[str, ModelUsage]` replaces separate `models_used: List[str]`:
- One structure contains all model information
- No redundancy or potential inconsistency
- Breakdowns are always available when model info exists

### 3. Session Bucketing by Start Time

Sessions belong to their start date only:
- Matches existing storage directory structure
- Simple, predictable behavior
- No double-counting across days

### 4. Project at Write Time

Project ID stored when session is written:
- Uses git root or cwd
- No reconstruction needed for historical data
- Consistent across platforms

---

## Dependencies

**Existing infrastructure to leverage**:
- `DailyIndex` (`storage.py:85-99`) - already has session list and totals
- `PlatformIndex` (`storage.py:144-161`) - has date ranges
- `SessionIndex` (`storage.py:51-82`) - has project field
- `list_sessions()` - needs date range extension

**No new external dependencies required**.

---

## Open Questions

See `docs/token-audit/open-questions.md` for unresolved items.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-24 | Initial plan with reduced v1.0 scope (no TUI) |
