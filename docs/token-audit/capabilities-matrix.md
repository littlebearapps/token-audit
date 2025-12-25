# Token Audit Capabilities Matrix

**Version**: 1.0.0
**Last Updated**: 2025-12-24

---

## Legend

| Symbol | Meaning |
|--------|---------|
| **✓** | Supported - Full, accurate support |
| **◐** | Partial - Works but incomplete/limited |
| **~** | Estimated - Approximation, not exact |
| **—** | Not available - Cannot be implemented |

---

## Session-Level Capabilities

What token-audit can track/calculate for individual sessions.

| Capability | Claude Code | Codex CLI | Gemini CLI | Notes |
|------------|-------------|-----------|------------|-------|
| **Token Tracking** |
| Input tokens | ✓ | ~ | ~ | Codex/Gemini: tiktoken/sentencepiece estimation |
| Output tokens | ✓ | ~ | ~ | Codex/Gemini: tiktoken/sentencepiece estimation |
| Total tokens | ✓ | ~ | ~ | Sum of above |
| Reasoning tokens | ✓ | ✓ | ✓ | Native from all platforms |
| **Cache Metrics** |
| Cache created | ✓ | ~ | — | Codex: estimated from prompts; Gemini: no cache API |
| Cache read | ✓ | ~ | — | Codex: estimated; Gemini: no visibility |
| Cache efficiency | ✓ | ~ | — | ratio = read/created |
| **Cost Calculation** |
| Session cost | ✓ | ~ | ~ | Uses LiteLLM pricing → cache → fallback |
| Model-specific cost | ✓ | ~ | ~ | Per-model rates applied |
| **Tool Attribution** |
| MCP tool calls | ✓ | ✓ | ✓ | All platforms log tool calls |
| Per-tool tokens | ✓ | ~ | ~ | Claude: native; others: estimated |
| Per-server totals | ✓ | ~ | ~ | Aggregated from per-tool |
| Built-in tools | ✓ | ✓ | ✓ | Platform-specific tool lists |
| **Model Tracking** |
| Model used | ✓ | ✓ | ✓ | From session metadata |
| Model switches | ✓ | ✓ | ✓ | Mid-session model changes |
| **Session Metadata** |
| Start/end time | ✓ | ✓ | ✓ | From session files |
| Duration | ✓ | ✓ | ✓ | Calculated |
| Project/cwd | ✓ | ✓ | ✓ | Stored at session write time |

---

## Historical Aggregation Capabilities (v1.0.0)

What token-audit can aggregate across sessions.

| Capability | Claude Code | Codex CLI | Gemini CLI | Notes |
|------------|-------------|-----------|------------|-------|
| **Time-Based Aggregation** |
| Daily totals | ✓ | ~ | ~ | Exact for Claude; estimated for others |
| Weekly totals | ✓ | ~ | ~ | Rolled up from daily |
| Monthly totals | ✓ | ~ | ~ | Rolled up from daily |
| **Grouping** |
| By platform | ✓ | ✓ | ✓ | Cross-platform or single |
| By project | ✓ | ✓ | ✓ | Git root or cwd |
| By model | ✓ | ~ | ~ | Model breakdown per period |
| **Aggregate Metrics** |
| Total tokens | ✓ | ~ | ~ | Sum across sessions |
| Total cost | ✓ | ~ | ~ | Sum in microdollars |
| Session count | ✓ | ✓ | ✓ | Exact count |
| Unique tools | ✓ | ✓ | ✓ | Set of tool names |
| **Cross-Session Analysis** |
| Cache efficiency trend | ✓ | ◐ | — | Claude: full; Codex: limited; Gemini: N/A |
| Tool usage patterns | ✓ | ✓ | ✓ | Aggregated call counts |

---

## Data Quality Indicators

How to interpret accuracy by platform.

| Platform | `accuracy_level` | `confidence` | Typical Use |
|----------|------------------|--------------|-------------|
| Claude Code | `exact` | 1.0 | Native Anthropic API data |
| Codex CLI | `estimated` | 0.90-0.95 | tiktoken o200k_base approximation |
| Gemini CLI | `estimated` | 0.85-0.90 | sentencepiece gemma approximation |

These values are stored per-session in `DataQuality` (`base_tracker.py:325-348`).

---

## Platform-Specific Limitations

### Claude Code
- **Strengths**: Native token counts, full cache visibility, exact costs
- **Limitations**: Requires debug.log file access

### Codex CLI
- **Strengths**: Reasoning tokens native, good tiktoken accuracy
- **Limitations**: Cache metrics estimated, ~5% token variance vs API

### Gemini CLI
- **Strengths**: Reasoning tokens (thoughts) tracked
- **Limitations**: No cache API, sentencepiece requires separate download, ~10% token variance

---

## What Cannot Be Reconstructed Historically

Some data can only be captured at session time:

1. **Per-call tokens for old sessions**: If sessions were recorded before token estimation, we cannot retroactively add per-tool token counts.

2. **Cache metrics for Gemini**: Gemini has no cache API, so historical cache efficiency cannot be calculated.

3. **Exact costs for old models**: If pricing data wasn't cached when the session ran with an old model, we fall back to defaults.

4. **Project for pre-v0.9.1 sessions**: Project field was added in v0.9.1; older sessions have `project: null`.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-24 | Initial matrix with 4-state legend, honest assessment |
