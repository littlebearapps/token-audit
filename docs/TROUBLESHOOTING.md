# Troubleshooting Guide

Common issues and solutions for MCP Audit. For quick answers, see [FAQ](FAQ.md).

---

## Quick Diagnostics

Run this first to check your setup:

```bash
mcp-audit init
```

This shows:
- Configuration file status
- Pricing source and cache status
- Tokenizer availability

---

## Installation Issues

### pip install fails with "externally-managed-environment"

**Error:**
```
error: externally-managed-environment
This environment is externally managed
```

**Cause:** Your system Python is managed by the OS (common on Ubuntu 23.04+, Fedora 38+).

**Solution:** Use pipx instead:
```bash
pipx install mcp-audit
```

Or create a virtual environment:
```bash
python3 -m venv ~/.mcp-audit-venv
source ~/.mcp-audit-venv/bin/activate
pip install mcp-audit
```

### pipx not found

**Solution:** Install pipx:
```bash
# macOS
brew install pipx
pipx ensurepath

# Ubuntu/Debian
sudo apt install pipx
pipx ensurepath

# Then restart your terminal
```

### Python version too old

**Error:**
```
Requires Python >=3.8, but you have 3.7
```

**Solution:** Install Python 3.8+:
```bash
# macOS
brew install python@3.11

# Ubuntu
sudo apt install python3.11
```

### Permission denied during install

**Error:**
```
PermissionError: [Errno 13] Permission denied
```

**Solution:** Don't use `sudo pip`. Use pipx or a virtual environment:
```bash
pipx install mcp-audit
```

---

## Tracking Issues

### "No events detected" / "Waiting for events..."

**Possible causes:**

1. **Started MCP Audit after the agent**
   - Solution: Start `mcp-audit collect` first, then start your AI agent

2. **Wrong platform specified**
   - Solution: Verify `--platform` matches your agent:
     ```bash
     mcp-audit collect --platform claude-code  # Not codex-cli
     ```

3. **Wrong directory**
   - Solution: Run MCP Audit from your project directory:
     ```bash
     cd /path/to/your/project
     mcp-audit collect
     ```

4. **Session file not updating**
   - Claude Code: Check `~/.claude/projects/*/session.json` exists
   - Codex CLI: Check `~/.codex/` for session files
   - Gemini CLI: Check `~/.gemini/` for session files

### Session not saving

**Symptoms:** Session completes but no file in `~/.mcp-audit/sessions/`

**Causes & Solutions:**

1. **Used `--no-logs` flag**
   - This intentionally skips saving. Remove the flag.

2. **Permission issue**
   - Check: `ls -la ~/.mcp-audit/`
   - Fix: `chmod 755 ~/.mcp-audit/`

3. **Disk full**
   - Check: `df -h ~`
   - Free up space

### Wrong platform detected

**Symptom:** MCP Audit detects Claude Code when you're using Codex CLI (or vice versa).

**Solution:** Specify platform explicitly:
```bash
mcp-audit collect --platform codex-cli
```

### TUI not updating

**Symptoms:** TUI shows activity but numbers don't change.

**Causes & Solutions:**

1. **No new tool calls**
   - The TUI updates on tool calls. If you're just chatting (no tools), counts won't change.

2. **Terminal too small**
   - Resize terminal to at least 80×24 characters

3. **Slow file system**
   - Network drives can cause delays. Work on local disk.

---

## Platform-Specific Issues

### Claude Code

#### "Could not find session file"

**Cause:** Claude Code stores sessions by project hash. MCP Audit may not find the correct one.

**Solution:**
1. Ensure you're in the same directory as your Claude Code session
2. Check session exists:
   ```bash
   ls ~/.claude/projects/*/session.json
   ```

#### Debug log permissions

**Cause:** Claude Code's debug.log may have restricted permissions.

**Solution:**
```bash
chmod 644 ~/.claude/debug.log
```

### Codex CLI

#### "No session files found"

**Cause:** Codex CLI stores sessions in `~/.codex/` with unique identifiers.

**Solution:**
1. Check Codex session directory exists:
   ```bash
   ls ~/.codex/
   ```
2. Start a new Codex session to generate fresh files

#### Per-tool tokens showing 0

**Expected behavior:** Codex CLI provides session-level tokens only. Per-tool attribution is estimated.

If session tokens are also 0, the session file may not be updating. Try restarting Codex CLI.

### Gemini CLI

#### "Estimated (tiktoken)" instead of Gemma

**Cause:** Gemma tokenizer not installed.

**Solution:**
```bash
mcp-audit tokenizer download
```

Verify:
```bash
mcp-audit tokenizer status
```

#### Tokenizer download fails

**Causes:**
1. **Network issue**
   - Check internet connection
   - Try: `curl -I https://github.com`

