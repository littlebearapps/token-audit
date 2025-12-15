# API Stability Policy

This document defines the stability guarantees for mcp-audit's public API.

---

## Overview

Starting with v0.9.0, mcp-audit provides explicit stability classifications for all public APIs. This enables users to make informed decisions about which APIs to depend on in their integrations.

**Key Principle**: The CLI is always the most stable interface. For maximum stability, prefer CLI usage with `--format json` output over direct Python API usage.

---

## Stability Tiers

### Stable

APIs marked as **stable** have the following guarantees:

- Breaking changes require a **major version** bump (e.g., v1.x → v2.0)
- At least **2 minor versions** of deprecation warnings before removal
- Full backward compatibility within a major version
- Documented behavior is reliable

**Examples**: `StorageManager`, `TokenEstimator`, `PricingConfig`, `create_display`

### Evolving

APIs marked as **evolving** have these characteristics:

- **Interface is stable** (method signatures, class names)
- **Implementation may change** (internal behavior, new optional parameters)
- New fields may be added to data classes
- No removal without deprecation warning

**Examples**: `ClaudeCodeAdapter`, `Session`, `SmellAggregator`

### Deprecated

APIs marked as **deprecated** are scheduled for removal:

- Emit `DeprecationWarning` when used
- Include migration path in warning message
- Removed in the version specified (usually 2 minor versions after deprecation)
- Documented alternatives are provided

**Examples**: `estimate_tool_tokens` (deprecated in v0.9.0, remove in v1.1.0)

---

## Version Guarantees

### v1.0.0 Promise

When mcp-audit reaches v1.0.0:

1. **All "stable" APIs** maintain backward compatibility through v1.x
2. **Deprecations** follow a 2-minor-version warning period
3. **Schema format** is backward compatible within major versions
4. **CLI commands** and their flags maintain compatibility

### Semantic Versioning

mcp-audit follows [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR** (v2.0.0): Breaking changes to stable APIs
- **MINOR** (v1.1.0): New features, deprecations, evolving API changes
- **PATCH** (v1.0.1): Bug fixes only

---

## CLI Stability

The CLI is the primary stable interface:

| Command | Stability | Notes |
|---------|-----------|-------|
| `mcp-audit collect` | Stable | Core collection command |
| `mcp-audit report` | Stable | Report generation |
| `mcp-audit export` | Stable | Data export |
| `mcp-audit smells` | Stable | Smell analysis |
| `mcp-audit ui` | Evolving | Interactive TUI |
| `mcp-audit init` | Evolving | Setup wizard |
| `mcp-audit tokenizer` | Evolving | Tokenizer management |

**Output Formats**: `--format json` output is stable and machine-parseable.

---

## Checking API Stability

### Programmatic Access

```python
from mcp_audit import get_api_stability, API_STABILITY

# Check a single API
stability = get_api_stability("StorageManager")  # "stable"
stability = get_api_stability("estimate_tool_tokens")  # "deprecated"
stability = get_api_stability("FutureAPI")  # "unknown"

# List all stable APIs
stable_apis = [name for name, tier in API_STABILITY.items() if tier == "stable"]

# List all deprecated APIs
deprecated_apis = [name for name, tier in API_STABILITY.items() if tier == "deprecated"]
```

### Runtime Warnings

Deprecated APIs emit `DeprecationWarning` when imported:

```python
import warnings
warnings.filterwarnings("default", category=DeprecationWarning)

from mcp_audit import estimate_tool_tokens
# DeprecationWarning: estimate_tool_tokens is deprecated...
```

---

## API Classification Reference

### Stable APIs (16)

| API | Module | Purpose |
|-----|--------|---------|
| `StorageManager` | storage | Session storage and queries |
| `SessionIndex` | storage | Session metadata for queries |
| `PricingConfig` | pricing_config | Model pricing configuration |
| `load_pricing_config` | pricing_config | Load pricing from TOML |
| `get_model_cost` | pricing_config | Calculate model costs |
| `normalize_tool_name` | normalization | Tool name normalization |
| `normalize_server_name` | normalization | Server name normalization |
| `extract_server_and_tool` | normalization | Parse server/tool from name |
| `TokenEstimator` | token_estimator | Token counting engine |
| `count_tokens` | token_estimator | Count text tokens |
| `get_estimator_for_platform` | token_estimator | Get platform-specific estimator |
| `FUNCTION_CALL_OVERHEAD` | token_estimator | Constant for tool call overhead |
| `DisplayAdapter` | display | Abstract display interface |
| `DisplaySnapshot` | display | Session display data |
| `create_display` | display | Display factory function |
| `DisplayMode` | display | Display mode type alias |

### Evolving APIs (13)

| API | Module | Purpose |
|-----|--------|---------|
| `BaseTracker` | base_tracker | Abstract adapter base class |
| `Session` | base_tracker | Complete session record |
| `ServerSession` | base_tracker | Per-server statistics |
| `Call` | base_tracker | Single tool call record |
| `ToolStats` | base_tracker | Tool usage statistics |
| `TokenUsage` | base_tracker | Token breakdown |
| `MCPToolCalls` | base_tracker | MCP call statistics |
| `ClaudeCodeAdapter` | claude_code_adapter | Claude Code tracking |
| `CodexCLIAdapter` | codex_cli_adapter | Codex CLI tracking |
| `GeminiCLIAdapter` | gemini_cli_adapter | Gemini CLI tracking |
| `SmellAggregator` | smell_aggregator | Cross-session smell analysis |
| `AggregatedSmell` | smell_aggregator | Aggregated smell data |
| `SmellAggregationResult` | smell_aggregator | Aggregation results |

### Deprecated APIs (1)

| API | Deprecated | Remove | Replacement |
|-----|------------|--------|-------------|
| `estimate_tool_tokens` | v0.9.0 | v1.1.0 | `TokenEstimator.estimate_tool_call()` |

---

## Migration Guides

### estimate_tool_tokens → TokenEstimator

**Deprecated (v0.9.0)**:
```python
from mcp_audit import estimate_tool_tokens

input_tokens, output_tokens = estimate_tool_tokens(
    server="zen",
    tool="chat",
    input_data={"prompt": "Hello"},
    output_data={"response": "Hi there!"},
    platform="claude_code"
)
```

**Replacement**:
```python
from mcp_audit import TokenEstimator, get_estimator_for_platform

# Get platform-specific estimator
estimator = get_estimator_for_platform("claude_code")

# Estimate tokens
input_tokens = estimator.count_tokens(str(input_data))
output_tokens = estimator.count_tokens(str(output_data))
```

---

## Reporting Issues

If you encounter unexpected behavior in a stable API:

1. Check the [CHANGELOG](../CHANGELOG.md) for recent changes
2. Verify your mcp-audit version: `mcp-audit --version`
3. Report issues on [GitHub](https://github.com/littlebearapps/mcp-audit/issues)

---

*Last updated: v0.9.0*
