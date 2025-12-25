# Cross-Platform Token Estimation Validation Report

**Date**: 2025-12-08
**token-audit Version**: 0.3.14
**Schema Version**: 1.4.0
**Status**: **PASS**
**Task Reference**: Task 69.22

---

## 1. Executive Summary

| Platform | Validation Status | Session Token Accuracy | MCP Estimation Working |
|----------|-------------------|------------------------|------------------------|
| Codex CLI | **PASS** | 0% variance | Yes (tiktoken/o200k_base) |
| Gemini CLI | **PASS** | 0% variance | Yes (tiktoken/cl100k_base) |

**Overall Status**: **PASS**

Both CLI platforms demonstrate 100% session-level token accuracy compared to their native implementations. MCP and built-in tool token estimation is functioning correctly on both platforms.

---

## 2. Test Environment

| Component | Version |
|-----------|---------|
| token-audit | 0.3.14 |
| tiktoken | 0.7.0+ |
| sentencepiece | 0.2.0+ |
| Codex CLI | 0.64.0 |
| Gemini CLI | 0.19.1 |
| Python | 3.13 |
| macOS | Darwin 25.1.0 |

---

## 3. Codex CLI Validation Results (Task 69.25)

**Validation Date**: 2025-12-07
**Result**: **PASS**
**Session ID**: `019af737-ab3f-7431-af96-7e029b019e56`
**Report**: `docs/validation/codex-cli-token-estimation-retest-report.md`

### 3.1 Session Token Accuracy

| Metric | Native Codex CLI | token-audit | Variance | % Diff | Status |
|--------|------------------|-----------|----------|--------|--------|
| input_tokens | 27,143 | 27,143 | 0 | 0.0% | **PASS** |
| output_tokens | 2,635 | 2,635 | 0 | 0.0% | **PASS** |
| cached_input_tokens / cache_read_tokens | 16,896 | 16,896 | 0 | 0.0% | **PASS** |
| reasoning_output_tokens / reasoning_tokens | 1,984 | 1,984 | 0 | 0.0% | **PASS** |
| total_tokens | 29,778 | 29,778 | 0 | 0.0% | **PASS** |

**Acceptance**: 0% variance - ALL PASS

### 3.2 MCP Tool Token Estimation

| Tool | Server | Input | Output | Total | is_estimated | method | encoding | Status |
|------|--------|-------|--------|-------|--------------|--------|----------|--------|
| `mcp__fs__fs_read` | fs | 39 | 1,858 | 1,897 | `true` | `tiktoken` | `o200k_base` | **PASS** |

### 3.3 Built-in Tool Token Estimation

| Tool | Input | Output | Total | is_estimated | method | encoding | Status |
|------|-------|--------|-------|--------------|--------|----------|--------|
| `__builtin__:shell_command` | 61 | 49 | 110 | `true` | `tiktoken` | `o200k_base` | **PASS** |

### 3.4 TUI Display Verification

- [x] Built-in tool with tokens: `__builtin__:shell_command (110 tokens)`
- [x] MCP tool with tokens: `mcp__fs__fs_read (1,897 tokens)`
- [x] Total tokens displayed: 29,778
- [x] MCP calls count: 2
- [x] Cost displayed: $0.0624

### 3.5 Cost Calculations

| Metric | Value |
|--------|-------|
| Cost w/ Cache (USD) | $0.0624 |
| Cost w/o Cache (USD) | $0.0814 |
| Cache Savings | $0.0190 (23.4% saved) |
| Cache Efficiency | 38% |

### 3.6 Issues Found

| # | Severity | Component | Description |
|---|----------|-----------|-------------|
| 1 | Info | base_tracker.py | UserWarning for `__builtin__:` prefix - expected behavior, not a bug |

**Note**: All acceptance criteria met. Both MCP tools and built-in tools have correct token estimation.

---

## 4. Gemini CLI Validation Results (Task 69.26)

**Validation Date**: 2025-12-07
**Result**: **PASS**
**Session File**: `session-2025-12-07T06-40-8062fd2b.json`
**Project Hash**: `76c62a47a1287071d52c32065e26834b212bf4df1e1551d71ebc39403d65d37b`
**Report**: `docs/validation/gemini-cli-token-estimation-retest-report.md`

