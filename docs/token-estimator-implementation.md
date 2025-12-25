# Token Estimator Implementation Plan

**Version**: 1.0.0
**Created**: 2025-12-04
**Related Task**: Task 69 - MCP Tool Token Tracking Investigation
**Status**: Ready for Implementation

---

## Executive Summary

This document provides a detailed implementation plan for adding token estimation to token-audit for Codex CLI and Gemini CLI sessions. Claude Code sessions have native per-tool token tracking; Codex CLI and Gemini CLI do not expose per-tool tokens, so we estimate them using tiktoken.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Library** | tiktoken | LiteLLM uses tiktoken internally; adds 15+ deps vs 2 |
| **Default encoding** | cl100k_base | Best coverage for GPT-4/Claude-like models |
| **Fallback** | Character-based (~4 chars/token) | When tiktoken fails or unavailable |
| **UI indicator** | `~` prefix or `*` suffix | Clearly distinguish estimated vs native |

---

## Background

### Per-Tool Token Availability

| Platform | Per-Tool Tokens | Data Source |
|----------|-----------------|-------------|
| **Claude Code** | Native | Session JSONL (`usage` in tool messages) |
| **Codex CLI** | Turn-level only | Token counts not linked to individual tools |
| **Gemini CLI** | Message-level only | `tokens.tool` field always 0 |

### Research Findings

1. **No official offline tokenizers** for Claude 3+ or Gemini
2. **tiktoken cl100k_base** provides ~90-95% accuracy for non-OpenAI models
3. **Character-based fallback** (~4 chars/token) is industry standard
4. **Tool tokens = tokenize(arguments) + tokenize(results)**

---

## Architecture

### Module Structure

```
src/token_audit/
├── token_estimator.py      # NEW: TokenEstimator class
├── base_tracker.py         # Update: Add estimation support
├── codex_cli_adapter.py    # Update: Integrate estimation
├── gemini_cli_adapter.py   # Update: Integrate estimation
├── claude_code_adapter.py  # No change (native tokens)
└── display/
    └── rich_display.py     # Update: Show estimated indicators
```

### Class Design

