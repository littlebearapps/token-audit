# Multi-Model Detection Research

**Date**: 2025-12-11
**Task**: 108.2.1
**Purpose**: Document how to detect model usage and changes per platform for v0.6.0 multi-model tracking.

---

## Summary

| Platform | Model Field Location | Multi-Model Sessions | Detection Strategy |
|----------|---------------------|---------------------|-------------------|
| Claude Code | `message.model` in assistant events | Yes (MCP servers) | Track per-message, aggregate by model |
| Codex CLI | `turn_context.payload.model` | Rare (not observed) | Track per-turn_context event |
| Gemini CLI | `message.model` in gemini messages | Yes (model switching) | Track per-message, detect switches |

---

## Claude Code

### Model Field Location

Model information is in the `message.model` field of assistant events:

```json
{
  "type": "assistant",
  "message": {
    "model": "claude-opus-4-5-20251101",
    "id": "msg_01CSmKGSRv8b1e4x7yMY3YAS",
    "type": "message",
    "role": "assistant",
    "content": [...],
    "usage": {
      "input_tokens": 10,
      "output_tokens": 3,
      "cache_creation_input_tokens": 46361,
      "cache_read_input_tokens": 12610
    }
  }
}
```

### Model Identifier Formats

| Model ID | Display Name |
|----------|-------------|
| `claude-opus-4-5-20251101` | Claude Opus 4.5 |
| `claude-sonnet-4-5-20250929` | Claude Sonnet 4.5 |
| `claude-sonnet-4-20250514` | Claude Sonnet 4 |
| `claude-opus-4-20250514` | Claude Opus 4 |
| `claude-3-5-haiku-20241022` | Claude Haiku 3.5 |

### Multi-Model Sessions

**Cause**: MCP servers (like zen MCP) call external AI models. When zen's `thinkdeep` or `consensus` tools call GPT-5.1 or Gemini, those responses appear in the debug log with their respective model IDs.

**Example multi-model session**:
- 184 messages with `claude-sonnet-4-5-20250929` (primary)
- 4 messages with `gemini-3-pro-preview` (from zen MCP)
- 4 messages with `gpt-5.1` (from zen MCP)

### Edge Cases

| Value | Meaning |
|-------|---------|
| `<synthetic>` | Synthetic/test messages |
| `haiku` | Short form (some MCP servers) |
| External models | `gpt-5.1`, `gemini-3-pro-preview` from MCP tools |

### Detection Strategy

```python
# Track model per assistant message
if data.get("type") == "assistant":
    message = data.get("message", {})
    model_id = message.get("model")
    if model_id:
        # Add to models_used set
        # Track tokens per model in model_usage dict
```

### Model Change Detection

Model doesn't change via user command mid-session. Multiple models appear because:
1. Different MCP servers may use different models
2. MCP tools like zen `consensus` call multiple external models

**Strategy**: Track model on EVERY assistant message, not just first. Aggregate tokens by model.

---

## Codex CLI

### Model Field Location

Model information is in `turn_context` events:

```json
{
  "timestamp": "2025-12-10T05:14:13.418Z",
  "type": "turn_context",
  "payload": {
    "cwd": "/Users/.../mcp-audit/main",
    "approval_policy": "never",
    "sandbox_policy": {"type": "read-only"},
    "model": "gpt-5.1",
    "effort": "high",
    "summary": "auto"
  }
}
```

Also in `session_meta` for provider info:
```json
{
  "type": "session_meta",
  "payload": {
    "model_provider": "openai",
    "cli_version": "0.65.0"
  }
}
```

### Model Identifier Formats

| Model ID | Display Name |
|----------|-------------|
| `gpt-5.1` | GPT-5.1 |
| `gpt-5.1-codex-max` | GPT-5.1 Codex Max |
| `gpt-5-codex` | GPT-5 Codex |
| `o4-mini` | O4 Mini |
| `gpt-4o` | GPT-4o |

### Multi-Model Sessions