2. **Firewall blocking GitHub**
   - Download manually from [Releases](https://github.com/littlebearapps/mcp-audit/releases)
   - Place in `~/.mcp-audit/tokenizers/`

3. **Disk space**
   - Tokenizer requires ~4MB
   - Check: `df -h ~`

---

## Pricing Issues

### "No pricing data available"

**Cause:** API disabled and no TOML config found.

**Solution:** Enable API pricing:
```toml
# ~/.mcp-audit/mcp-audit.toml
[pricing.api]
enabled = true
```

Or add TOML pricing manually. See [Configuration](CONFIGURATION.md#pricing-configuration).

### Network errors fetching pricing

**Error:**
```
WARNING: Could not fetch pricing from API
```

**Cause:** Firewall or network blocking GitHub raw content.

**Solutions:**

1. **Use offline mode:**
   ```toml
   [pricing.api]
   enabled = true
   offline_mode = true
   ```

2. **Check network:**
   ```bash
   curl -I https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
   ```

3. **Use cached data:** If you previously fetched pricing, the cache at `~/.mcp-audit/pricing-cache.json` will be used.

### Stale pricing data

**Symptom:** Costs seem wrong for newer models.

**Cause:** Cache expired and API fetch failed.

**Solution:**
```bash
# Clear cache to force refresh
rm ~/.mcp-audit/pricing-cache.json
mcp-audit init
```

### "TOML support not available"

**Cause:** `toml` package not installed (Python 3.8-3.10).

**Solution:**
```bash
pip install toml
```

Note: Python 3.11+ has built-in `tomllib` (no installation needed).

---

## Report/Export Issues

### Empty reports

**Symptom:** `mcp-audit report` shows no data.

**Causes:**

1. **No sessions saved**
   - Check: `ls ~/.mcp-audit/sessions/`
   - If empty, track a session first

2. **Wrong path**
   - Default: `~/.mcp-audit/sessions/`
   - Specify explicitly: `mcp-audit report ~/.mcp-audit/sessions/`

3. **Filter too restrictive**
   - Try without filters first

### JSON parsing errors

**Error:**
```
JSONDecodeError: Expecting value
```

**Cause:** Corrupted session file.

**Solutions:**

1. **Identify bad file:**
   ```bash
   for f in ~/.mcp-audit/sessions/**/*.json; do
     python3 -c "import json; json.load(open('$f'))" || echo "Bad: $f"
   done
   ```

2. **Remove or fix corrupted file**

3. **Prevent future corruption:** Don't kill mcp-audit with `kill -9`. Use `Ctrl+C` for graceful shutdown.

### Export truncated

**Symptom:** AI export seems incomplete.

**Cause:** Large session truncated for AI context limits.

**Solution:** Export as JSON for full data:
```bash
mcp-audit export ai-prompt --format json
```

---

## Display Issues

### Unicode characters not rendering

**Symptom:** Box-drawing characters appear as question marks or garbage.

**Cause:** Terminal doesn't support Unicode.

**Solutions:**

1. **Use plain mode:**
   ```bash
   mcp-audit collect --plain
   ```

2. **Change terminal:** Use iTerm2 (macOS), Windows Terminal, or any UTF-8 capable terminal

3. **Set locale:**
   ```bash
   export LANG=en_US.UTF-8
   ```

### Colors too bright/dim

**Solution:** Use a different theme:
```bash
# High contrast
mcp-audit collect --theme hc-dark

# Or disable colors entirely
NO_COLOR=1 mcp-audit collect
```

### TUI doesn't fit terminal

**Solution:** Resize terminal to at least 80 columns × 24 rows.

For smaller terminals, use plain mode:
```bash
mcp-audit collect --plain
```

---

## Performance Issues

### High CPU usage

**Symptom:** `mcp-audit` using significant CPU during tracking.

**Cause:** Aggressive file polling on slow file system.

**Solutions:**

1. **Work on local disk** (not network drive)

2. **Check for large session files:**
   ```bash
   du -sh ~/.mcp-audit/sessions/
   ```

3. **Clear old sessions if very large**

### Slow startup

**Symptom:** `mcp-audit` takes several seconds to start.

**Causes:**

1. **Many session files** — Clear old sessions
2. **Network timeout** — Enable offline mode
3. **Slow tokenizer load** — First run after install is slower

---

## Getting Help

### Information to include in bug reports

When opening a [GitHub Issue](https://github.com/littlebearapps/mcp-audit/issues):

```bash
# Version info
mcp-audit --version
python3 --version

# Platform
uname -a

# Configuration status
mcp-audit init
```

Plus:
- Steps to reproduce
- Expected vs actual behavior
- Full error message (if any)
- Relevant session file (with sensitive data removed)

### Community support

- [GitHub Discussions](https://github.com/littlebearapps/mcp-audit/discussions) — Questions and ideas
- [GitHub Issues](https://github.com/littlebearapps/mcp-audit/issues) — Bug reports

---

*For quick answers, see [FAQ](FAQ.md). For configuration help, see [Configuration](CONFIGURATION.md).*
