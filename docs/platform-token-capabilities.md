# Platform Token Capabilities

This document describes the token tracking capabilities and limitations for each platform supported by token-audit, including our implemented MCP tool token estimation.

---

## Overview

token-audit tracks token usage and MCP server efficiency across multiple AI coding platforms. Each platform provides different levels of token attribution detail:

| Platform | Session Tokens | Per-Message Tokens | Per-Tool Tokens | Reasoning Tokens | MCP Tool Data | Built-in Tools |
|----------|---------------|-------------------|-----------------|-----------------|---------------|----------------|
| Claude Code | ✅ Native | ✅ Native | ✅ Native | ❌ Not exposed | Full attribution | ✅ Calls + Tokens |
| Codex CLI | ✅ Native | ✅ Native (turn-level) | ✅ **Estimated** (v0.4.0) | ✅ `reasoning_output_tokens` | Args + results | ✅ Calls only |
| Gemini CLI | ✅ Native | ✅ Native | ✅ **Estimated** (v0.4.0) | ✅ `thoughts` | Args + results | ✅ Calls only |

**Token Estimation (v0.4.0+)**: MCP tools on Codex CLI and Gemini CLI use platform-native tokenizers (~99-100% accuracy).

**New in v0.7.0**: Rate metrics (tokens/min, calls/min) and cache hit ratio tracking across all platforms.

---

## Claude Code

### Token Capabilities

Claude Code provides **complete per-tool token attribution** through its JSONL session logs.

**What's tracked:**
- Input tokens (per tool call)
- Output tokens (per tool call)
- Cache read tokens
- Cache created tokens
- Tool call duration

**Session log format:**
```json
{
  "type": "assistant",
  "message": {
    "usage": {
      "input_tokens": 1234,
      "output_tokens": 567,
      "cache_read_input_tokens": 890,
      "cache_creation_input_tokens": 123
    },
    "content": [{
      "type": "tool_use",
      "name": "mcp__brave-search__brave_web_search",
      "input": {"query": "..."}
    }]
  }
}
```

### Built-in Tool Tracking (v1.2.0)

As of schema v1.2.0, token-audit tracks built-in tools in session files. Claude Code has **18 built-in tools**:

| Tool | Description |
|------|-------------|
| AskUserQuestion | User interaction/clarification |
| Bash | Shell command execution |
| BashOutput | Background shell output retrieval |
| Edit | Targeted file edits |
| EnterPlanMode | Enter plan mode |
| ExitPlanMode | Exit plan mode |
| Glob | File pattern matching |
| Grep | Content search |
| KillShell | Kill background shell |
| NotebookEdit | Jupyter notebook editing |
| Read | File reading |
| Skill | Execute skills |
| SlashCommand | Custom slash commands |
| Task | Sub-agent tasks |
| TodoWrite | Task list management |
| WebFetch | URL content fetching |
| WebSearch | Web searching |
| Write | File creation/overwrite |

```json
{
  "builtin_tool_summary": {
    "total_calls": 15,
    "total_tokens": 1250000,
    "tools": [
      {"tool": "Read", "calls": 5, "tokens": 450000},
      {"tool": "Bash", "calls": 4, "tokens": 350000}
    ]
  }
}
```

This enables post-session analysis of both MCP and built-in tool usage patterns.

### Limitations

None - Claude Code provides full MCP tool token attribution and built-in tool tracking.

---

## Codex CLI (OpenAI)

### Token Capabilities

Codex CLI provides **turn-level token tracking** but does NOT provide per-tool token attribution.

**What's available:**
- Cumulative session totals (`total_token_usage`) - **used by token-audit**
- Per-turn deltas (`last_token_usage`) - not used (causes double-counting)
- Input, output, cached, and reasoning tokens
- Full tool call arguments and results