```python
# src/token_audit/token_estimator.py

from typing import Optional, Dict, Tuple
import json

# Optional tiktoken dependency
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False
    tiktoken = None  # type: ignore


class TokenEstimator:
    """
    Estimate token counts for MCP tool arguments and results.

    Uses tiktoken for accurate estimation when available,
    falls back to character-based approximation otherwise.

    Attributes:
        encoding_name: The tiktoken encoding used (e.g., "cl100k_base")
        is_fallback: True if using character-based fallback
        chars_per_token: Ratio used for fallback estimation (default 4.0)
    """

    # Encoding selection based on model family
    MODEL_ENCODINGS: Dict[str, str] = {
        # OpenAI models
        "gpt-4o": "o200k_base",
        "gpt-4o-mini": "o200k_base",
        "o1": "o200k_base",
        "o3": "o200k_base",
        "gpt-5": "o200k_base",
        "gpt-4": "cl100k_base",
        "gpt-3.5": "cl100k_base",
        # Codex models (same as GPT-4o family)
        "codex": "o200k_base",
        # Default for Claude/Gemini (best general approximation)
        "claude": "cl100k_base",
        "gemini": "cl100k_base",
    }

    DEFAULT_ENCODING = "cl100k_base"
    DEFAULT_CHARS_PER_TOKEN = 4.0

    def __init__(
        self,
        encoding_name: Optional[str] = None,
        chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    ):
        """
        Initialize token estimator.

        Args:
            encoding_name: tiktoken encoding to use. If None, uses DEFAULT_ENCODING.
            chars_per_token: Fallback ratio when tiktoken unavailable.
        """
        self.encoding_name = encoding_name or self.DEFAULT_ENCODING
        self.chars_per_token = chars_per_token
        self.is_fallback = False
        self._encoding = None

        self._init_encoding()

    def _init_encoding(self) -> None:
        """Initialize tiktoken encoding or set fallback mode."""
        if not HAS_TIKTOKEN:
            self.is_fallback = True
            return

        try:
            self._encoding = tiktoken.get_encoding(self.encoding_name)
        except Exception:
            self.is_fallback = True

    @classmethod
    def for_model(cls, model: str) -> "TokenEstimator":
        """
        Create estimator tuned for a specific model.

        Args:
            model: Model name or family (e.g., "gpt-4o", "claude-opus-4-5", "gemini-2.5-flash")

        Returns:
            TokenEstimator with appropriate encoding.
        """
        model_lower = model.lower()

        # Find matching encoding
        for prefix, encoding in cls.MODEL_ENCODINGS.items():
            if prefix in model_lower:
                return cls(encoding_name=encoding)

        # Default encoding for unknown models
        return cls()

    @classmethod
    def for_platform(cls, platform: str) -> "TokenEstimator":
        """
        Create estimator for a platform's default models.

        Args:
            platform: Platform name ("claude-code", "codex-cli", "gemini-cli")

        Returns:
            TokenEstimator with platform-appropriate encoding.
        """
        platform_lower = platform.lower().replace("-", "_").replace(" ", "_")

        if "codex" in platform_lower:
            return cls(encoding_name="o200k_base")  # GPT-5.1 Codex
        elif "gemini" in platform_lower:
            return cls(encoding_name="cl100k_base")  # Best approximation
        elif "claude" in platform_lower:
            return cls(encoding_name="cl100k_base")  # Best approximation

        return cls()

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to tokenize.

        Returns:
            Token count (estimated if fallback mode).
        """
        if not text:
            return 0

        if self.is_fallback or self._encoding is None:
            return self._count_fallback(text)

        try:
            return len(self._encoding.encode(text))
        except Exception:
            return self._count_fallback(text)

    def _count_fallback(self, text: str) -> int:
        """Character-based token estimation fallback."""
        return max(1, int(len(text) / self.chars_per_token))

    def estimate_tool_call(
        self,
        arguments: str,
        result: str,
    ) -> Tuple[int, int]:
        """
        Estimate tokens for a tool call.

        Args:
            arguments: JSON string of tool arguments.
            result: String result from the tool.

        Returns:
            Tuple of (input_tokens, output_tokens).
        """
        input_tokens = self.count_tokens(arguments)
        output_tokens = self.count_tokens(result)
        return input_tokens, output_tokens

    def estimate_tool_call_dict(
        self,
        arguments: Dict,
        result: str,
    ) -> Tuple[int, int]:
        """
        Estimate tokens for a tool call with dict arguments.

        Args:
            arguments: Tool arguments as dictionary.
            result: String result from the tool.

        Returns:
            Tuple of (input_tokens, output_tokens).
        """
        args_str = json.dumps(arguments, separators=(",", ":"))
        return self.estimate_tool_call(args_str, result)


# Module-level convenience functions

def count_tokens(text: str, model: Optional[str] = None) -> int:
    """
    Count tokens in text.

    Args:
        text: Text to tokenize.
        model: Optional model name for encoding selection.

    Returns:
        Token count.
    """
    if model:
        estimator = TokenEstimator.for_model(model)
    else:
        estimator = TokenEstimator()
    return estimator.count_tokens(text)


def estimate_tool_tokens(
    arguments: str,
    result: str,
    model: Optional[str] = None,
) -> Tuple[int, int]:
    """
    Estimate tokens for a tool call.

    Args:
        arguments: JSON string of tool arguments.
        result: String result from the tool.
        model: Optional model name for encoding selection.

    Returns:
        Tuple of (input_tokens, output_tokens).
    """
    if model:
        estimator = TokenEstimator.for_model(model)
    else:
        estimator = TokenEstimator()
    return estimator.estimate_tool_call(arguments, result)
```

---

## Data Structures

### Updated Call Dataclass

```python
# In base_tracker.py - add estimation fields to Call

@dataclass
class Call:
    """Single MCP tool call record"""

    # ... existing fields ...

    # NEW: Estimation metadata (v1.2.0)
    is_estimated: bool = False  # True if tokens are estimated
    estimation_method: Optional[str] = None  # "tiktoken" or "character"
    estimation_encoding: Optional[str] = None  # e.g., "cl100k_base"
```

### Session Log Schema Update (v1.2.0)

```json
{
  "file_header": {
    "schema_version": "1.2.0"
  },
  "mcp_tools": {
    "calls": [
      {
        "index": 1,
        "tool": "mcp__brave-search__brave_web_search",
        "input_tokens": 156,
        "output_tokens": 2340,
        "is_estimated": true,
        "estimation_method": "tiktoken",
        "estimation_encoding": "o200k_base"
      }
    ]
  }
}
```

---

## Integration Points

### 1. Codex CLI Adapter

