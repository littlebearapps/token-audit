# Ollama CLI Research Findings

**Date**: 2025-12-11
**Status**: Research Complete
**Conclusion**: Ollama CLI requires API monitoring approach (not session file parsing)

---

## Executive Summary

Unlike Claude Code, Codex CLI, and Gemini CLI, **Ollama CLI does not persist conversation history** to accessible session files. This means the standard adapter pattern (parse session files) won't work. Instead, Ollama support requires an **API monitoring approach**.

---

## Research Findings

### Session Storage Comparison

| Platform | Session Storage | Format | Accessible |
|----------|-----------------|--------|------------|
| Claude Code | `~/.claude/projects/*/` | JSON | Yes |
| Codex CLI | `~/.codex/` | JSON | Yes |
| Gemini CLI | `~/.gemini/tmp/*/chats/` | JSON | Yes |
| **Ollama CLI** | **None** | N/A | **No** |

### Ollama Directory Structure

```
~/.ollama/
├── logs/           # Application logs (no conversation data)
│   ├── app.log     # GUI app events
│   └── server.log  # Server startup/shutdown
├── models/         # Downloaded model blobs
├── history         # Readline history (user inputs only, no responses)
├── id_ed25519      # Authentication keys
└── id_ed25519.pub
```

### Key Discoveries

1. **No Conversation Persistence**: Ollama CLI is a stateless REPL. Conversations are held in memory only and lost when the session ends.

2. **`~/.ollama/history`**: This file only stores readline input history (what the user typed), NOT model responses or tool calls.

3. **`/save` Command**: Creates a model variant with conversation context, but stores it as SHA256 blobs - not human-readable session files.

4. **macOS GUI Storage**: The Ollama macOS app (if installed as GUI) may store history in `~/Library/Containers/com.ollama.ollama/Data/Documents/ollama.sqlite`, but this is GUI-only.

5. **Ollama API DOES Report Tokens**: Despite CLI not logging, the API responses include full token counts.

---

## Ollama API Token Information

The Ollama API (`http://localhost:11434`) returns token counts in responses:

### `/api/generate` Response
```json
{
  "model": "llama3.2",
  "response": "...",
  "done": true,
  "prompt_eval_count": 26,      // INPUT tokens
  "eval_count": 259,            // OUTPUT tokens
  "prompt_eval_duration": 130079000,
  "eval_duration": 4232710000,
  "total_duration": 10706818083
}
```

### `/api/chat` Response (with tools)
```json
{
  "model": "llama3.2",
  "message": {
    "role": "assistant",
    "content": "",
    "tool_calls": [
      {
        "function": {
          "name": "get_weather",
          "arguments": {"city": "Tokyo"}
        }
      }
    ]
  },
  "prompt_eval_count": 169,
  "eval_count": 15
}
```

### Key API Fields

| Field | Description |
|-------|-------------|
| `prompt_eval_count` | Number of input tokens |
| `eval_count` | Number of output tokens |
| `tool_calls` | Array of tool invocations |
| `model` | Model name used |
| `total_duration` | Total processing time (nanoseconds) |

---

## Recommended Implementation: API Monitoring

Since Ollama doesn't persist sessions, we need to **intercept API traffic** to track usage.

### Approach Options

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Proxy Mode** | Run token-audit as HTTP proxy between client and Ollama | Full capture, works with any client | Requires config change |
| **B. Log Watcher** | Monitor Ollama server logs | No config needed | Limited data in logs |
| **C. API Polling** | Poll `/api/ps` for active models | Simple | No conversation data |
| **D. Wrapper Script** | Wrap `ollama run` command | Works with CLI | Complex, may miss API clients |

### Recommended: Proxy Mode (Option A)

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│ Ollama CLI  │────▶│  token-audit   │────▶│ Ollama API   │
│ or Client   │     │  Proxy       │     │ :11434       │
└─────────────┘     └──────────────┘     └──────────────┘
                          │
                          ▼
                    ┌──────────────┐
                    │ Session Log  │
                    │ (JSONL)      │
                    └──────────────┘
```

**Implementation**:
1. `token-audit proxy --port 11435` starts local proxy
2. User configures clients to use `:11435` instead of `:11434`
3. Proxy forwards requests, logs all traffic
4. Creates session files compatible with existing adapters

### Alternative: Environment Variable Approach

```bash
# User sets this once
export OLLAMA_HOST=http://localhost:11435

# token-audit runs proxy
token-audit ollama-proxy --upstream http://localhost:11434
```

---

## Tool Calling in Ollama

Ollama supports tool calling but uses its own format (not MCP):

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get weather for a city",
        "parameters": {
          "type": "object",
          "properties": {
            "city": {"type": "string"}
          },
          "required": ["city"]
        }
      }
    }
  ]
}
```

**Note**: Ollama's tool calling is NOT MCP protocol. Tools are defined per-request, not via MCP server configuration.

---

## Data Quality Implications

| Metric | Via API Proxy | Without Proxy |
|--------|---------------|---------------|
| Input tokens | `exact` | N/A |
| Output tokens | `exact` | N/A |
| Tool calls | `exact` | N/A |
| Model name | `exact` | N/A |
| Cost | `$0.00` (local) | N/A |
| Cache | N/A (no cache) | N/A |

---

## Next Steps (v0.6.1)

1. **Create `ollama_proxy.py`**: HTTP proxy that intercepts Ollama API traffic
2. **Session logging**: Write intercepted data to JSONL session files
3. **Adapter integration**: Create `OllamaProxyAdapter` to read logged sessions
4. **CLI command**: `token-audit ollama-proxy` to start proxy mode
5. **Documentation**: Setup guide for proxy configuration

---

## References

- [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [GitHub Issue #1052 - Chat logs location](https://github.com/ollama/ollama/issues/1052)
- [GitHub Issue #7684 - Session files documentation](https://github.com/ollama/ollama/issues/7684)
- [Reddit: Ollama Conversation History](https://www.reddit.com/r/ollama/comments/1oarkmc/ollama_conversation_history/)
