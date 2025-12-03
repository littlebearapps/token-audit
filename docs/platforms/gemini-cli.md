# Gemini CLI Platform

> **📖 See [Gemini CLI Setup Guide](../gemini-cli-setup.md) for complete documentation.**

## Overview

MCP Audit supports Gemini CLI through native JSON session file parsing.

**Session Location**: `~/.gemini/tmp/<project_hash>/chats/session-*.json`

## Key Features

- **No OTEL Required**: Parses native session files directly
- **Project Hash Auto-Detection**: SHA256 of your CWD
- **Thinking Tokens**: Tracks Gemini's reasoning tokens separately
- **Model Detection**: Supports Gemini 2.0, 2.5, and 3.0 series

## Quick Start

```bash
# Start tracking (from your project directory)
mcp-audit collect --platform gemini_cli

# Batch process latest session
mcp-audit collect --platform gemini_cli --batch --latest
```

## Token Mapping

| Gemini Token | MCP Audit Field |
|--------------|-----------------|
| `input` | `input_tokens` |
| `output` | `output_tokens` |
| `cached` | `cache_read_tokens` |
| `thoughts` | `thoughts_tokens` (Gemini-specific) |
| `tool` | Tool-related tokens |

## See Also

- [Complete Setup Guide](../gemini-cli-setup.md)
- [Architecture](../architecture.md)
- [Pricing Configuration](../PRICING-CONFIGURATION.md)
