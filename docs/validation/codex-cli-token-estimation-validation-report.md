# Codex CLI Token Estimation Validation Report

**Date**: 2025-12-07
**Task**: 69.20 - Codex CLI Token Estimation Validation
**token-audit Version**: 0.3.14
**Codex CLI Version**: 0.64.0
**Validation Result**: **FAIL** - Critical bug found in total_tokens calculation

---

## Test Session Details

| Field | Value |
|-------|-------|
| Session ID | `019af69f-ac6c-70a3-b54d-7db938041889` |
| Model | GPT-5.1 Codex Max (`gpt-5.1-codex-max`) |
| Timestamp | 2025-12-07T13:24:10 |
| Duration | ~58 seconds |
| MCP Servers Used | fs-mcp, rg-mcp |
| MCP Tool Calls | 2 (fs_read, rg_search) |

### Test Prompt

```
Use the fs-mcp to read the contents of CLAUDE.md in this directory, then use rg-mcp
to search for 'token' in all python files in src/. Summarize what you find.
```

---

## Token Count Comparison Table

| Metric | Native Codex CLI | token-audit | Variance | % Diff | Status |
|--------|------------------|-----------|----------|--------|--------|
| input_tokens | 43,853 | 43,853 | 0 | 0.0% | **PASS** |
| output_tokens | 1,044 | 1,044 | 0 | 0.0% | **PASS** |
| cached_input_tokens / cache_read_tokens | 8,320 | 8,320 | 0 | 0.0% | **PASS** |
| reasoning_output_tokens / reasoning_tokens | 576 | 576 | 0 | 0.0% | **PASS** |
| **total_tokens** | **44,897** | **53,793** | **+8,896** | **+19.8%** | **FAIL** |

---

## Root Cause Analysis

### Bug Location
**File**: `src/token_audit/codex_cli_adapter.py`
**Lines**: 944-950

### Current (Incorrect) Calculation
```python
total_tokens = (
    usage["input_tokens"]           # 43,853
    + usage["output_tokens"]        # 1,044
    + usage["cache_created_tokens"] # 0
    + usage["cache_read_tokens"]    # 8,320 (BUG)
    + reasoning_tokens              # 576   (BUG)
)
# Result: 53,793
```

### Expected (Correct) Calculation
According to OpenAI's API documentation:
```python
total_tokens = input_tokens + output_tokens
# Result: 44,897
```

### Why This Is Wrong

1. **`cache_read_tokens` is already included in `input_tokens`**
   - OpenAI's `input_tokens` is the TOTAL input tokens
   - `cached_input_tokens` is a SUBSET that hit the cache (for billing purposes)
   - Adding it again double-counts these tokens

2. **OpenAI's `total_tokens` excludes reasoning tokens**
   - Native Codex CLI: `total_tokens = input_tokens + output_tokens`
   - Reasoning tokens are tracked separately for informational purposes
   - They should NOT be added to total_tokens

### Variance Breakdown
```
token-audit total:    53,793
Native total:       44,897
Difference:          8,896

Breakdown:
- cache_read_tokens:  8,320 (incorrectly added)
- reasoning_tokens:     576 (incorrectly added)
Total error:          8,896 (100% accounted for)
```

---

## MCP Tool Token Estimation Validation

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `is_estimated` field present | `true` | `True` | **PASS** |
| `estimation_method` field | `"tiktoken"` | `tiktoken` | **PASS** |
| `estimation_encoding` field | `"o200k_base"` | `o200k_base` | **PASS** |
| `input_tokens` > 0 | Yes | 55, 62 | **PASS** |
| `output_tokens` > 0 | Yes | 2440, 40675 | **PASS** |
| Sum of MCP tokens < session total | Yes | 43,232 < 53,793 | **PASS** |

### MCP Tool Call Details

| Tool | Server | Input Tokens | Output Tokens | Total Tokens |
|------|--------|--------------|---------------|--------------|
| mcp__fs__fs_read | fs | 55 | 2,440 | 2,495 |
| mcp__rg__rg_search | rg | 62 | 40,675 | 40,737 |
| **Total** | | **117** | **43,115** | **43,232** |

---

## TUI Display Verification