**Not observed** in production data. Codex CLI sessions appear to use a single model throughout.

### Detection Strategy

```python
# Track model from turn_context events
if event_type == "turn_context":
    model_id = payload.get("model")
    if model_id:
        # Track per turn_context
        # Each turn_context represents new turn, check if model changed
```

### Model Change Detection

Current implementation only sets model once. For v0.6.0:
- Track model on each `turn_context` event
- Compare to previous model to detect switches
- Aggregate tokens per model

---

## Gemini CLI

### Model Field Location

Model information is in the `model` field of gemini-type messages:

```json
{
  "id": "msg-123",
  "timestamp": "2025-12-05T04:48:00.000Z",
  "type": "gemini",
  "content": "...",
  "model": "gemini-2.5-flash",
  "tokens": {
    "input": 1234,
    "output": 567,
    "cached": 100,
    "thoughts": 50,
    "tool": 200,
    "total": 2151
  }
}
```

### Model Identifier Formats

| Model ID | Display Name |
|----------|-------------|
| `gemini-3-pro-preview` | Gemini 3 Pro Preview |
| `gemini-2.5-pro` | Gemini 2.5 Pro |
| `gemini-2.5-flash` | Gemini 2.5 Flash |
| `gemini-2.5-flash-lite` | Gemini 2.5 Flash Lite |
| `gemini-2.0-flash` | Gemini 2.0 Flash |

### Multi-Model Sessions

**Yes** - Model switches observed within single session:

```
Model switch at msg 16: gemini-3-pro-preview -> gemini-2.5-flash
Model switch at msg 24: gemini-2.5-flash -> gemini-3-pro-preview
Model switch at msg 58: gemini-3-pro-preview -> gemini-2.5-flash

Model counts: {'gemini-3-pro-preview': 40, 'gemini-2.5-flash': 10}
```

### Detection Strategy

```python
# Track model per gemini message
if msg.message_type == "gemini":
    model_id = msg.model
    if model_id:
        # Add to models_used set
        # Track tokens per model in model_usage dict
```

### Model Change Detection

Model CAN change mid-session (user can switch models). For v0.6.0:
- Track model on EVERY gemini message
- Detect switches by comparing to previous model
- Record switch events for analysis
- Aggregate tokens per model

---

## Implementation Recommendations

### Data Structure Changes

```python
# Per-call tracking
@dataclass
class Call:
    tool_name: str
    model: Optional[str]  # NEW: Which model made this call
    input_tokens: int
    output_tokens: int
    # ... existing fields

# Session-level aggregation
@dataclass
class Session:
    models_used: List[str]  # NEW: All models used in session
    model_usage: Dict[str, ModelUsage]  # NEW: Per-model breakdown

@dataclass
class ModelUsage:
    model_id: str
    tokens: int
    cost: float
    calls: int  # Number of assistant messages with this model
```

### Schema v1.6.0 Additions

```json
{
  "models_used": ["claude-opus-4-5-20251101", "gpt-5.1"],
  "model_usage": {
    "claude-opus-4-5-20251101": {
      "input_tokens": 50000,
      "output_tokens": 10000,
      "cache_created_tokens": 5000,
      "cache_read_tokens": 40000,
      "cost_usd": 0.45
    },
    "gpt-5.1": {
      "input_tokens": 1000,
      "output_tokens": 500,
      "cost_usd": 0.02
    }
  }
}
```

### Edge Case Handling

| Case | Strategy |
|------|----------|
| Missing model field | Use session default or "unknown" |
| Unknown model ID | Store as-is, use fallback pricing |
| `<synthetic>` model | Exclude from cost calculation |
| External models | Include in tracking, use appropriate pricing |
| Model switches | Record switch events, don't lose token history |

---

## Verification Checklist

- [x] Claude Code model field documented
- [x] Codex CLI model field documented
- [x] Gemini CLI model field documented
- [x] Multi-model scenarios identified
- [x] Edge cases documented
- [x] Implementation recommendations provided
