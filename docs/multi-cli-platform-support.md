# Multi-CLI Platform Support Research

**Date**: 2025-12-03
**Status**: ✅ Research Validated
**Validated**: 2025-12-03 via brave-search, jina MCP, and local config/session file analysis
**Purpose**: Investigate requirements for token-audit to support Codex CLI and Gemini CLI platforms

---

## Executive Summary

token-audit already has adapters for both Codex CLI and Gemini CLI, but they need updates to work with actual CLI session data formats discovered on this macbook.

**Key Findings**:
- **Codex CLI Adapter**: Functional but uses subprocess wrapper; needs file-based session reading
- **Gemini CLI Adapter**: **Needs significant rewrite** - expects OTEL telemetry but Gemini uses JSON session files

---

## Platform 1: OpenAI Codex CLI

### Configuration Files
| File | Location | Purpose |
|------|----------|---------|
| `config.toml` | `~/.codex/config.toml` | Main config (model, MCP servers, features) |
| `auth.json` | `~/.codex/auth.json` | Authentication credentials |
| `history.jsonl` | `~/.codex/history.jsonl` | Conversation history |
| `version.json` | `~/.codex/version.json` | CLI version info |

### Session Data Format
**Location**: `~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl`

Each session file is JSONL with event types:
```jsonl
{"timestamp":"...","type":"session_meta","payload":{...}}
{"timestamp":"...","type":"response_item","payload":{"type":"message",...}}
{"timestamp":"...","type":"turn_context","payload":{"model":"gpt-5-codex",...}}
{"timestamp":"...","type":"event_msg","payload":{"type":"token_count","info":{...}}}
{"timestamp":"...","type":"response_item","payload":{"type":"function_call",...}}
```

### Token Usage Data Structure
From `token_count` events:
```json
{
  "type": "event_msg",
  "payload": {
    "type": "token_count",
    "info": {
      "total_token_usage": {
        "input_tokens": 3183,
        "cached_input_tokens": 1920,
        "output_tokens": 100,
        "reasoning_output_tokens": 64,
        "total_tokens": 3283
      },
      "last_token_usage": {...},  // Delta from last event
      "model_context_window": 272000
    },
    "rate_limits": {
      "primary": {"used_percent": 0.0, "window_minutes": 300},
      "secondary": {"used_percent": 1.0, "window_minutes": 10080}
    }
  }
}
```

### MCP Tool Call Format
```json
{
  "type": "response_item",
  "payload": {
    "type": "function_call",
    "name": "mcp__server__tool_name",
    "arguments": "{\"param\":\"value\"}",
    "call_id": "call_xxx"
  }
}
```

### Available Models (Validated 2025-12-03)
Observed in local `~/.codex/config.toml`:
- `gpt-5.1-codex-max` (current default on this macbook)
- `gpt-5-codex` (previous default)
- Model reasoning effort configurable: `model_reasoning_effort = "high"`

### Current Adapter Status
**File**: `src/token_audit/codex_cli_adapter.py`

| Feature | Status | Notes |
|---------|--------|-------|
| Parse session JSONL | ✅ Working | Parses event types correctly |
| Token tracking | ✅ Working | Uses `last_token_usage` for deltas |
| MCP tool detection | ✅ Working | Filters by `mcp__` prefix |
| Model detection | ✅ Working | From `turn_context` events |
| File-based reading | ❌ Missing | Only subprocess wrapper mode |
| OTEL export support | ❌ Missing | Codex supports OTEL but adapter doesn't use it |

**Validation Notes** (2025-12-03):
- Verified session JSONL structure matches documented format
- Confirmed MCP servers in config.toml (brave-search, context7, fs-mcp, github-mcp, etc.)
- Model names in adapter need update to include `gpt-5.1-codex-max`, `gpt-5-codex`

### Required Changes
1. Add file-based session reading mode (read existing `~/.codex/sessions/` files)
2. Add auto-discovery of recent session files
3. Test with actual session data from this macbook
4. Consider OTEL export support as alternative data source

---

## Platform 2: Google Gemini CLI

### Configuration Files
| File | Location | Purpose |
|------|----------|---------|
| `settings.json` | `~/.gemini/settings.json` | Main config (auth, UI, telemetry) |
| `google_accounts.json` | `~/.gemini/google_accounts.json` | Google account info |
| `oauth_creds.json` | `~/.gemini/oauth_creds.json` | OAuth credentials |
| `state.json` | `~/.gemini/state.json` | CLI state |
| `installation_id` | `~/.gemini/installation_id` | Unique installation ID |

### Session Data Format
**Location**: `~/.gemini/tmp/<project_hash>/chats/session-<date>-<id>.json`

