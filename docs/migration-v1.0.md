# Migration Guide: v0.9.x to v1.0

This guide covers upgrading token-audit from v0.9.x to v1.0.0.

**Good news: v1.0.0 has no breaking changes.** All existing functionality works exactly as before. The main addition is MCP Server Mode.

---

## What's New in v1.0.0

### MCP Server Mode (NEW)

Run token-audit as an MCP server your AI assistant connects to directly:

- **8 MCP tools** for real-time monitoring and analysis
- **Natural language access** to metrics, recommendations, and best practices
- **Configuration analysis** with context tax estimation
- **Cross-session trend analysis** over 7/30/90 days
- **Works with** Claude Code, Codex CLI, and Gemini CLI

See [MCP Server Guide](mcp-server-guide.md) for full documentation.

### Stability Improvements from v0.9.x

v1.0.0 includes all the stability work from v0.9.x:

- **Performance optimization** — Sub-millisecond TUI refresh
- **API stability tiers** — 30 public exports with explicit stability guarantees
- **Tiered pricing** — Support for Claude/Gemini token threshold pricing
- **Performance benchmarks** — 14 CI-integrated benchmark tests

---

## Upgrade Steps

### 1. Upgrade the Package

```bash
# pipx (recommended)
pipx upgrade token-audit

# pip
pip install --upgrade token-audit

# uv
uv pip install --upgrade token-audit
```

### 2. (Optional) Enable MCP Server Mode

If you want to use MCP Server Mode, install with server extras:

```bash
# pipx
pipx install 'token-audit[server]' --force

# pip
pip install 'token-audit[server]'
```

Then configure your AI CLI. See [Quick Setup](#quick-mcp-server-setup) below.

### 3. Verify Upgrade

```bash
token-audit --version
# Expected: token-audit 1.0.0
```

---

## Quick MCP Server Setup

Add to your AI CLI configuration:

**Claude Code** (`.mcp.json`):

```json
{
  "mcpServers": {
    "token-audit": {
      "command": "token-audit-server",
      "args": []
    }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`):

```toml
[mcp_servers.token-audit]
command = "token-audit-server"
args = []
```

**Gemini CLI** (`~/.gemini/settings.json`):

```json
{
  "mcpServers": {
    "token-audit": {
      "command": "token-audit-server",
      "args": []
    }
  }
}
```

---

## No Breaking Changes

v1.0.0 is **fully backward compatible** with v0.9.x:

| Component | Status |
|-----------|--------|
| CLI commands | Unchanged |
| `token-audit collect` | Works the same |
| `token-audit report` | Works the same |
| `token-audit ui` | Works the same |
| `token-audit export` | Works the same |
| Session file format | Compatible |
| Configuration format | Compatible |
| Python API | Compatible |

Your existing workflows, scripts, and configurations will continue to work without modification.

---

## Deprecation Notes

### From v0.9.x

The following was deprecated in v0.9.0 and will be removed in v1.1.0:

- **`estimate_tool_tokens`** function
  - Use `TokenEstimator.estimate_tool_call()` instead
  - See [api-stability.md](api-stability.md) for migration details

---

## FAQ

### Do I need to migrate anything?

**No.** v1.0.0 is additive. All existing functionality works without changes.

### Is MCP Server Mode required?

**No.** MCP Server Mode is optional. You can continue using CLI mode (`token-audit collect`) exactly as before.

### Can I use both modes together?

**Yes.** CLI mode and MCP Server Mode work independently:
- CLI mode runs in a separate terminal with the TUI
- MCP Server Mode runs within your AI CLI session

### Do I need to update my session files?

**No.** Session file format is unchanged and backward compatible.

### Do I need to update my token-audit.toml?

**No.** Configuration format is unchanged.

### What if I have automation using the Python API?

**No changes needed.** All public APIs maintain backward compatibility.

---

## Getting Help

- **Documentation**: [MCP Server Guide](mcp-server-guide.md)
- **Troubleshooting**: [Troubleshooting Guide](troubleshooting.md)
- **Questions**: [GitHub Discussions](https://github.com/littlebearapps/token-audit/discussions)
- **Bugs**: [GitHub Issues](https://github.com/littlebearapps/token-audit/issues)

---

## See Also

- [Changelog](../CHANGELOG.md) — Full version history
- [MCP Server Guide](mcp-server-guide.md) — MCP server mode documentation
- [API Stability](api-stability.md) — API stability tiers and guarantees
