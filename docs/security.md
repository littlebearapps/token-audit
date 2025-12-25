# MCP Server Security Considerations

This document describes the security measures implemented in token-audit's MCP server to protect against common vulnerabilities.

## Overview

The token-audit MCP server exposes 8 tools for analyzing AI coding session efficiency. Security measures are in place to:

1. **Prevent path traversal attacks** - Restrict file access to known configuration directories
2. **Prevent credential exposure** - Redact sensitive data in outputs
3. **Prevent information disclosure** - Sanitize error messages

## Input Validation

### Path Validation (`analyze_config` tool)

The `analyze_config` tool accepts an optional `config_path` parameter. To prevent attackers from reading arbitrary files:

**Allowed Directories**:
- `~/.claude/` - Claude Code configuration
- `~/.codex/` - Codex CLI configuration
- `~/.gemini/` - Gemini CLI configuration

**Allowed Extensions**:
- `.json` - JSON configuration files
- `.toml` - TOML configuration files

**Rejected Patterns**:
- Path traversal sequences (`../`)
- Absolute paths outside allowed directories
- Disallowed file extensions (`.py`, `.sh`, etc.)

**Example - Valid path**:
```
~/.claude/settings.json
```

**Example - Rejected paths**:
```
~/.claude/../../etc/passwd  # Path traversal rejected
/etc/passwd                 # Outside allowed directories
~/.claude/script.py         # Invalid extension
```

### Other Tool Inputs

All other tool inputs use Pydantic schema validation with:
- **Enum validation** - Platform names validated against allowed values
- **Type validation** - String, boolean, integer types enforced
- **Default values** - Sensible defaults prevent null pointer issues

## Output Sanitization

### Credential Redaction

Credentials detected in configuration files are shown as redacted previews to help users identify which secret is affected while not exposing the full value:

| Credential Type | Preview Format |
|-----------------|----------------|
| OpenAI API key | `sk-abcd...GHIJ` |
| Anthropic API key | `sk-ant-abc...1234` |
| GitHub PAT (classic) | `ghp_abc...7890` |
| GitHub PAT (fine-grained) | `github_pat_abc...7890` |
| AWS Access Key ID | `AKIAIOSF...MPLE` |
| Google API key | `AIzaABCD...5678` |

This matches the format used by the credential detector's `value_preview` field.

### Path Sanitization

Full file paths in outputs are abbreviated to prevent exposing the user's home directory:

- `/Users/john/.claude/settings.json` → `~/.claude/settings.json`
- Paths outside home directory → `[config path]`

### Error Messages

Error messages are sanitized to prevent information disclosure:

- Parse errors don't expose file contents
- "File not found" errors don't include full paths
- Credential values in error messages are redacted

## Rate Limiting

**Not applicable for stdio transport.**

The MCP server runs locally via stdio transport, meaning:
- Single client connection (the AI agent)
- Inherits the client's filesystem permissions
- No network exposure

Rate limiting would only be needed for potential future HTTP transport modes.

## Security Testing

Security measures are verified by tests in `tests/test_server_security.py`:

- `TestValidateConfigPath` - Path traversal and directory restriction tests
- `TestSanitizePathForOutput` - Path abbreviation tests
- `TestRedactCredentialPreview` - Credential redaction format tests
- `TestSanitizeErrorMessage` - Error message sanitization tests
- `TestAnalyzeConfigSecurity` - Integration tests for analyze_config

## Reporting Security Issues

If you discover a security vulnerability in token-audit, please report it via GitHub Security Advisories:

1. Go to https://github.com/littlebearapps/token-audit/security/advisories
2. Click "New draft security advisory"
3. Provide details of the vulnerability

Do not report security issues via public GitHub Issues.