Each session file is a JSON object (NOT JSONL, NOT OTEL):
```json
{
  "sessionId": "0b04c358-738c-4a88-887a-7ec5d10c5c51",
  "projectHash": "1102b4e278...",
  "startTime": "2025-11-07T05:10:41.717Z",
  "lastUpdated": "2025-11-08T02:31:51.770Z",
  "messages": [
    {
      "id": "84fae2a9-...",
      "timestamp": "2025-11-07T05:10:41.717Z",
      "type": "user",
      "content": "Hello Gemini..."
    },
    {
      "id": "7c551aed-...",
      "timestamp": "2025-11-07T05:10:53.137Z",
      "type": "gemini",
      "content": "Yes, I have access...",
      "thoughts": [
        {
          "subject": "Defining My Capabilities",
          "description": "I've been reviewing my toolkit...",
          "timestamp": "2025-11-07T05:10:44.545Z"
        }
      ],
      "tokens": {
        "input": 7420,
        "output": 84,
        "cached": 0,
        "thoughts": 868,
        "tool": 0,
        "total": 8372
      },
      "model": "gemini-2.5-pro"
    }
  ]
}
```

### Token Data Per Message
Gemini CLI provides **rich token breakdown per message**:
```json
{
  "tokens": {
    "input": 7420,      // Input context tokens
    "output": 84,       // Generated response tokens
    "cached": 0,        // Cached context tokens
    "thoughts": 868,    // "Thinking" tokens (reasoning)
    "tool": 0,          // Tool call tokens
    "total": 8372       // Sum of all
  }
}
```

### Tool Calls Format (Validated 2025-12-03)
Tool calls are embedded in gemini-type messages as a `toolCalls` array:
```json
{
  "id": "c495846b-...",
  "timestamp": "2025-11-07T05:21:18.087Z",
  "type": "gemini",
  "content": "",
  "toolCalls": [
    {
      "id": "read_file-1762492877944-363d6fe9e6b708",
      "name": "read_file",
      "args": {
        "absolute_path": "/Users/nathanschram/claude-code-tools/CLAUDE.md"
      },
      "result": [...],
      "status": "success",
      "timestamp": "2025-11-07T05:21:18.087Z",
      "displayName": "ReadFile",
      "description": "Reads and returns the content of a specified file..."
    }
  ],
  "thoughts": [...],
  "tokens": {
    "input": 7420,
    "output": 84,
    "cached": 0,
    "thoughts": 868,
    "tool": 0,
    "total": 8372
  },
  "model": "gemini-2.5-pro"
}
```

**Key Discovery**: MCP tools would have names prefixed with `mcp__` similar to other platforms. The `tokens.tool` field tracks tool-related token usage.

### Logs File Format
**Location**: `~/.gemini/tmp/<project_hash>/logs.json`

Contains message history without full token data:
```json
[
  {
    "sessionId": "...",
    "messageId": 0,
    "type": "user",
    "message": "/quit",
    "timestamp": "2025-11-07T05:10:18.407Z"
  }
]
```

### Current Adapter Status
**File**: `src/token_audit/gemini_cli_adapter.py`

| Feature | Status | Notes |
|---------|--------|-------|
| Parse session JSON | ❌ **Wrong format** | Expects OTEL, actual is JSON |
| Token tracking | ❌ **Wrong format** | Token data is per-message, not OTEL metrics |
| MCP tool detection | ❌ **Wrong format** | Now known: `toolCalls` array in messages |
| Thoughts tracking | ✅ Partial | Adapter tracks `thoughts_tokens` but wrong source |
| File-based reading | ❌ Wrong location | Expects telemetry.log, should use session JSON |
| Telemetry support | ⚠️ Optional | OTEL is opt-in, not default |

**Validation Notes** (2025-12-03):
- Confirmed session JSON format with actual session files from this macbook
- Discovered `toolCalls` array structure (was previously unknown)
- Verified token breakdown per message (input/output/cached/thoughts/tool/total)
- OTEL telemetry is optional and requires infrastructure setup

