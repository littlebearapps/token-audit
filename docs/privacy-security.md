# Privacy & Security

Token Audit is designed with privacy as a core principle. This document explains what data is collected, how it's stored, and what controls you have.

---

## Table of Contents

1. [Data Collection Philosophy](#data-collection-philosophy)
2. [What We Collect](#what-we-collect)
3. [What We DON'T Collect](#what-we-dont-collect)
4. [Local-Only Operation](#local-only-operation)
5. [Redaction Hooks](#redaction-hooks)
6. [Data Storage Security](#data-storage-security)
7. [Sharing Session Data](#sharing-session-data)
8. [Configuration Options](#configuration-options)

---

## Data Collection Philosophy

### Minimum Necessary

Token Audit collects only the minimum data needed to provide usage insights:

- ✅ **Token counts** - How many tokens were used
- ✅ **Tool names** - Which MCP tools were called
- ✅ **Timestamps** - When events occurred
- ❌ **NOT prompts** - What you asked
- ❌ **NOT responses** - What the AI said
- ❌ **NOT file contents** - What files were read/written

### Why This Matters

Your AI coding conversations may contain:
- Proprietary code
- Business logic
- Authentication details
- Personal information
- Confidential project details

Token Audit is designed so you can safely track usage without exposing this sensitive content.

---

## What We Collect

### Token Usage Events

```json
{
  "event_type": "token_usage",
  "timestamp": "2025-11-25T10:30:45.123Z",
  "data": {
    "input_tokens": 1234,
    "output_tokens": 567,
    "cache_created_tokens": 890,
    "cache_read_tokens": 12345,
    "model": "claude-sonnet-4"
  }
}
```

**Collected:**
- Token counts (input, output, cache)
- Model identifier
- Timestamp

**NOT collected:**
- Actual prompt content
- Response content
- Conversation context

### Tool Call Events

```json
{
  "event_type": "tool_call",
  "timestamp": "2025-11-25T10:30:46.456Z",
  "data": {
    "tool_name": "mcp__zen__chat",
    "server": "zen",
    "tokens_used": 2345,
    "duration_ms": 1234
  }
}
```

**Collected:**
- Tool name (e.g., `mcp__zen__chat`)
- Server identifier
- Token usage for the call
- Duration (optional)

**NOT collected:**
- Tool input parameters
- Tool output content
- Arguments passed to tools

### Session Metadata

```json
{
  "event_type": "session_metadata",
  "timestamp": "2025-11-25T10:30:00.000Z",
  "data": {
    "session_id": "session-20251125T103000-abc123",
    "platform": "claude_code",
    "project": "my-project",
    "working_directory": "/Users/name/projects/my-project"
  }
}
```

**Collected:**
- Session identifier (randomly generated)
- Platform name
- Project name (directory name by default)
- Working directory path

**Optionally redacted:**
- Project name (can be anonymized)
- Working directory (can be stripped)

---

## What We DON'T Collect

### Never Stored

The following data is **never** written to disk by Token Audit:

| Data Type | Reason |
|-----------|--------|
| Prompt content | May contain sensitive information |
| Response content | May contain generated code/secrets |
| File contents | Proprietary code |
| Tool arguments | May contain file paths, queries |
| Tool outputs | May contain sensitive data |
| API keys | Security risk |
| Error details | May expose internal state |

### Example: What Gets Stripped

**Original event (internal):**
```json
{
  "tool": "mcp__brave-search__web",
  "input": {
    "query": "how to authenticate with internal-api.company.com"
  },
  "output": {
    "results": [...]
  }
}
```

**What gets stored:**
```json
{
  "event_type": "tool_call",
  "data": {
    "tool_name": "mcp__brave-search__web",
    "server": "brave-search",
    "tokens_used": 5432
  }
}
```

The query content and search results are **not stored**.

---

## Local-Only Operation

### No Cloud Communication

Token Audit operates entirely on your local machine:

```
Your Machine
┌─────────────────────────────────────────────────────┐
│                                                     │
│  Claude Code/Codex ──► Token Audit ──► Local Storage │
│                                                     │
│  ~/.token-audit/sessions/                            │
│                                                     │
└─────────────────────────────────────────────────────┘
                           │
                           ✗ No internet required
                           ✗ No data sent externally
                           ✗ No cloud storage
                           ✗ No telemetry
```

### What This Means

- ✅ Works offline
- ✅ Data never leaves your machine
- ✅ No account required
- ✅ No telemetry or analytics
- ✅ No external dependencies after installation

### Network Usage

Token Audit itself makes **zero network requests**. The only network usage is:

1. **Installation** (`pip install token-audit`) - Downloads package from PyPI
2. **Updates** (`pip install --upgrade token-audit`) - Downloads newer version

After installation, Token Audit is fully offline-capable.

---

## Redaction Hooks

Token Audit provides hooks to customize what data is stored.

### Built-in Redaction

Default redaction applied automatically:

```python
# Built-in redaction rules
DEFAULT_REDACTION = {
    "strip_tool_inputs": True,      # Remove tool arguments
    "strip_tool_outputs": True,     # Remove tool responses
    "strip_prompt_content": True,   # Remove prompts (if present)
    "strip_response_content": True, # Remove AI responses (if present)
}
```

### Custom Redaction Hooks

Create `~/.token-audit/config/redaction.py`:

```python
"""Custom redaction hooks for Token Audit."""

def redact_event(event: dict) -> dict:
    """
    Custom redaction function called for every event.

    Args:
        event: Raw event data

    Returns:
        Redacted event (modify in place or return new dict)
    """
    # Example: Remove working directory path
    if "working_directory" in event.get("data", {}):
        event["data"]["working_directory"] = "[REDACTED]"

    # Example: Anonymize project names
    if "project" in event.get("data", {}):
        event["data"]["project"] = hash_project_name(event["data"]["project"])

    return event

def redact_session_metadata(metadata: dict) -> dict:
    """
    Redact session-level metadata.

    Args:
        metadata: Session metadata dict

    Returns:
        Redacted metadata
    """
    # Example: Remove user-identifying information
    sensitive_keys = ["username", "email", "user_id"]
    for key in sensitive_keys:
        if key in metadata:
            del metadata[key]

    return metadata

def hash_project_name(name: str) -> str:
    """Hash a project name for anonymization."""
    import hashlib
    return f"project-{hashlib.sha256(name.encode()).hexdigest()[:8]}"
```

### Configuration File

Enable custom redaction in `~/.token-audit/config/token-audit.toml`:

```toml
[privacy]
# Enable custom redaction hooks
custom_redaction = true
redaction_module = "~/.token-audit/config/redaction.py"

# Built-in redaction options
strip_working_directory = false  # Default: false
anonymize_project_names = false  # Default: false
strip_timestamps = false         # Default: false (breaks time analysis)
```

### Redaction Levels

Choose a redaction level based on your needs:

| Level | Description | Use Case |
|-------|-------------|----------|
| **minimal** | Token counts only | Maximum privacy |
| **standard** | + Tool names, timestamps | Typical usage (default) |
| **detailed** | + Project names, paths | Full analysis |
| **custom** | Your redaction hooks | Specific requirements |

Configure in `token-audit.toml`:

```toml
[privacy]
redaction_level = "standard"  # minimal, standard, detailed, custom
```

---

## Data Storage Security

### File Permissions

Token Audit creates files with secure permissions:

```bash
# Session files: Owner read/write only
-rw------- user  staff  sessions/session-xxx.jsonl

# Config directory: Owner access only
drwx------ user  staff  ~/.token-audit/
```

### Storage Location

Default: `~/.token-audit/sessions/`

All data is stored in your home directory, protected by your system's user permissions.

### Custom Storage Location

For additional security, you can specify a custom location:

```bash
# Use encrypted volume
token-audit collect --output /Volumes/EncryptedDrive/token-audit/

# Use per-project storage
token-audit collect --output ./local-audit/
```

### Encryption

Token Audit does not encrypt data at rest (files are plaintext JSON). For sensitive environments, consider:

1. **Encrypted home directory** - macOS FileVault, Linux LUKS
2. **Encrypted volume** - Store sessions on encrypted partition
3. **File-level encryption** - Encrypt session files with age, gpg

Example with age encryption:

```bash
# Encrypt session after tracking
age -r age1... session.jsonl > session.jsonl.age
rm session.jsonl

# Decrypt for analysis
age -d -i key.txt session.jsonl.age > session.jsonl
```

---

## Sharing Session Data

### When You Might Share

- Bug reports
- Performance analysis help
- Research collaboration

### Safe Sharing Checklist

Before sharing session data:

1. ✅ Review the JSONL file for any sensitive content
2. ✅ Run additional redaction if needed
3. ✅ Remove or anonymize project names
4. ✅ Strip file paths if they contain sensitive info
5. ✅ Consider sharing aggregated summaries instead

### Sanitization Script

Use the built-in sanitization tool:

```bash
# Sanitize a session for sharing
token-audit sanitize session.jsonl --output sanitized.jsonl

# Options
token-audit sanitize session.jsonl \
    --anonymize-projects \
    --strip-paths \
    --strip-timestamps \
    --output safe-to-share.jsonl
```

### Example: Sanitized Session

**Original:**
```json
{
  "session_id": "session-20251125T103045-abc123",
  "project": "secret-project",
  "working_directory": "/Users/john/work/secret-project",
  "tool_calls": [...]
}
```

**Sanitized:**
```json
{
  "session_id": "session-xxxxxxxx-000000",
  "project": "project-a1b2c3d4",
  "working_directory": "[REDACTED]",
  "tool_calls": [...]
}
```

---

## Configuration Options

### Privacy-Related Settings

`~/.token-audit/config/token-audit.toml`:

```toml
[privacy]
# Redaction level: minimal, standard, detailed, custom
redaction_level = "standard"

# Strip working directory from session metadata
strip_working_directory = false

# Anonymize project names (hash them)
anonymize_project_names = false

# Custom redaction module path
custom_redaction = false
redaction_module = ""

[storage]
# Base directory for sessions
base_dir = "~/.token-audit/sessions"

# File permissions (octal)
file_mode = "0600"
dir_mode = "0700"

[telemetry]
# Token Audit has no telemetry, but this explicitly disables any future options
enabled = false
```

### Environment Variables

```bash
# Override storage location
export TOKEN_AUDIT_BASE_DIR="/secure/location/token-audit"

# Set redaction level
export TOKEN_AUDIT_REDACTION_LEVEL="minimal"

# Disable all metadata storage
export TOKEN_AUDIT_MINIMAL_MODE="true"
```

---

## Security Best Practices

### For Individual Users

1. **Use default redaction** - Don't disable built-in privacy protections
2. **Review before sharing** - Check session files before sending to others
3. **Encrypt if needed** - Use disk encryption for sensitive work
4. **Regular cleanup** - Delete old sessions you no longer need

### For Teams

1. **Establish data policy** - Define what can be tracked
2. **Use custom redaction** - Match your organization's requirements
3. **Centralize storage** - Use team-accessible encrypted storage
4. **Audit access** - Monitor who accesses session data

### For Open Source Projects

1. **Don't commit sessions** - Add `~/.token-audit/` to global gitignore
2. **Sanitize examples** - Use sanitization tool before sharing
3. **Document policies** - Tell contributors what's tracked

---

## Questions?

If you have privacy or security concerns:

1. **Review source code** - Token Audit is open source
2. **Open an issue** - [GitHub Issues](https://github.com/littlebearapps/token-audit/issues)
3. **Start a discussion** - [GitHub Discussions](https://github.com/littlebearapps/token-audit/discussions)

---

## Summary

| Aspect | Status |
|--------|--------|
| Prompt/response content | ❌ Never collected |
| Tool arguments | ❌ Never collected |
| Token counts | ✅ Collected |
| Tool names | ✅ Collected |
| Network requests | ❌ None (local-only) |
| Telemetry | ❌ None |
| Redaction hooks | ✅ Available |
| Encryption | ✅ Use system-level |

**Token Audit is designed to help you optimize costs without compromising your privacy.**