**Session log format (JSONL):**
```json
// Token count event (turn-level)
{
  "timestamp": "2025-12-04T03:57:56.501Z",
  "type": "event_msg",
  "payload": {
    "type": "token_count",
    "info": {
      "total_token_usage": {
        "input_tokens": 18062,
        "cached_input_tokens": 8704,
        "output_tokens": 162,
        "reasoning_output_tokens": 64,
        "total_tokens": 18224
      },
      "last_token_usage": {
        "input_tokens": 9317,
        "cached_input_tokens": 8704,
        "output_tokens": 51,
        "reasoning_output_tokens": 0,
        "total_tokens": 9368
      }
    }
  }
}

// Tool call event (no token info)
{
  "timestamp": "2025-12-04T03:57:56.731Z",
  "type": "response_item",
  "payload": {
    "type": "function_call",
    "name": "mcp__brave-search__brave_web_search",
    "arguments": "{\"query\": \"...\"}",
    "call_id": "call_kvoLihUZg6LMYJU5nnYlIOJm"
  }
}

// Tool result event (no token info)
{
  "type": "response_item",
  "payload": {
    "type": "function_call_output",
    "call_id": "call_kvoLihUZg6LMYJU5nnYlIOJm",
    "output": "Search results: ..."
  }
}
```

### Event Timing Pattern

```
TOKEN_CNT (before decision)
    ↓
FUNC_CALL (tool invocation)
    ↓
FUNC_CALL_OUTPUT (tool result)
    ↓
TOKEN_CNT (same values - confirmation/duplicate)
    ↓
[Model processes result]
    ↓
TOKEN_CNT (new cumulative total)
```

**Important**: Codex CLI native logs contain **duplicate `token_count` events** - the same values often appear twice consecutively (e.g., Event 2 duplicates Event 1 with identical cumulative totals).

### How token-audit Handles Duplicates (v0.3.14+)

token-audit uses `total_token_usage` (cumulative totals) and **replaces** session values instead of summing:

| Field | Strategy | Why |
|-------|----------|-----|
| `total_token_usage` | REPLACE | Cumulative - last event has final totals |
| `last_token_usage` | IGNORED | Summing would cause double-counting |

This ensures token counts match native Codex CLI values exactly, regardless of duplicate events.

### Limitations

1. **No `call_id` in token events**: Cannot link `token_count` events to specific `function_call` events
2. **Turn-level granularity**: Token deltas include model thinking, not just tool I/O
3. **Multiple tools per turn**: When multiple tools are called in one turn, tokens cannot be separated
4. **No official API**: OpenAI has not documented per-tool token attribution for Codex CLI

### What We CAN Extract

Despite limitations, Codex CLI logs contain:
- Full tool arguments (JSON string)
- Full tool results (string)
- Tool call timing (timestamps)
- Tool names and call IDs

This data enables **token estimation** based on content size.

### Built-in Tool Tracking (v1.2.0)

As of schema v1.2.0, token-audit tracks built-in tools in session files. Codex CLI has **11 built-in tools**:

| Tool | Description |
|------|-------------|
| shell | Main shell execution |
| shell_command | Alternative shell command |
| apply_patch | File patching |
| grep_files | File search |
| list_dir | Directory listing |
| read_file | File reading |
| view_image | Image viewing |
| exec | Unified execution |
| update_plan | Task planning |
| list_mcp_resources | MCP resource discovery |
| list_mcp_resource_templates | MCP resource templates |

```json
{
  "builtin_tool_summary": {
    "total_calls": 8,
    "total_tokens": 0,
    "tools": [
      {"tool": "shell", "calls": 5, "tokens": 0},
      {"tool": "read_file", "calls": 3, "tokens": 0}
    ]
  }
}
```

**Note**: Codex CLI doesn't provide per-tool token attribution, so `tokens` is always 0. Call counts are tracked accurately.

---

## Gemini CLI (Google)

### Token Capabilities

Gemini CLI provides **per-message token tracking** with a dedicated `tool` field (currently unused).

**What's available:**
- Per-message token breakdown
- Input, output, cached, and thoughts tokens
- A `tool` token field (always 0 currently)
- Full tool call arguments and results

