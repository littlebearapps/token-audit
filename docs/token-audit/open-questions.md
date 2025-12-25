# Token Audit Open Questions

**Last Updated**: 2025-12-24

---

## Genuinely Unresolved Items

These are questions that may be addressed in future versions.

### 1. Historical Project Backfill

**Question**: Should we attempt to infer project for sessions recorded before project field was added (pre-v0.9.1)?

**Options**:
- **A) No backfill**: Old sessions show `project: null`, group as "Unknown"
- **B) Best-effort backfill**: Parse file paths from session data to infer project
- **C) User-prompted backfill**: CLI command to manually associate old sessions

**Current Leaning**: Option A (no backfill) for v1.0. Consider B for v1.1.

**Blocking**: None (project field exists in current sessions)

---

### 2. Retention Policy

**Question**: Should token-audit auto-prune old sessions to manage disk space?

**Options**:
- **A) No auto-prune**: User manages manually
- **B) Opt-in prune**: `token-audit prune --older-than 90d`
- **C) Configurable auto-prune**: TOML setting for retention period

**Current Leaning**: Option A for v1.0, Option B for v1.1.

**Blocking**: None (not in v1.0 scope)

---

## Resolved Questions

These were open but have been decided.

### Cost Storage Format

**Question**: Float or integer for cost storage?
**Decision**: **Microdollars (int)**. Avoids float precision issues in aggregation.
**Decided**: 2025-12-24

### TUI in v1.0

**Question**: Include TUI historical views in v1.0?
**Decision**: **No**. Deferred to v1.1.0.
**Decided**: 2025-12-24

### `--jq` Flag

**Question**: Include `--jq` flag for inline filtering?
**Decision**: **No**. Users can pipe to `jq` themselves.
**Decided**: 2025-12-24

### Session Bucketing

**Question**: How to handle sessions spanning midnight?
**Decision**: **Start date only**. Session belongs to its start date.
**Decided**: 2025-12-24

### Cross-Platform Default Behavior

**Question**: Should `token-audit daily` (without `--platform`) show all platforms combined?
**Decision**: **Default to all**. Running without `--platform` shows all platforms; use `--platform claude-code` to filter.
**Decided**: 2025-12-24

### Week Start Default

**Question**: Should week start default to Monday (ISO 8601) or Sunday (US convention)?
**Decision**: **Monday (ISO 8601)**. Use `--start-of-week sunday` for US convention.
**Decided**: 2025-12-24

### Empty Period Display

**Question**: How to display days/weeks/months with zero sessions?
**Decision**: **Skip empty periods**. Only show periods with data for cleaner output.
**Decided**: 2025-12-24

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-24 | Initial open questions (trimmed to genuinely unresolved) |
