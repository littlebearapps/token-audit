# ccusage Investigation Notes

**Date**: 2025-12-24
**Repository**: https://github.com/anthropics/ccusage
**Commit Analyzed**: main branch (Dec 2025)

---

## Purpose

Document what patterns to adopt (and not adopt) from ccusage for token-audit's historical reporting feature.

---

## Adopted Patterns

### 1. Time-Based Aggregation Commands

**ccusage structure** (`apps/ccusage/src/commands/`):
- `daily.ts` - Daily usage view
- `weekly.ts` - Weekly usage view
- `monthly.ts` - Monthly usage view

**Adoption**: Create equivalent `token-audit daily`, `token-audit weekly`, `token-audit monthly` CLI commands.

### 2. Data Loading Functions

**ccusage** (`apps/ccusage/src/data/data-loader.ts`):
```typescript
// Line ~45: Load all usage for a date range
export async function loadDailyUsageData(
  startDate: Date,
  endDate: Date
): Promise<DailyUsage[]>

// Line ~80: Load and group by week
export async function loadWeeklyUsageData(
  startDate: Date,
  endDate: Date,
  startOfWeek: 'monday' | 'sunday'
): Promise<WeeklyUsage[]>

// Line ~115: Load and group by month
export async function loadMonthlyUsageData(
  startDate: Date,
  endDate: Date
): Promise<MonthlyUsage[]>
```

**Adoption**: Create `aggregation.py` with `aggregate_daily()`, `aggregate_weekly()`, `aggregate_monthly()` functions.

### 3. Project Grouping

**ccusage** (`apps/ccusage/src/data/_daily-grouping.ts`):
```typescript
// Line ~12: Group sessions by project
export function groupByProject(
  sessions: Session[]
): Map<string, Session[]>

// Line ~35: Create project breakdown
export function groupDataByProject(
  data: DailyUsage[]
): ProjectUsage[]
```

**Adoption**: Add `--instances` flag (ccusage name) for project-level breakdown. Project = git repo root or cwd.

### 4. Model Breakdown

**ccusage** (`apps/ccusage/src/calculate/calculate-cost.ts`):
```typescript
// Line ~28: Aggregate with model breakdown
export function calculateTotals(usage: Usage[]): Totals {
  return {
    tokens: sum(usage.map(u => u.tokens)),
    cost: sum(usage.map(u => u.cost)),
    // ...model breakdown
  };
}
```

**Adoption**: Include `model_breakdowns: Dict[str, ModelUsage]` in aggregates.

### 5. JSON Output

**ccusage** (`apps/ccusage/src/commands/daily.ts`):
```typescript
// Line ~65: JSON output flag
.option('--json', 'Output as JSON')
.option('--jq <expression>', 'Filter JSON with jq')
```

**Adoption**: Add `--json` flag. **Not adopting** `--jq` - users can pipe to `jq` themselves.

### 6. Total Row in Tables

**ccusage** displays a "Total" row at the bottom of all tables with aggregate sums.

**Adoption**: Include total row in CLI table output.

---

## Not Adopted

### 1. TypeScript/Node.js Stack

ccusage is TypeScript. token-audit stays Python for ecosystem consistency.

### 2. "blocks" Command

**ccusage** (`apps/ccusage/src/commands/blocks.ts`):
```typescript
// Anthropic billing-specific, shows API blocks/usage
```

**Not adopting**: This is Anthropic billing-specific. token-audit is cross-platform.

### 3. Statusline Integration

**ccusage** has shell integration for displaying usage in prompt.

**Not adopting**: Shell-specific, not priority for v1.0.

### 4. `--jq` Flag

**ccusage** allows inline jq expressions.

**Not adopting**: Adds complexity. Users can pipe `token-audit daily --json | jq '.[]'`.

### 5. Complex Config Loading

**ccusage** has elaborate config resolution from multiple sources.

**Not adopting**: token-audit uses simple TOML (`token-audit.toml`).

---

## Key Implementation Insights

### Session Date Assignment

**ccusage approach**: Sessions are assigned to their start date.

```typescript
// apps/ccusage/src/data/_daily-grouping.ts, Line ~48
function getSessionDate(session: Session): string {
  return session.startedAt.toISOString().slice(0, 10);  // YYYY-MM-DD
}
```

**token-audit implementation**: Sessions already stored in date directories by start date (`storage.py:235-238`).

### Week Start Configuration

**ccusage** (`apps/ccusage/src/commands/weekly.ts`):
```typescript
// Line ~35: Configurable week start
.option('--start-of-week <day>', 'monday or sunday', 'monday')
```

**token-audit implementation**: Add `--start-of-week` option with default `monday` (ISO 8601 standard).

### Timezone Handling

**ccusage** uses local timezone for date boundaries.

**token-audit implementation**: Already uses timezone-aware timestamps (`base_tracker.py:29-39`).

---

## Data Structure Comparison

| ccusage | token-audit equivalent | Notes |
|---------|---------------------|-------|
| `DailyUsage` | `DailyAggregate` | Same concept |
| `WeeklyUsage` | `WeeklyAggregate` | Same concept |
| `MonthlyUsage` | `MonthlyAggregate` | Same concept |
| `Session` | `SessionIndex` | Already exists in `storage.py:51-82` |
| `ProjectUsage` | `ProjectAggregate` | New dataclass needed |
| `Totals.cost` (float) | `cost_micros` (int) | token-audit uses microdollars |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-24 | Initial investigation with explicit code references |
