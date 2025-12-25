# Frequently Asked Questions

Common questions about Token Audit. For detailed troubleshooting, see [Troubleshooting](troubleshooting.md).

---

## General

### What is Token Audit?

Token Audit is a real-time token profiler for MCP (Model Context Protocol) servers and tools. It helps you understand which tools consume your tokens, diagnose context bloat, and optimize your AI coding sessions.

### Who is Token Audit for?

**MCP Tool Developers**: Build efficient MCP servers with visibility into token consumption patterns.

**AI Coding Power Users**: Understand why Claude Code, Codex CLI, or Gemini CLI auto-compacts or hits context limits.

### Is Token Audit free?

Yes. Token Audit is free and open-source under the MIT license. There are no paid tiers.

### Does Token Audit work offline?

Mostly yes:
- **Token tracking**: Works completely offline
- **Session storage**: Local only
- **Pricing data**: By default fetches from LiteLLM API, but can be configured for offline mode with `offline_mode = true` in config

---

## Installation & Setup

### Which Python versions are supported?

Python 3.8, 3.9, 3.10, 3.11, 3.12, and 3.13.

### Should I use pipx, pip, or uv?

**pipx (recommended)**: Installs in isolated environment, prevents dependency conflicts.

**pip**: Works fine if you manage your own virtual environments.

**uv**: Fast alternative to pip, same behavior.

```bash
# Recommended
pipx install token-audit

# Alternatives
pip install token-audit
uv pip install token-audit
```

### Do I need to configure anything before using Token Audit?

No. Token Audit works out of the box with sensible defaults:
- Auto-detects your platform
- Fetches model pricing automatically
- Saves sessions to `~/.token-audit/sessions/`

Configuration is optional for customization (themes, zombie tools, pricing overrides).

### How do I update to the latest version?

```bash
# pipx
pipx upgrade token-audit

# pip
pip install --upgrade token-audit

# uv
uv pip install --upgrade token-audit
```

### How do I uninstall Token Audit?

```bash
# pipx
pipx uninstall token-audit

# pip
pip uninstall token-audit
```

Session data remains in `~/.token-audit/` — delete manually if desired.

---

## Privacy & Security

### What data does Token Audit collect?

Token Audit logs:
- **Token counts**: Input, output, cached tokens per tool
- **Tool names**: Which MCP tools were called
- **Timestamps**: When calls occurred
- **Model names**: Which AI model was used

Token Audit does **NOT** log:
- Prompts or responses
- File contents
- Conversation text
- Any PII

### Does Token Audit send data to the cloud?

**Token data**: Never sent anywhere. All session data stays in `~/.token-audit/`.

**Pricing data**: By default, fetches model pricing from LiteLLM's public GitHub repo (cached 24h). No usage data is sent. Disable with `[pricing.api] enabled = false`.

### Can I use Token Audit with confidential projects?

Yes. Token Audit is designed for privacy:
- No prompts or responses stored
- No network transmission of usage data
- All data in local files you control

Review [Privacy & Security](privacy-security.md) for details.

### How do I delete my session data?

```bash
# Delete all sessions
rm -rf ~/.token-audit/sessions/

# Delete specific platform
rm -rf ~/.token-audit/sessions/claude_code/

# Delete specific date
rm -rf ~/.token-audit/sessions/claude_code/2025-01-15/
```

---

## Token Tracking

### How accurate is token estimation for Codex CLI and Gemini CLI?

**Very accurate**:

| Platform | Tokenizer | Session Accuracy | Per-Tool Accuracy |
|----------|-----------|------------------|-------------------|
| Claude Code | Native (Anthropic) | 100% | 100% |
| Codex CLI | tiktoken (o200k_base) | 99%+ | Estimated |
| Gemini CLI | Gemma tokenizer | 100% | Estimated |
| Gemini CLI | tiktoken fallback | ~95% | Estimated |

Per-tool token counts are estimated for Codex and Gemini because these platforms don't expose per-tool attribution natively.

### Why am I seeing 0 tokens or no activity?

1. **Started Token Audit after the agent**: Only new activity is tracked. Start `token-audit collect` first, then your agent.

2. **Wrong directory**: Token Audit looks for session files based on current working directory. `cd` to your project folder.

3. **No MCP tools used yet**: Built-in tools (Read, Write, Bash) are tracked separately. Use an MCP tool to see activity.

4. **Platform mismatch**: Ensure `--platform` matches your actual agent (`claude-code`, `codex-cli`, `gemini-cli`).

### What is "context tax"?

Context tax is the static token overhead from MCP server schemas. Every MCP server consumes tokens just by existing in your context:

- Tool definitions are loaded before any work begins
- More servers = more overhead
- A typical server with 10 tools consumes ~1,750 tokens