**Session log format (JSON):**
```json
{
  "sessionId": "16b12454-dd91-4cc8-a69f-eb5ff9049a4a",
  "messages": [
    {
      "id": "msg_001",
      "type": "gemini",
      "tokens": {
        "input": 10323,
        "output": 16,
        "cached": 0,
        "thoughts": 218,
        "tool": 0,
        "total": 10557
      },
      "toolCalls": [
        {
          "name": "read_file",
          "args": {"file_path": "example.txt"},
          "result": [{"functionResponse": {...}}]
        }
      ]
    }
  ]
}
```

### Token Fields Explained

| Field | Description | Status |
|-------|-------------|--------|
| `input` | Input tokens for the message | ✅ Populated |
| `output` | Output tokens for the response | ✅ Populated |
| `cached` | Cached/reused tokens | ✅ Populated |
| `thoughts` | Thinking/reasoning tokens | ✅ Populated |
| `tool` | Tool-specific tokens | ❌ Always 0 |
| `total` | Sum of all token types | ✅ Populated |

### Limitations

1. **`tool` field unused**: Despite having a dedicated field, it's always 0
2. **Message-level only**: Tokens are per-message, not per-tool-call
3. **Multiple tools per message**: When a message has multiple tool calls, tokens cannot be separated
4. **No official documentation**: Google has not documented per-tool token plans

### What We CAN Extract

Gemini CLI logs contain:
- Full tool arguments (in `args` object)
- Full tool results (in `result` array)
- Message-level tokens (can be correlated to tools)
- Tool names and timing

This data enables **token estimation** based on content size.

### Built-in Tool Tracking (v1.2.0)

As of schema v1.2.0, token-audit tracks built-in tools in session files. Gemini CLI has **12 built-in tools**:

| Tool | Description |
|------|-------------|
| glob | File pattern matching |
| google_web_search | Web search |
| list_directory | Directory listing |
| read_file | Read single file |
| read_many_files | Read multiple files |
| replace | File content replacement |
| run_shell_command | Shell execution |
| save_memory | Memory/context saving |
| search_file_content | Grep/ripgrep search |
| web_fetch | Fetch web content |
| write_file | Write file |
| write_todos | Task management |

```json
{
  "builtin_tool_summary": {
    "total_calls": 12,
    "total_tokens": 0,
    "tools": [
      {"tool": "read_file", "calls": 6, "tokens": 0},
      {"tool": "google_web_search", "calls": 4, "tokens": 0},
      {"tool": "list_directory", "calls": 2, "tokens": 0}
    ]
  }
}
```

**Note**: Gemini CLI doesn't provide per-tool token attribution. Tokens are reported at message level only, so `tokens` is always 0. Call counts are tracked accurately.

---

## Reasoning/Thinking Tokens (v1.3.0)

Starting with schema v1.3.0, token-audit tracks reasoning/thinking tokens separately from output tokens. This provides more accurate cost analysis for models that include thinking tokens.

### Platform Support

| Platform | Field Name | Schema v1.3.0 Field | Notes |
|----------|------------|---------------------|-------|
| Claude Code | N/A | `reasoning_tokens: 0` | Claude doesn't expose thinking tokens |
| Codex CLI | `reasoning_output_tokens` | `reasoning_tokens` | Present in o1, o3-mini, and similar models |
| Gemini CLI | `thoughts` | `reasoning_tokens` | Present in Gemini 2.0+ responses |

### Impact on Token Counts

**Before v1.3.0:**
- `output_tokens` = output + reasoning (combined)
- Reasoning tokens hidden inside output total

**After v1.3.0:**
- `output_tokens` = output only
- `reasoning_tokens` = thinking/reasoning tokens separately
- `total_tokens` = input + output + reasoning + cache_read (for TUI display)

### TUI Display Behavior

The reasoning tokens row is displayed conditionally:

```
# When reasoning_tokens > 0 (Codex CLI, Gemini CLI):
╭─ Token Usage ────────────────────╮
│  Input:      10,000              │
│  Output:     2,000               │
│  Reasoning:  500                 │
│  Cache Read: 50,000              │
│  Total:      62,500              │
╰──────────────────────────────────╯

# When reasoning_tokens == 0 (Claude Code):
╭─ Token Usage ────────────────────╮
│  Input:      10,000              │
│  Output:     2,000               │
│  Cache Read: 50,000              │
│  Total:      62,000              │
╰──────────────────────────────────╯
```