### 4.1 Session Token Accuracy

| Metric | Native Gemini CLI | token-audit | Variance | % Diff | Status |
|--------|-------------------|-----------|----------|--------|--------|
| input / input_tokens | 25,357 | 25,357 | 0 | 0.0% | **PASS** |
| output / output_tokens | 316 | 316 | 0 | 0.0% | **PASS** |
| cached / cache_read_tokens | 6,399 | 6,399 | 0 | 0.0% | **PASS** |
| thoughts / reasoning_tokens | 1,049 | 1,049 | 0 | 0.0% | **PASS** |
| total / total_tokens | 26,722 | 26,722 | 0 | 0.0% | **PASS** |

**Acceptance**: 0% variance - ALL PASS

### 4.2 MCP Tool Token Estimation

| Tool | Server | Input | Output | Total | is_estimated | method | encoding | Status |
|------|--------|-------|--------|-------|--------------|--------|----------|--------|
| `mcp__fs__read_file` | fs | 33 | 1,485 | 1,518 | `true` | `tiktoken` | `cl100k_base` | **PASS** |

### 4.3 Built-in Tool Token Estimation

| Tool | Input | Output | Total | is_estimated | method | encoding | Status |
|------|-------|--------|-------|--------------|--------|----------|--------|
| `builtin__google_web_search` | 36 | 2,443 | 2,479 | `true` | `tiktoken` | `cl100k_base` | **PASS** |

### 4.4 Gemini-Specific: `thoughts` -> `reasoning_tokens` Mapping

| Source | Value | Status |
|--------|-------|--------|
| Native Gemini `thoughts` | 1,049 | Captured |
| token-audit `reasoning_tokens` | 1,049 | **PASS** |
| Match? | Yes (0% variance) | **PASS** |

### 4.5 Cost Calculations

| Metric | Value |
|--------|-------|
| Cost w/ Cache (USD) | $0.0558 |
| Cost w/o Cache (USD) | $0.0673 |
| Cache Savings | $0.0115 (17.1% saved) |
| Cache Efficiency | 20% |

### 4.6 Issues Found

No issues found during final validation run.

---

## 5. Cross-Platform Comparison

### 5.1 Estimation Method Comparison

| Aspect | Codex CLI | Gemini CLI |
|--------|-----------|------------|
| Tokenizer Library | tiktoken | tiktoken (fallback) |
| Encoding | o200k_base | cl100k_base |
| Fallback Encoding | N/A | cl100k_base |
| Expected Accuracy | ~99-100% | ~95-99% (fallback) |
| Observed Accuracy | 100% (session-level) | 100% (session-level) |

**Note**: Gemini CLI currently uses tiktoken/cl100k_base fallback. The bundled Gemma tokenizer (`sentencepiece:gemma`) is available but requires explicit setup. Task 69.29/69.30 addressed tokenizer bundling.

### 5.2 TUI Display Consistency

| Feature | Codex CLI | Gemini CLI | Consistent? |
|---------|-----------|------------|-------------|
| Panel title shows estimation method | Yes | Yes | Yes |
| Token counters format correctly | Yes | Yes | Yes |
| MCP servers panel layout | Yes | Yes | Yes |
| Final summary format | Yes | Yes | Yes |

### 5.3 Session Log Schema v1.4.0 Compliance

| Field | Codex CLI | Gemini CLI | Required |
|-------|-----------|------------|----------|
| `is_estimated` | Yes | Yes | Yes |
| `estimation_method` | `tiktoken` | `tiktoken` | Yes |
| `estimation_encoding` | `o200k_base` | `cl100k_base` | Yes |
| `input_tokens` > 0 | Yes | Yes | Yes |
| `output_tokens` > 0 | Yes | Yes | Yes |

---

## 6. Accuracy Summary

| Platform | Session Total Match | MCP Fields Populated | TUI Correct | Overall |
|----------|---------------------|----------------------|-------------|---------|
| Codex CLI | **PASS** (0%) | **PASS** | **PASS** | **PASS** |
| Gemini CLI | **PASS** (0%) | **PASS** | **PASS** | **PASS** |

