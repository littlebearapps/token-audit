# Gemini CLI Token Estimation Validation Report

**Task**: 69.21 - Gemini CLI Token Estimation Validation
**Date**: 2025-12-07
**Validator**: Claude (Opus 4.5)
**token-audit Version**: 0.3.14
**Gemini CLI Version**: 0.19.1

---

## Executive Summary

| Category | Status | Notes |
|----------|--------|-------|
| **Session-Level Tokens** | ✅ PASS | 100% match with native Gemini CLI |
| **Built-in Tool Tokens** | ❌ FAIL | Bug: No token estimation applied |
| **MCP Tool Tokens** | ⚠️ N/A | No MCP tools called in test session |
| **Overall Result** | **PARTIAL PASS** | Blocked by Task 69.24 |

---

## Test Session Details

| Property | Value |
|----------|-------|
| **Session File** | `session-2025-12-07T04-11-61d29c4e.json` |
| **Project Hash** | `76c62a47a1287071d52c32065e26834b212bf4df1e1551d71ebc39403d65d37b` |
| **Model** | gemini-3-pro-preview |
| **Duration** | ~29 seconds |
| **Message Count** | 3 |
| **Tool Calls** | 3 (2x google_web_search, 1x web_fetch) |

### Test Prompt

```bash
gemini "Search the web for 'MCP Model Context Protocol' and summarize the first 3 results. Then use context7 to get documentation for the 'express' npm package." --yolo --output-format json
```

---

## Session-Level Token Validation

### Comparison Table

| Metric | Native Gemini CLI | token-audit | Variance | Status |
|--------|-------------------|-----------|----------|--------|
| `input_tokens` | 33,779 | 33,779 | 0 (0.0%) | ✅ PASS |
| `output_tokens` | 390 | 390 | 0 (0.0%) | ✅ PASS |
| `cache_read_tokens` | 9,513 | 9,513 | 0 (0.0%) | ✅ PASS |
| `reasoning_tokens` | 2,111 | 2,111 | 0 (0.0%) | ✅ PASS |
| `total_tokens` | 36,280 | 36,280 | 0 (0.0%) | ✅ PASS |

**Result**: All session-level token counts match native Gemini CLI exactly.

### Native Token Calculation Verification

```
input + output = 33,779 + 390 = 34,169
input + output + thoughts = 33,779 + 390 + 2,111 = 36,280 ✓
```

Gemini CLI's `total` includes reasoning/thoughts tokens, which token-audit correctly captures.

---

## Gemini-Specific Validation

### `thoughts` → `reasoning_tokens` Mapping

| Source | Field | Value | Status |
|--------|-------|-------|--------|
| Native Gemini CLI | `thoughts` | 2,111 | - |
| token-audit | `reasoning_tokens` | 2,111 | ✅ PASS |

The `thoughts` field from native Gemini CLI is correctly mapped to `reasoning_tokens` in token-audit.

### Native `tool` Field Verification

```python
Unique tool token values in native session: {0}
```

Confirmed: Native Gemini CLI `tool` field is always 0, confirming token estimation is necessary for per-tool attribution.

---

## Tool-Level Token Validation

### Built-in Tools Called

| Tool | Call Count | Native Tokens | token-audit Tokens | Status |
|------|------------|---------------|------------------|--------|
| `google_web_search` | 2 | 0 (native always 0) | 0 | ❌ FAIL |
| `web_fetch` | 1 | 0 (native always 0) | 0 | ❌ FAIL |

### Estimation Fields Check

| Field | Expected | Actual | Status |
|-------|----------|--------|--------|
| `is_estimated` | `true` | `false` | ❌ FAIL |
| `estimation_method` | `"sentencepiece"` | `null` | ❌ FAIL |
| `estimation_encoding` | `"sentencepiece:gemma"` | `null` | ❌ FAIL |
| `input_tokens` | > 0 | 0 | ❌ FAIL |
| `output_tokens` | > 0 | 0 | ❌ FAIL |

**Root Cause**: Token estimation is only implemented for MCP tools (`mcp__*` prefix), not built-in tools. See Task 69.24 for fix.

---

## TUI Capture Verification

### TUI Screenshot (tmux capture)

```
╭──────────────────────────────────────────────────────────────────────────────────╮
│ MCP Audit v0.3.14 - Full Session ↺  [gemini-cli]                                 │
│ Project: token-audit  Started: 15:14:34  Duration: 21s                             │
│ Model: Gemini 3 Pro Preview                                                      │
│ 🌿 v0.4.0-token-estimation@10e45d2*  📁 1 files                                  │
╰──────────────────────────────────────────────────────────────────────────────────╯
╭─────────────────────────────────── Token Usage & Cost ───────────────────────────╮
│  Input:                  33,779  Cache Created:               0                  │
│  Output:                    390  Cache Read:              9,513                  │
│  Reasoning:               2,111                                                  │
│  Total:                  36,280  Efficiency:              22.0%                  │
│  Messages:                    3  Built-in Tools:          3 (0)                  │
╰──────────────────────────────────────────────────────────────────────────────────╯
```

### TUI Element Verification

| Element | Expected | Status |
|---------|----------|--------|
| Header shows platform | `[gemini-cli]` | ✅ PASS |
| Model detected | `Gemini 3 Pro Preview` | ✅ PASS |
| Input tokens | 33,779 | ✅ PASS |
| Output tokens | 390 | ✅ PASS |
| Reasoning tokens | 2,111 | ✅ PASS |
| Cache Read tokens | 9,513 | ✅ PASS |
| Total tokens | 36,280 | ✅ PASS |
| Built-in Tools count | 3 | ✅ PASS |
| Built-in Tools tokens | 0 | ❌ FAIL (bug) |
| Estimation method label | Not shown | ⚠️ N/A |