### Required Changes
1. **Complete rewrite** of data source - use session JSON not OTEL
2. Parse `~/.gemini/tmp/<hash>/chats/session-*.json` files
3. Extract token data from message `tokens` object
4. Detect project hash from current working directory
5. Handle `toolCalls` array in gemini messages (format now documented above)
6. Track `thoughts` tokens separately (Gemini's reasoning tokens)

---

## Shared Requirements

### Data Discovery
Both platforms need auto-discovery of session files:
1. Claude Code: `~/.claude/projects/<hash>/cache/mcp.log`
2. Codex CLI: `~/.codex/sessions/YYYY/MM/DD/*.jsonl`
3. Gemini CLI: `~/.gemini/tmp/<hash>/chats/session-*.json`

### Report Generation
Reports should support:
- Per-platform breakdown
- Cross-platform aggregation
- Model-specific cost calculation
- MCP tool usage comparison

### Pricing Configuration
Need to add/verify pricing for:
- OpenAI models (GPT-5.x, O-series, GPT-4.x)
- Google models (Gemini 2.x, 2.5.x, 3.x)

---

## Implementation Priority

| Task | Priority | Effort | Impact |
|------|----------|--------|--------|
| Gemini CLI adapter rewrite | P0 | High | Currently non-functional |
| Codex CLI file reading | P1 | Medium | Enables post-session analysis |
| Codex CLI session discovery | P1 | Low | Improves UX |
| Gemini CLI session discovery | P1 | Medium | Enables auto-tracking |
| Cross-platform reporting | P2 | Medium | Unifies analysis |
| Pricing config updates | P2 | Low | Accurate cost estimates |

---

## User Setup Instructions

### Installing token-audit in Codex CLI Environment

**Installation**:
```bash
pip install token-audit
```

**Current Limitations**:
- Codex CLI runs as a subprocess wrapper, not integrated
- User would need to run: `token-audit collect --platform codex-cli -- codex <args>`
- This wraps the codex command and monitors stdout

**What Codex CLI Would Need**:
1. **No Codex config changes required** - token-audit wraps the process
2. **Alternative**: Read existing session files post-session:
   ```bash
   token-audit report ~/.codex/sessions/2025/12/03/
   ```

**Ideal Future State**:
1. Run `token-audit collect --platform codex-cli` in background
2. token-audit watches `~/.codex/sessions/` for new JSONL files
3. Real-time tracking without wrapping codex command
4. Or: Codex CLI native integration via its OTEL export feature

**Required token-audit Changes**:
- Add file watcher mode for `~/.codex/sessions/`
- Add CLI flag: `--watch-sessions` for live monitoring
- Add session auto-discovery: `token-audit report --platform codex-cli --latest`

---

### Installing token-audit in Gemini CLI Environment

**Installation**:
```bash
pip install token-audit
```

**Current Limitations (Critical)**:
- token-audit expects OpenTelemetry telemetry export
- Gemini CLI does NOT export OTEL by default
- Session data is in different format than adapter expects
- **Current adapter will NOT work**

**What Gemini CLI Would Need** (with current adapter):
1. Enable telemetry in `~/.gemini/settings.json`:
   ```json
   {
     "telemetry": {
       "enabled": true,
       "target": "local",
       "otlpEndpoint": "http://localhost:4317"
     }
   }
   ```
2. Run OTEL collector locally
3. Run token-audit to monitor collector output

**This is impractical** - requires OTEL infrastructure.

**Ideal Future State** (after adapter rewrite):
1. Install token-audit: `pip install token-audit`
2. Run: `token-audit collect --platform gemini-cli`
3. token-audit auto-discovers project hash from CWD
4. token-audit watches `~/.gemini/tmp/<hash>/chats/` for session files
5. Parses rich token data from JSON (input/output/cached/thoughts/tool)

**Required token-audit Changes**:
- Rewrite GeminiCLIAdapter to parse session JSON format
- Auto-detect project hash from CWD
- Watch session directory for new files
- Parse per-message token breakdown
- Handle `thoughts` tokens (Gemini's reasoning)

---

## References

### Official Documentation
- [Codex CLI Main Docs](https://developers.openai.com/codex/cli/)
- [Codex CLI Reference](https://developers.openai.com/codex/cli/reference/)
- [Codex CLI Features](https://developers.openai.com/codex/cli/features/)
- [Codex CLI GitHub](https://github.com/openai/codex)
- [Gemini CLI GitHub](https://github.com/google-gemini/gemini-cli)
- [Gemini CLI Telemetry](https://google-gemini.github.io/gemini-cli/docs/cli/telemetry.html)
- [Gemini CLI Configuration](https://geminicli.com/docs/get-started/configuration/)

### Local Configuration
- Codex CLI: `~/.codex/config.toml`
- Gemini CLI: `~/.gemini/settings.json`

### Session Data Locations
- Codex CLI: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
- Gemini CLI: `~/.gemini/tmp/<project_hash>/chats/session-*.json`

---

## Validation Summary (2025-12-03)

### Research Validation Method
- **brave-search MCP**: Searched official documentation for both CLIs
- **jina MCP**: Fetched and parsed GitHub README content
- **Local file analysis**: Examined actual config and session files on this macbook

### Codex CLI Validation Results
✅ **Accurate** - All documented formats match actual data
- Session JSONL format verified with `~/.codex/sessions/2025/11/04/*.jsonl`
- Config structure verified with `~/.codex/config.toml`
- Token structure matches documented format
- MCP tool call format confirmed

### Gemini CLI Validation Results
✅ **Accurate** - Critical discoveries made
- Session JSON format verified with `~/.gemini/tmp/.../session-*.json`
- **New discovery**: `toolCalls` array format documented
- Confirmed OTEL is optional, session JSON is default
- Token breakdown per message verified

### Plan Validation
✅ **Task-60 plan is accurate and well-prioritized**
- Phase 1 (Gemini Rewrite) correctly marked as P0
- Phase 2 (Codex Enhancement) correctly marked as P1
- Subtask breakdown is comprehensive and actionable