```python
# In codex_cli_adapter.py

from .token_estimator import TokenEstimator

class CodexCliTracker(BaseTracker):
    def __init__(self, ...):
        super().__init__(...)
        self._estimator = TokenEstimator.for_platform("codex-cli")

    def _process_function_call(self, payload: dict) -> None:
        """Process function_call events and estimate tokens."""
        call_id = payload.get("call_id")
        arguments = payload.get("arguments", "{}")

        # Store for later pairing with result
        self._pending_calls[call_id] = {
            "name": payload.get("name"),
            "arguments": arguments,
            "timestamp": datetime.now(timezone.utc),
        }

    def _process_function_result(self, payload: dict) -> None:
        """Process function_call_output and create Call with estimated tokens."""
        call_id = payload.get("call_id")
        result = payload.get("output", "")

        if call_id not in self._pending_calls:
            return

        pending = self._pending_calls.pop(call_id)

        # Estimate tokens
        input_tokens, output_tokens = self._estimator.estimate_tool_call(
            pending["arguments"],
            result
        )

        call = Call(
            timestamp=pending["timestamp"],
            tool_name=pending["name"],
            server=self._extract_server(pending["name"]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            is_estimated=True,
            estimation_method="tiktoken" if not self._estimator.is_fallback else "character",
            estimation_encoding=self._estimator.encoding_name,
        )

        self._record_call(call)
```

### 2. Gemini CLI Adapter

```python
# In gemini_cli_adapter.py

from .token_estimator import TokenEstimator

class GeminiCliTracker(BaseTracker):
    def __init__(self, ...):
        super().__init__(...)
        self._estimator = TokenEstimator.for_platform("gemini-cli")

    def _process_tool_call(self, tool_call: dict, message: dict) -> Call:
        """Process tool call from Gemini session and estimate tokens."""
        name = tool_call.get("name", "")
        args = json.dumps(tool_call.get("args", {}))
        result = json.dumps(tool_call.get("result", []))

        input_tokens, output_tokens = self._estimator.estimate_tool_call(args, result)

        return Call(
            tool_name=name,
            server=self._extract_server(name),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            is_estimated=True,
            estimation_method="tiktoken" if not self._estimator.is_fallback else "character",
            estimation_encoding=self._estimator.encoding_name,
        )
```

### 3. TUI Display Updates

```python
# In display/rich_display.py

def _format_estimated_tokens(self, tokens: int, is_estimated: bool) -> str:
    """Format token count with estimation indicator."""
    if is_estimated:
        return f"~{tokens:,}"  # Tilde prefix for estimates
    return f"{tokens:,}"

def _render_mcp_table(self) -> Table:
    """Render MCP tools table with estimation indicators."""
    table = Table(...)

    # Add footnote if any estimates present
    has_estimates = any(call.is_estimated for call in self.session.calls)

    for call in self.session.calls:
        table.add_row(
            call.tool_name,
            self._format_estimated_tokens(call.input_tokens, call.is_estimated),
            self._format_estimated_tokens(call.output_tokens, call.is_estimated),
            ...
        )

    if has_estimates:
        # Add footnote explaining estimation
        table.caption = "[dim]~ indicates estimated tokens (tiktoken/character-based)[/dim]"

    return table
```

---

## Accuracy Analysis

### Expected Accuracy by Platform

| Platform | Model | Encoding | Expected Accuracy |
|----------|-------|----------|-------------------|
| **Codex CLI** | GPT-5.1 Codex | o200k_base | ~100% |
| **Codex CLI** | GPT-4o | o200k_base | ~100% |
| **Gemini CLI** | Gemini 2.5 | cl100k_base | ~90-95% |
| **Claude Code** | N/A | N/A | Native (100%) |

### Estimation Limitations

1. **Model framing overhead**: Actual API calls include system prompts, tool schemas
2. **Serialization differences**: JSON formatting may vary from API's internal format
3. **Special tokens**: Tool call markers, role tokens not counted
4. **Caching**: Cached tokens not distinguishable in estimates

### Mitigation