Token Audit measures this and shows it in the "Context Tax" panel.

### What are "zombie tools"?

Zombie tools are MCP tools defined in server schemas but never called during a session. They consume context tokens without providing value.

Configure known tools in `token-audit.toml` to detect zombies:

```toml
[zombie_tools.zen]
tools = ["mcp__zen__thinkdeep", "mcp__zen__debug"]
```

### What are "reasoning tokens"?

Reasoning tokens (also called "thinking tokens") are tokens used by the model's internal reasoning process, separate from visible output:

- **OpenAI O-series models**: Uses reasoning tokens for chain-of-thought
- **Gemini 2.0+**: Uses "thoughts" field for reasoning

Token Audit tracks these separately when available.

---

## Costs & Pricing

### Where does Token Audit get pricing data?

By default, from the [LiteLLM pricing database](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json) which tracks 2,000+ models across major providers.

Pricing is cached locally for 24 hours. You can also configure custom pricing in `token-audit.toml`.

### How do I add custom model pricing?

Add to your `token-audit.toml`:

```toml
[pricing.custom]
"my-model-name" = { input = 2.0, output = 10.0 }
```

Prices are USD per million tokens.

### Why do my costs differ from my provider's bill?

Token Audit shows **estimated** costs based on:
- Token counts (may be estimated for some platforms)
- Published model pricing (may differ from negotiated rates)
- Cache pricing assumptions

Your provider's bill is authoritative. Token Audit is for relative comparisons and optimization, not exact billing.

### How do I use it without network access?

Enable offline mode:

```toml
[pricing.api]
enabled = true
offline_mode = true
```

This uses cached pricing or TOML configuration only.

---

## Platform-Specific

### Can I track multiple platforms simultaneously?

Yes, run separate `token-audit collect` instances:

```bash
# Terminal 1
token-audit collect --platform claude-code

# Terminal 2
token-audit collect --platform codex-cli
```

Sessions are stored separately by platform.

### Does Token Audit work with Cursor?

Not directly. Cursor uses its own session format. If Cursor's internals change to expose MCP-compatible session data, support could be added.

[Start a discussion](https://github.com/littlebearapps/token-audit/discussions) if you're interested.

### Will Token Audit support Ollama CLI?

Yes, planned for v1.1.0. Ollama CLI uses a different session format that requires a dedicated adapter.

See [Roadmap](../ROADMAP.md) for timeline.

### Why doesn't my platform show per-tool token counts?

Only Claude Code provides native per-tool token attribution. Codex CLI and Gemini CLI provide session-level tokens only.

Token Audit estimates per-tool attribution for these platforms using tokenizers, which is highly accurate but not exact.

---

## Integration

### Can I integrate Token Audit with CI/CD?

Yes, use headless mode:

```bash
token-audit collect --platform codex-cli --plain --quiet
```

Parse JSON output programmatically:

```bash
token-audit report --format json | jq '.total_cost'
```

See [CI/CD Integration Example](examples/ci-cd-integration.md) for patterns.

### Is there an API for programmatic access?

Token Audit is primarily a CLI tool. Basic programmatic usage is possible:

```python
from token_audit.storage import StorageManager

storage = StorageManager()
sessions = storage.list_sessions(platform="claude_code")
```

See [API Reference](api.md) for details. Note: The API surface is not yet stable before v1.0.0.

### Can I export data for AI analysis?

Yes, the AI export is designed exactly for this:

```bash
token-audit report --format ai > analysis.md
```

Then paste into Claude, ChatGPT, or any AI assistant with prompts like:
- "Analyze this session for optimization opportunities"
- "What patterns suggest context bloat?"
- "Recommend changes to my MCP configuration"

---

## Troubleshooting

### Where can I get help?

1. [Troubleshooting Guide](troubleshooting.md) — Common issues
2. [GitHub Discussions](https://github.com/littlebearapps/token-audit/discussions) — Questions
3. [GitHub Issues](https://github.com/littlebearapps/token-audit/issues) — Bug reports

### How do I report a bug?

Open an issue at [GitHub Issues](https://github.com/littlebearapps/token-audit/issues) with:
- Token Audit version (`token-audit --version`)
- Python version (`python3 --version`)
- Platform (Claude Code, Codex CLI, Gemini CLI)
- Steps to reproduce
- Error messages or unexpected behavior

### How do I request a feature?

Start a discussion at [GitHub Discussions](https://github.com/littlebearapps/token-audit/discussions/new?category=ideas).

Feature requests are tracked there before becoming Issues for implementation.

---

*For detailed troubleshooting, see [Troubleshooting](troubleshooting.md). For feature details, see [Feature Reference](features.md).*