This auto-hiding behavior ensures the TUI remains clean for platforms that don't support thinking tokens.

---

## Token Estimation (Implemented v0.4.0)

Since Codex CLI and Gemini CLI don't provide native per-tool token attribution, token-audit **estimates** MCP tool token usage using platform-native tokenizers.

### Approach

Estimates are calculated from tool call content plus API formatting overhead:

```
Input Tokens  = tokenize(tool_arguments) + FUNCTION_CALL_OVERHEAD
Output Tokens = tokenize(tool_result)
```

Where `FUNCTION_CALL_OVERHEAD = 25` tokens accounts for function name, JSON structure, and API formatting.

### Optional Gemma Tokenizer (Gemini CLI)

The Gemma tokenizer provides 100% accurate token estimation for Gemini CLI but is **not bundled** with the package to keep install size small (~500KB vs ~5MB).

**Install options:**
```bash
# Direct download from GitHub Releases (recommended)
token-audit tokenizer download

# Check status
token-audit tokenizer status
```

The tokenizer is downloaded from GitHub Releases (no HuggingFace account required) to `~/.cache/token-audit/tokenizer.model` (~4MB). SHA256 checksum verification ensures integrity.

**Without the tokenizer:** Gemini CLI uses tiktoken cl100k_base (~95% accuracy). A hint is shown during `collect`:
```
Note: Using standard tokenizer for Gemini CLI (~95% accuracy).
      For 100% accuracy: token-audit tokenizer download
```

**Change your mind later:** Just run `token-audit tokenizer download` - no reinstall needed.

### Implementation

#### TokenEstimator Module (`src/token_audit/token_estimator.py`)

```python
from token_audit.token_estimator import (
    TokenEstimator,
    FUNCTION_CALL_OVERHEAD,  # 25 tokens
    count_tokens,
    estimate_tool_tokens,
    get_estimator_for_platform,
)

# Platform-specific estimators (recommended)
codex_estimator = TokenEstimator.for_platform("codex-cli")   # tiktoken o200k_base
gemini_estimator = TokenEstimator.for_platform("gemini-cli") # SentencePiece/Gemma

# Model-specific estimators
gpt5_estimator = TokenEstimator.for_model("gpt-5.1")     # tiktoken o200k_base
gemini_estimator = TokenEstimator.for_model("gemini-2.5") # SentencePiece

# Estimate tokens for a tool call
input_tokens, output_tokens = estimator.estimate_tool_call(
    args='{"query": "test"}',
    result="Search results...",
    include_overhead=True,  # default: adds FUNCTION_CALL_OVERHEAD
)

# Check estimation method
print(estimator.method_name)    # "tiktoken" or "sentencepiece" or "character"
print(estimator.encoding_name)  # "o200k_base" or "sentencepiece:gemma"
print(estimator.is_fallback)    # True if using character-based fallback
```

#### Platform-Specific Tokenizers

| Platform | Tokenizer | Encoding | Accuracy |
|----------|-----------|----------|----------|
| Codex CLI | tiktoken | o200k_base | ~99-100% (native OpenAI) |
| Gemini CLI | SentencePiece | Gemma tokenizer | 100% (optional download) |
| Gemini CLI | tiktoken | cl100k_base | ~95% (fallback) |
| Claude Code | N/A | Native tokens | 100% (no estimation) |

#### Adapter Integration

Both Codex CLI and Gemini CLI adapters automatically estimate tokens for MCP tool calls:

```python
# Codex CLI adapter (codex_cli_adapter.py)
class CodexCLIAdapter(BaseTracker):
    def __init__(self, ...):
        self._estimator = TokenEstimator.for_platform("codex-cli")
        self._estimated_tool_calls = 0

    def _parse_function_call_output(self, ...):
        if is_mcp_tool:
            input_tokens, output_tokens = self._estimator.estimate_tool_call(
                args=args_str, result=result
            )
            self._estimated_tool_calls += 1
            # Records with is_estimated=True, estimation_method, estimation_encoding

# Gemini CLI adapter (gemini_cli_adapter.py)
class GeminiCLIAdapter(BaseTracker):
    def __init__(self, ...):
        self._token_estimator = TokenEstimator.for_platform("gemini-cli")
        self._estimated_tool_calls = 0

    def _parse_tool_call(self, ...):
        if is_mcp_tool:
            input_tokens, output_tokens = self._token_estimator.estimate_tool_call(
                args=args_str, result=result_str
            )
            self._estimated_tool_calls += 1
```