- Estimates are clearly marked in UI and logs
- Used for **relative comparison** (which tools use most context?)
- Not for **billing accuracy** (use platform's native totals)

---

## Dependencies

### Required (Already in token-audit)

- `typing` (stdlib)
- `json` (stdlib)
- `dataclasses` (stdlib)

### New Dependency

```toml
# pyproject.toml
dependencies = [
    # ... existing ...
    "tiktoken>=0.7.0",  # Token estimation for MCP tools
]

[project.optional-dependencies]
minimal = [
    # Core without tiktoken - uses character fallback
]
```

### Graceful Degradation

If tiktoken is not installed:
1. Warning logged at startup
2. Character-based fallback activated automatically
3. `is_fallback=True` in estimator
4. `estimation_method="character"` in logs

---

## Testing Strategy

### Unit Tests

```python
# tests/test_token_estimator.py

import pytest
from token_audit.token_estimator import TokenEstimator, count_tokens

class TestTokenEstimator:
    """Test token estimation functionality."""

    def test_basic_counting(self):
        """Test basic token counting."""
        estimator = TokenEstimator()
        tokens = estimator.count_tokens("Hello, world!")
        assert tokens > 0
        assert tokens < 10  # Reasonable for short string

    def test_empty_string(self):
        """Empty string returns 0 tokens."""
        estimator = TokenEstimator()
        assert estimator.count_tokens("") == 0

    def test_json_arguments(self):
        """Test estimation with JSON tool arguments."""
        estimator = TokenEstimator()
        args = '{"query": "python tiktoken tutorial", "limit": 10}'
        input_tokens, output_tokens = estimator.estimate_tool_call(
            args,
            "Search results: 1. Tutorial... 2. Guide..."
        )
        assert input_tokens > 0
        assert output_tokens > 0

    def test_model_encoding_selection(self):
        """Test correct encoding for different models."""
        gpt4o = TokenEstimator.for_model("gpt-4o-mini")
        assert gpt4o.encoding_name == "o200k_base"

        claude = TokenEstimator.for_model("claude-opus-4-5")
        assert claude.encoding_name == "cl100k_base"

    def test_platform_encoding_selection(self):
        """Test correct encoding for platforms."""
        codex = TokenEstimator.for_platform("codex-cli")
        assert codex.encoding_name == "o200k_base"

        gemini = TokenEstimator.for_platform("gemini-cli")
        assert gemini.encoding_name == "cl100k_base"

    def test_fallback_mode(self):
        """Test character-based fallback."""
        estimator = TokenEstimator()
        estimator.is_fallback = True
        estimator._encoding = None

        tokens = estimator.count_tokens("Hello world!")  # 12 chars
        assert tokens == 3  # 12 / 4 = 3

    def test_large_json_result(self):
        """Test with large tool result."""
        estimator = TokenEstimator()
        large_result = '{"results": [' + ', '.join([f'"item{i}"' for i in range(100)]) + ']}'

        input_tokens, output_tokens = estimator.estimate_tool_call(
            '{"query": "test"}',
            large_result
        )

        assert output_tokens > input_tokens
        assert output_tokens > 50  # Large result = many tokens
```

### Integration Tests

```python
# tests/test_estimation_integration.py

def test_codex_adapter_estimates_tokens():
    """Codex adapter should estimate tokens for tool calls."""
    # Parse sample Codex session with tool calls
    # Verify calls have is_estimated=True
    # Verify estimation_method is set
    pass

def test_gemini_adapter_estimates_tokens():
    """Gemini adapter should estimate tokens for tool calls."""
    # Parse sample Gemini session with tool calls
    # Verify calls have is_estimated=True
    pass

def test_claude_adapter_native_tokens():
    """Claude adapter should use native tokens (not estimated)."""
    # Parse sample Claude session
    # Verify calls have is_estimated=False
    pass
```

### Accuracy Validation

```python
# tests/test_estimation_accuracy.py

def test_accuracy_vs_openai_api():
    """Compare tiktoken estimates to known OpenAI token counts."""
    # Known examples from OpenAI documentation
    test_cases = [
        ("Hello, world!", "cl100k_base", 4),
        ("The quick brown fox", "cl100k_base", 4),
    ]

    for text, encoding, expected in test_cases:
        estimator = TokenEstimator(encoding_name=encoding)
        actual = estimator.count_tokens(text)
        # Allow small variance
        assert abs(actual - expected) <= 1
```

---

## Implementation Phases

### Phase 1: Core Estimator (Task 69.7)
- [ ] Create `token_estimator.py` module
- [ ] Implement `TokenEstimator` class
- [ ] Add model/platform encoding selection
- [ ] Add character-based fallback
- [ ] Write unit tests

### Phase 2: Codex Integration (Task 69.8)
- [ ] Update `codex_cli_adapter.py`
- [ ] Add estimator initialization
- [ ] Estimate tokens in `_process_function_call`
- [ ] Set estimation metadata on Call
- [ ] Write integration tests

### Phase 3: Gemini Integration (Task 69.9)
- [ ] Update `gemini_cli_adapter.py`
- [ ] Add estimator initialization
- [ ] Estimate tokens in `_process_tool_call`
- [ ] Set estimation metadata on Call
- [ ] Write integration tests

### Phase 4: TUI Updates (Task 69.10)
- [ ] Update `rich_display.py` for estimation indicators
- [ ] Add `~` prefix for estimated tokens
- [ ] Add footnote explaining estimates
- [ ] Test display rendering

### Phase 5: Schema Update (Task 69.11)
- [ ] Update `Call` dataclass with estimation fields
- [ ] Update schema version to 1.2.0
- [ ] Update `data-contract.md`
- [ ] Ensure backward compatibility

### Phase 6: Documentation (Task 69.13)
- [ ] Update `platform-token-capabilities.md`
- [ ] Add estimation accuracy notes
- [ ] Document tiktoken dependency

### Phase 7: Validation & Confidence (Task 69.19)
- [ ] Add `estimation_confidence` field to `Call` dataclass
- [ ] Implement confidence level assignment logic
- [ ] Add `token-audit validate <session>` CLI command
- [ ] Update TUI with confidence indicators (●●● high, ●●○ medium, ●○○ low)
- [ ] Add session-level validation summary to display
- [ ] Update schema to v1.2.0 with validation fields
- [ ] Document accuracy expectations in user-facing docs

---

## Accuracy and Validation

### What Is Estimated vs What Is Native

| Component | Estimated | Native |
|-----------|-----------|--------|
| Tool arguments | ✅ Tokenized | ❌ Not available from platform |
| Tool results | ✅ Tokenized | ❌ Not available from platform |
| Model framing | ❌ Not included | ✅ Included in platform totals |
| System prompts | ❌ Not included | ✅ Included in platform totals |
| Tool schemas | ❌ Not included | ✅ Included in platform totals |
| Cache tokens | ❌ Not distinguished | ✅ Available from platform |

### What This Means

**Estimated tool tokens** = `tokenize(arguments) + tokenize(result)`

This captures ~85-95% of the actual tokens used for MCP tool operations. The ~5-15% gap is due to:
1. **Framing overhead**: Model wraps tool calls with special tokens
2. **Schema context**: Tool schemas loaded into context
3. **Serialization variance**: API may format JSON differently

### Confidence Levels

| Level | Indicator | Platform | Expected Accuracy |
|-------|-----------|----------|-------------------|
| **High** | ●●● | Codex CLI | 95-100% (same tokenizer) |
| **Medium** | ●●○ | Gemini CLI | 90-95% (approximation) |
| **Low** | ●○○ | Fallback | ~80% (character-based) |

### User Validation

Users can validate estimates by comparing:

```
Session Native Total: 50,000 tokens
Estimated Tool Total: ~12,500 tokens (25%)
```

If estimated tool tokens significantly exceed native totals, something is wrong.

### CLI Validation Command

```bash
token-audit validate <session-id>
```

Output example:
```
Token Estimation Validation Report
===================================
Session: abc123-def456
Platform: codex-cli

Native Totals (from platform):
  Input tokens:  45,000
  Output tokens: 5,000
  Total:         50,000

Estimated Tool Tokens:
  Total:         ~12,500 (25% of session)
  Method:        tiktoken (o200k_base encoding)

Confidence Distribution:
  High   (●●●): 45 tools (79%)
  Medium (●●○): 12 tools (21%)
  Low    (●○○): 0 tools (0%)

Estimation Quality: GOOD
Expected accuracy: 95-100% for tool token estimates
```

---

## Rollout Plan

1. **v0.4.0-alpha**: Token estimation behind feature flag
2. **v0.4.0-beta**: Enabled by default, schema v1.2.0
3. **v0.4.0**: Full release with estimation support

---

## Future Considerations

### Potential Improvements

1. **Model-specific tokenizers**: If Anthropic/Google release official tokenizers
2. **Calibration data**: Collect actual vs estimated for accuracy tuning
3. **API-based validation**: Optional API calls to validate estimates

### Monitoring

1. Track estimation accuracy reports from users
2. Monitor tiktoken version updates
3. Watch for new model encodings (e.g., o300k_base)

---

## References

- [tiktoken GitHub](https://github.com/openai/tiktoken)
- [OpenAI Cookbook: Token Counting](https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken)
- [Task 69 Investigation](../backlog/tasks/task-69%20-%20MCP-Tool-Token-Tracking-Investigation.md)
- [Task 69.18 tiktoken vs LiteLLM](../backlog/tasks/task-69.18%20-%20Tiktoken-vs-LiteLLM-Comparison.md)