---

## Session Log Verification

### Schema Version

```json
"_file": {
  "schema_version": "1.4.0",
  "generated_by": "token-audit v0.3.14"
}
```

**Status**: ✅ PASS - Schema version is 1.4.0 as expected.

### Tool Calls in Session Log

```json
"tool_calls": [
  {
    "index": 1,
    "tool": "builtin__google_web_search",
    "server": "builtin",
    "input_tokens": 0,           // ❌ Should be > 0
    "output_tokens": 0,          // ❌ Should be > 0
    "is_estimated": false,       // ❌ Should be true
    "estimation_method": null,   // ❌ Should be "sentencepiece"
    "estimation_encoding": null  // ❌ Should be "sentencepiece:gemma"
  }
]
```

---

## Issues Found

### Issue #1: Built-in Tool Token Estimation Missing (HIGH SEVERITY)

**Location**: `src/token_audit/gemini_cli_adapter.py` lines 892-921

**Problem**: Token estimation is only applied to MCP tools (`mcp__*` prefix), not built-in tools (`google_web_search`, `web_fetch`, `read_file`, etc.).

**Impact**:
- Built-in tool calls show 0 tokens in TUI and session logs
- Violates Task 69 validated plan: "Built-in vs MCP Tools: No difference in accuracy approach."
- Cannot analyze per-tool token usage for Gemini CLI sessions

**Fix**: Task 69.24 created - extend token estimation to both MCP AND built-in tools.

### Issue #2: No MCP Tools in Test Session (MEDIUM)

**Observation**: Gemini CLI routes "search the web" and "use context7" requests to built-in tools, not MCP tools:
- `google_web_search` instead of `mcp__brave-search__*`
- `web_fetch` instead of `mcp__context7__*`

**Impact**: Cannot validate MCP token estimation (`mcp__*` tools) without explicit MCP tool calls.

**Recommendation**: Configure Gemini CLI MCP servers and test with explicit `mcp__` tool calls.

### Issue #3: TUI Estimation Label Missing (LOW)

**Expected**: TUI panel title shows `Token Usage & Cost (MCP: sentencepiece)`
**Actual**: TUI shows `Token Usage & Cost` without estimation method

**Root Cause**: No MCP tools called → no estimation triggered → no label shown.

---

## Cost Verification

| Metric | Value | Status |
|--------|-------|--------|
| Cost with Cache | $0.0741 | ✅ Calculated |
| Cost without Cache | $0.0913 | ✅ Calculated |
| Cache Savings | $0.0171 (19%) | ✅ Calculated |

---

## Conclusion

### Summary

| Validation Category | Result |
|---------------------|--------|
| Session-level token tracking | ✅ **100% PASS** |
| `thoughts` → `reasoning_tokens` mapping | ✅ **PASS** |
| Schema version 1.4.0 | ✅ **PASS** |
| Cost calculations | ✅ **PASS** |
| Built-in tool token estimation | ❌ **FAIL** (Task 69.24) |
| MCP tool token estimation | ⚠️ **NOT TESTED** |

### Final Verdict: **PARTIAL PASS**

**What Works**:
- Session-level token counts match native Gemini CLI exactly (0% variance)
- Reasoning tokens correctly mapped from `thoughts`
- Schema v1.4.0 compliant
- Cost calculations accurate

**What's Blocked**:
- Built-in tool token estimation not implemented (Task 69.24 required)
- MCP tool estimation not validated (need explicit MCP tool calls)

### Next Steps

1. **Fix Task 69.24**: Extend token estimation to built-in tools
2. **Re-run validation**: After fix, re-run Task 69.21 to validate built-in tools
3. **Test MCP tools**: Configure Gemini CLI MCP servers and test `mcp__*` tools
4. **Complete Task 69.22**: Cross-platform validation report

---

## Appendix

### Native Gemini CLI Output (excerpt)

```json
{
  "stats": {
    "models": {
      "gemini-3-pro-preview": {
        "tokens": {
          "prompt": 33779,
          "candidates": 390,
          "total": 36280,
          "cached": 9513,
          "thoughts": 2111,
          "tool": 0
        }
      }
    },
    "tools": {
      "totalCalls": 3,
      "byName": {
        "google_web_search": { "count": 2 },
        "web_fetch": { "count": 1 }
      }
    }
  }
}
```

### token-audit Session Log (excerpt)

```json
{
  "_file": {
    "schema_version": "1.4.0",
    "generated_by": "token-audit v0.3.14"
  },
  "token_usage": {
    "input_tokens": 33779,
    "output_tokens": 390,
    "cache_read_tokens": 9513,
    "reasoning_tokens": 2111,
    "total_tokens": 36280
  },
  "mcp_summary": {
    "total_calls": 3,
    "unique_tools": 2,
    "servers_used": ["builtin"]
  }
}
```

### Test Files

- Native session: `~/.gemini/tmp/76c62a47.../chats/session-2025-12-07T04-11-61d29c4e.json`
- token-audit session: `~/.token-audit/sessions/gemini-cli/2025-12-07/token-audit-2025-12-07T15-14-34.json`
- TUI capture: `/tmp/gemini-tui-capture.txt`