**Acceptance Threshold Met**:
- Session totals match native CLI exactly (0% variance) on BOTH platforms
- All MCP calls have estimation fields populated
- All TUI elements display correctly

---

## 7. Issues Summary (All Platforms)

| # | Platform | Severity | Component | Description | Fix Required |
|---|----------|----------|-----------|-------------|--------------|
| 1 | Codex CLI | Info | base_tracker.py | UserWarning for `__builtin__:` prefix | No (expected) |

**Bugs Fixed During Validation Cycle**:

| Task | Platform | Issue | Resolution |
|------|----------|-------|------------|
| 69.23 | Codex CLI | `total_tokens` calculation bug | Fixed to match OpenAI formula: `input + output` |
| 69.24 | Both | Built-in tools showed 0 tokens | Extended estimation to all tool types |
| 69.27 | Gemini CLI | Token double-counting bug | Fixed session token aggregation |
| 69.28 | Gemini CLI | MCP tools not detected | Fixed tool naming pattern detection |

---

## 8. Recommendations

### Bugs Fixed Before v0.4.0

1. **Task 69.23**: Fixed `total_tokens` calculation in Codex CLI adapter to match OpenAI formula
2. **Task 69.24**: Extended token estimation to built-in tools (both platforms)
3. **Task 69.27**: Fixed Gemini CLI token double-counting
4. **Task 69.28**: Fixed Gemini CLI MCP tool detection

### Improvements for Future Releases

1. Consider adding automated validation tests to CI/CD pipeline
2. Add per-platform token comparison regression tests
3. Monitor upstream CLI changes for session format updates

### Documentation Updates Completed

1. `docs/platform-token-capabilities.md` - Updated with validation results
2. Platform-specific validation reports generated
3. Cross-platform comparison documented

---

## 9. Lessons Learned

1. **Validate assumptions about API semantics**: The `total_tokens` bug arose from assuming cache tokens should be added to total, when they're actually a subset of input tokens (OpenAI API)

2. **Test against native CLI output**: Direct comparison with native CLI session files is essential for accuracy validation

3. **Fix bugs before proceeding**: Each blocking bug was addressed before continuing validation (69.23 -> 69.24 -> 69.27 -> 69.28)

4. **Platform-specific quirks exist**: Each CLI has different tool naming conventions (e.g., `__builtin__:` vs `builtin__`, MCP tool detection patterns)

5. **Iterative testing is valuable**: Multiple test runs revealed progressive issues that were fixed incrementally

---

## 10. Conclusion

The token-audit token estimation feature for v0.4.0 is **production-ready** across both supported CLI platforms:

### Codex CLI
- 100% session-level token accuracy (0% variance)
- tiktoken/o200k_base provides accurate MCP tool estimation
- Built-in tool estimation working correctly
- Cost calculations accurate

### Gemini CLI
- 100% session-level token accuracy (0% variance)
- tiktoken/cl100k_base fallback working correctly
- MCP tool detection fixed and verified
- `thoughts` -> `reasoning_tokens` mapping correct
- Built-in tool estimation working correctly

### Overall Assessment

**Token estimation is functioning correctly across all supported platforms.** The v0.4.0 release can proceed with confidence that:

1. Session-level token counts match native CLI implementations exactly
2. MCP and built-in tool token estimation provides accurate estimates
3. Schema v1.4.0 properly records estimation metadata
4. TUI displays all token information correctly
5. Cost calculations are accurate

**Final Verdict: PASS - Ready for v0.4.0 Release**

---

## References

- Task 69.20 - Codex CLI Token Estimation Validation (initial)
- Task 69.21 - Gemini CLI Token Estimation Validation (initial)
- Task 69.23 - Fix Codex CLI Total Tokens Calculation
- Task 69.24 - Fix Built-in Tool Token Estimation
- Task 69.25 - Codex CLI Token Estimation Retest
- Task 69.26 - Gemini CLI Token Estimation Retest
- Task 69.27 - Fix Gemini CLI Token Double-Counting
- Task 69.28 - Fix Gemini CLI MCP Tool Detection
- `docs/platform-token-capabilities.md`
- `docs/validation/codex-cli-token-estimation-retest-report.md`
- `docs/validation/gemini-cli-token-estimation-retest-report.md`