### TUI Capture Excerpt
```
╭──────────────────────────────────────────────────────────────────────────────╮
│ MCP Audit v0.3.14 - Full Session ↺  [codex-cli]                              │
│ Project: token-audit  Started: 13:25:04  Duration: 25s                         │
│ Model: GPT-5.1 Codex Max                                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭───────────────────── Token Usage & Cost (MCP: tiktoken) ─────────────────────╮
│  Input:                  43,853  Cache Created:               0              │
│  Output:                  1,044  Cache Read:              8,320              │
│  Reasoning:                 576                                              │
│  Total:                  53,793  Efficiency:              15.9%              │
│  Messages:                    3  Built-in Tools:          0 (0)              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭────────────────────── MCP Servers Usage (2 servers, 2 calls) ────────────────╮
│   fs                   1 calls        2K  (avg 2K/call)                      │
│     └─ fs_read           1 calls        2K  (100% of server)                 │
│   rg                   1 calls       41K  (avg 41K/call)                     │
│     └─ rg_search         1 calls       41K  (100% of server)                 │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### TUI Checklist

#### Header Section
- [x] Project name displayed: "token-audit"
- [x] Platform shows "codex-cli"
- [x] Model detected correctly: "GPT-5.1 Codex Max"
- [x] Duration timer running

#### Token Usage Panel
- [x] Panel title shows estimation method: `Token Usage & Cost (MCP: tiktoken)`
- [x] `Input:` tokens displayed: 43,853
- [x] `Output:` tokens displayed: 1,044
- [x] `Cache Read:` tokens displayed: 8,320
- [x] `Reasoning:` tokens displayed: 576
- [ ] `Total:` tokens displayed: 53,793 **INCORRECT** (should be 44,897)
- [x] Cost estimate displayed: $0.0663

#### MCP Servers Panel
- [x] Panel title shows "MCP Servers Usage"
- [x] Each server listed with call count
- [x] Each server shows token count
- [x] Tools listed under each server
- [x] Total MCP calls shown: 2

---

## Session Log File Verification

### File Metadata (`_file`)
- [x] `schema_version` is "1.4.0"
- [x] `generated_by` shows "token-audit v0.3.14"

### Token Usage (`token_usage`)
- [x] `input_tokens`: 43,853 (matches native)
- [x] `output_tokens`: 1,044 (matches native)
- [x] `cache_read_tokens`: 8,320 (matches native `cached_input_tokens`)
- [x] `reasoning_tokens`: 576 (matches native `reasoning_output_tokens`)
- [ ] `total_tokens`: 53,793 **DOES NOT MATCH** native 44,897

### Cost Estimates
- [x] `cost_estimate_usd`: $0.0663 (calculated correctly)
- [x] `cost_no_cache_usd`: $0.0757 (calculated correctly)
- [x] `cache_savings_usd`: $0.0094 (calculated correctly)

### MCP Summary (`mcp_summary`)
- [x] `total_calls`: 2 (correct)
- [x] `unique_servers`: 2 (correct)
- [x] `servers_used`: ["fs", "rg"] (correct)
- [x] `top_by_tokens` populated
- [x] `top_by_calls` populated

### Tool Calls (`tool_calls`)
For EACH MCP tool call:
- [x] `tool` name correct (starts with `mcp__`)
- [x] `server` extracted correctly
- [x] `input_tokens` > 0 (estimated)
- [x] `output_tokens` > 0 (estimated)
- [x] `total_tokens` = input + output
- [x] `is_estimated` = `true`
- [x] `estimation_method` = `"tiktoken"`
- [x] `estimation_encoding` = `"o200k_base"`

---

## Issues Found

| # | Severity | Component | Description | Fix Required |
|---|----------|-----------|-------------|--------------|
| 1 | **Critical** | `codex_cli_adapter.py:944-950` | `total_tokens` calculation incorrectly adds `cache_read_tokens` (already a subset of `input_tokens`) and `reasoning_tokens` (excluded by OpenAI from total) | **Yes** |

### Recommended Fix

```python
# Lines 944-950 in codex_cli_adapter.py
# Change from:
total_tokens = (
    usage["input_tokens"]
    + usage["output_tokens"]
    + usage["cache_created_tokens"]
    + usage["cache_read_tokens"]
    + reasoning_tokens
)

# To:
total_tokens = usage["input_tokens"] + usage["output_tokens"]
```

**Note**: The reasoning_tokens should still be tracked in the session for informational purposes but NOT added to total_tokens.

---

## Acceptance Criteria Status

| Criteria | Status |
|----------|--------|
| Headless test session generated successfully with `codex exec` | **PASS** |
| TUI captured via tmux shows all expected elements | **PASS** |
| TUI token counts match native Codex CLI exactly | **FAIL** (total_tokens) |
| Session log file has schema version 1.4.0 | **PASS** |
| Session log token counts match native Codex CLI exactly | **FAIL** (total_tokens) |
| All MCP tool calls have estimation fields populated | **PASS** |
| Estimation method is "tiktoken" with "o200k_base" encoding | **PASS** |
| No critical or high severity issues found | **FAIL** (1 critical issue) |
| Validation report generated | **PASS** |

---

## Final Determination

**RESULT: FAIL**

The Codex CLI token estimation validation has **FAILED** due to a critical bug in the `total_tokens` calculation that causes a 19.8% variance from native Codex CLI values.

### What Works Correctly
- Individual token counts (input, output, cache, reasoning) all match exactly
- MCP tool token estimation with tiktoken/o200k_base is working
- Cost calculations are correct
- Schema version 1.4.0 fields are all present
- TUI displays all required information

### What Needs Fixing
- `total_tokens` calculation must match OpenAI's formula: `input_tokens + output_tokens`

### Impact
- Users see inflated total token counts in TUI and session logs
- Token comparison across sessions will be inconsistent
- Efficiency metrics may be skewed

---

## Test Artifacts

- **Native Codex CLI session**: `~/.codex/sessions/2025/12/07/rollout-2025-12-07T13-24-10-019af69f-ac6c-70a3-b54d-7db938041889.jsonl`
- **token-audit session**: `~/.token-audit/sessions/codex-cli/2025-12-07/token-audit-2025-12-07T13-25-04.json`
- **TUI capture**: `/tmp/codex-tui-capture.txt`
- **Native token extraction**: `/tmp/codex-native-tokens.json`