#### Schema v1.4.0 Estimation Fields

Each `Call` record includes estimation metadata:

```json
{
  "schema_version": "1.4.0",
  "calls": [
    {
      "tool": "mcp__brave-search__brave_web_search",
      "input_tokens": 52,
      "output_tokens": 1250,
      "is_estimated": true,
      "estimation_method": "tiktoken",
      "estimation_encoding": "o200k_base"
    }
  ]
}
```

#### TUI Display

The TUI shows estimation method in the Token Usage panel title:

```
╭─ Token Usage & Cost (MCP: tiktoken) ─────────────╮
│  Input:        10,000                            │
│  Output:       2,000                             │
│  Cache Read:   50,000                            │
│  Total:        62,000                            │
╰──────────────────────────────────────────────────╯

Final Summary:
  Duration: 2m 30s | 15 tool calls ($0.45)
    (5 calls with tiktoken estimation, o200k_base)
```

### What Estimation Measures

| Metric | Meaning | Use Case |
|--------|---------|----------|
| Input Tokens | Tokens in tool arguments + overhead | How much context sent to tool |
| Output Tokens | Tokens in tool results | How much context returned from tool |
| Total Estimated | Combined tool I/O | Overall MCP context load |

### What Estimation Does NOT Measure

- Actual model billing tokens (use session totals for billing)
- System prompt overhead
- Model reasoning about tool calls
- Internal formatting tokens beyond FUNCTION_CALL_OVERHEAD
- Cache efficiency

### Accuracy Details

**Codex CLI (tiktoken o200k_base):**
- Uses OpenAI's native tokenizer for GPT-5.1, o1, o3, o4 models
- ~99-100% accuracy for content tokenization
- FUNCTION_CALL_OVERHEAD adds 25 tokens per call for API formatting

**Gemini CLI (SentencePiece + Gemma):**
- Uses Google's Gemma tokenizer (same family as Gemini)
- 100% accuracy when tokenizer is installed via `token-audit tokenizer download`
- Falls back to tiktoken cl100k_base (~95% accuracy) if Gemma tokenizer not installed
- Tokenizer downloaded from GitHub Releases (no account required)

**Fallback (character-based):**
- Used when tokenizer libraries unavailable
- ~4 characters per token heuristic
- Less accurate but still useful for relative comparisons

### Value Proposition

MCP tool token tracking provides:

1. **Relative comparisons**: Which MCP servers use the most context?
2. **Efficiency insights**: Are tool results excessively large?
3. **Optimization targets**: Which tools should be optimized?
4. **Cross-session trends**: Is MCP usage growing over time?

This is **unique functionality** - competitors like ccusage only track session-level tokens.

---

## Future Possibilities

### Native Per-Tool Token Attribution

We're monitoring these platforms for native per-tool token support:

- **Codex CLI**: OpenAI could add `tokens` field to `function_call` events
- **Gemini CLI**: Google could populate the existing `tool` token field (currently always 0)

If native attribution becomes available, token-audit will automatically prefer native values over estimates, with the `is_estimated` field reflecting the source.

### Feature Requests Filed

- **Task 69.14**: File feature requests with OpenAI and Google for native per-tool token attribution

---

## References

- [tiktoken](https://github.com/openai/tiktoken) - OpenAI's fast BPE tokenizer (used for Codex CLI)
- [Gemma tokenizer](https://huggingface.co/google/gemma-2-2b) - Google's Gemma tokenizer (used for Gemini CLI)
- [Codex CLI](https://github.com/openai/codex) - OpenAI's Codex CLI repository
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) - Google's Gemini CLI repository

---

**Last Updated**: December 2025 (v0.4.0)
