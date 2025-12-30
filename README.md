# Token Audit

[![PyPI](https://img.shields.io/pypi/v/token-audit?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/token-audit/)
[![Install Size](https://img.shields.io/badge/install%20size-288%20KB-brightgreen?style=for-the-badge)](https://pypi.org/project/token-audit/)
[![CI](https://img.shields.io/github/actions/workflow/status/littlebearapps/token-audit/ci.yml?branch=main&label=CI&style=for-the-badge&logo=github&logoColor=white)](https://github.com/littlebearapps/token-audit/actions/workflows/ci.yml)
[![codecov](https://img.shields.io/codecov/c/github/littlebearapps/token-audit?style=for-the-badge&logo=codecov&logoColor=white)](https://codecov.io/gh/littlebearapps/token-audit)
[![Socket](https://img.shields.io/badge/Socket-Secured-green?style=for-the-badge&logo=socket.io&logoColor=white)](https://socket.dev/pypi/package/token-audit)

**Know exactly where your AI tokens go.**

Cross-agent token usage and cost auditing for Claude Code, Codex CLI, and Gemini CLI. Use it from the command line, or let your AI agent query it directly via MCP. 100% local, no cloud required.

---

## 🚀 Quick Install

```bash
pipx install token-audit
```

<details>
<summary>Alternative: pip or uv</summary>

```bash
pip install token-audit
# or
uv pip install token-audit
```

</details>

![Token Audit TUI showing token usage and cost analysis](https://raw.githubusercontent.com/littlebearapps/token-audit/main/docs/images/demo.gif)

---

## What's New (v1.0.6)

**Bug Fixes** — 7 stability improvements for CLI commands:

- **Task markers persist correctly** — Fixed critical data loss where markers were overwritten ([#119](https://github.com/littlebearapps/token-audit/issues/119))
- **Sessions list reliability** — `--json` and `--verbose` now show all sessions ([#120](https://github.com/littlebearapps/token-audit/issues/120), [#124](https://github.com/littlebearapps/token-audit/issues/124))
- **Platform name handling** — Hyphenated names (e.g., `claude-code`) work correctly ([#121](https://github.com/littlebearapps/token-audit/issues/121))
- **Collect command robustness** — No more `FileNotFoundError` without project dir ([#122](https://github.com/littlebearapps/token-audit/issues/122))
- **Validate command fixed** — Schema path resolution works in all install modes ([#123](https://github.com/littlebearapps/token-audit/issues/123))

See [v1.0.5](https://github.com/littlebearapps/token-audit/releases/tag/v1.0.5) for task command targeting fix, [v1.0.4](https://github.com/littlebearapps/token-audit/releases/tag/v1.0.4) for Bucket Classification.

---

## Who Benefits

- **MCP developers** — See which tools are expensive, find schema bloat, track unused tools
- **Power users** — Know why sessions auto-compact early, find what's eating tokens
- **Cost-conscious teams** — Track spend across Claude/Codex/Gemini, compare model costs

---

## 🚀 Quick Start

```bash
# Start tracking (auto-detects platform)
token-audit collect
# → Live TUI showing token burn rate, cache ratio, costs

# Browse past sessions with interactive dashboard
token-audit ui
# → Navigate sessions, view recommendations, export for AI analysis

# See daily usage summary
token-audit daily
# → Token counts, costs, and trends by project
```

That's it. Token Audit reads your local session logs and shows you exactly where your tokens go.

<details>
<summary>💡 <strong>Gemini CLI users: Improve token accuracy</strong></summary>

> [!TIP]
> Run `token-audit tokenizer download` for 100% accurate per-tool token counts.
> Without this, Token Audit uses a ~95% accurate fallback estimator.

</details>

Want your AI agent to query usage directly? See [MCP Server Mode](#mcp-server-mode-v100).

**Jump to:** [What It Tracks](#-what-it-tracks) · [Platform Support](#platform-support) · [MCP Server Mode](#mcp-server-mode-v100) · [CLI Reference](#️-cli-reference) · [Roadmap](#roadmap)

---

## 📊 What It Tracks

| Category | What's Tracked |
|----------|----------------|
| **Session totals** | Input, output, cache read/write tokens, and costs |
| **Historical usage** | Daily, weekly, monthly aggregation with project grouping and per-model breakdown |
| **Built-in tools** | Read, Write, Bash, Edit, Grep ([counts vary by platform](docs/features.md#built-in-tools)) |
| **MCP tools** | Any MCP server tool, with per-tool token attribution |
| **MCP servers** | Schema overhead ("context tax") per server |

---

## Platform Support

![Claude Code](https://img.shields.io/badge/Claude%20Code-D97757?style=for-the-badge&logo=claude&logoColor=white)
![OpenAI Codex](https://img.shields.io/badge/Codex%20CLI-412991?style=for-the-badge&logo=openaigym&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Gemini%20CLI-8E75B2?style=for-the-badge&logo=google%20gemini&logoColor=white)

| Platform | Session Accuracy | Per-Tool Accuracy | Guide |
|:---------|:----------------:|:-----------------:|:-----:|
| **Claude Code** | Native (100%) | Native | [→](docs/platforms/claude-code.md) |
| **Codex CLI** | Native (99%+) | Estimated¹ | [→](docs/platforms/codex-cli.md) |
| **Gemini CLI** | Native (100%) | Estimated² | [→](docs/platforms/gemini-cli.md) |

¹ tiktoken `o200k_base` &nbsp; ² Gemma tokenizer (optional download for 100% accuracy)

<details>
<summary><strong>Detailed Capability Matrix</strong></summary>
<br>

| Capability | Claude Code | Codex CLI | Gemini CLI |
|------------|:-----------:|:---------:|:----------:|
| Session tokens | Native | Native | Native |
| Per-tool tokens | Native | Estimated | Estimated |
| Reasoning tokens | Not exposed | o-series | Gemini 2.0+ |
| Cache tracking | Create + Read | Read only | Read only |
| Cost estimates | Accurate | Accurate | Accurate |

**Gemini CLI users:** Run `token-audit tokenizer download` for 100% accurate token counts (otherwise ~95% via fallback).

</details>

---

## Key Features

### 👁️ See — Real-time Visibility

- **Live TUI dashboard** — Token burn rate, cache hit ratio, cost efficiency
- **Per-server breakdown** — Which MCP servers consume the most tokens
- **Per-tool attribution** — Drill down to individual tool calls

### 🧠 Understand — Attribution & Patterns

Token Audit detects "smells" — patterns that signal inefficiency, not errors. These are opportunities to optimize, not problems to fix immediately.

- **4-bucket classification** — Diagnose WHERE tokens go: state serialization (large payloads), redundant outputs (duplicate calls), tool discovery (schema introspection), or conversation drift (reasoning/retries). See [Bucket Classification Guide](docs/bucket-classification.md).
- **12 efficiency smells** — HIGH_VARIANCE, CHATTY, REDUNDANT_CALLS, BURST_PATTERN, and more. For example, CHATTY flags tools that send many small payloads instead of batching, and REDUNDANT_CALLS highlights repeated identical calls that could be cached — both common causes of early compaction.
- **Zombie tool detection** — Find MCP tools defined but never called (wasting schema tokens)
- **Context tax analysis** — See how much schema overhead each MCP server adds per turn

### ⚡ Act — Reports & Exports

- **Historical aggregation** — `token-audit daily`, `weekly`, `monthly` with project grouping
- **AI export** — `token-audit report --format ai` for analysis with your preferred AI
- **Best practices** — `token-audit best-practices` exports 10 curated MCP efficiency patterns

Token Audit is actively developed — see the [roadmap](#roadmap) for burn-rate tracking, billing blocks, and deeper MCP profiling.

---

## MCP Server Mode (v1.0.0)

Run token-audit as an MCP server your AI assistant connects to directly — get efficiency insights without switching terminals.

### Setup

```bash
# Install with server support
pipx install 'token-audit[server]'
```

<details open>
<summary><strong>Claude Code</strong></summary>

Add to `.mcp.json` in your project or `~/.claude/.mcp.json` globally:

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

See [Claude Code setup guide](docs/platforms/claude-code.md) for details.

</details>

<details>
<summary><strong>Codex CLI</strong></summary>

Add to `~/.codex/config.toml` (path may vary by installation):

```toml
[mcp_servers.token-audit]
command = "token-audit-server"
args = []
```

See [Codex CLI setup guide](docs/platforms/codex-cli.md) for details.

</details>

<details>
<summary><strong>Gemini CLI</strong></summary>

Add to `~/.gemini/settings.json` (path may vary by installation):

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

> [!TIP]
> Run `token-audit tokenizer download` for 100% accurate per-tool token counts.

See [Gemini CLI setup guide](docs/platforms/gemini-cli.md) for details.

</details>

#### Test the Connection

After restarting your AI CLI, ask:
- *"Get current token usage metrics"*
- *"Show breakdown by tool"*

### Available Tools (15)

| Tool | Purpose |
|------|---------|
| `start_tracking` | Begin live session monitoring |
| `get_metrics` | Query current token usage, costs, cache stats |
| `get_recommendations` | Get optimization suggestions |
| `analyze_session` | Comprehensive end-of-session analysis |
| `get_best_practices` | Retrieve MCP efficiency patterns |
| `analyze_config` | Analyze MCP config for issues |
| `get_pinned_servers` | Get frequently-used MCP servers |
| `get_trends` | Cross-session pattern analysis (7/30/90 days) |
| `get_daily_summary` | Daily token/cost aggregation with trends |
| `get_weekly_summary` | Weekly usage aggregation |
| `get_monthly_summary` | Monthly usage aggregation |
| `list_sessions` | Query historical sessions with filtering |
| `get_session_details` | Retrieve full session data |
| `pin_server` | Add/remove pinned MCP servers |
| `delete_session` | Remove session from storage |

Tool names and outputs are stable in v1.x. New tools may be added without breaking changes.

### Available Resources (5)

MCP resources provide read-only access to usage data via the resource protocol:

| Resource URI | Description |
|--------------|-------------|
| `token-audit://usage/daily` | Daily usage summary (last 7 days) |
| `token-audit://usage/weekly` | Weekly usage summary (last 4 weeks) |
| `token-audit://usage/monthly` | Monthly usage summary (last 3 months) |
| `token-audit://sessions` | List of recent sessions |
| `token-audit://sessions/{id}` | Detailed session information |

Ask your AI: *"How many tokens have I used? Show me the breakdown by tool."*

See [MCP Server Guide](docs/mcp-server-guide.md) for full documentation.

---

## 🔒 Privacy & Safety

Token Audit is a **passive observer**. It reads local session logs — nothing more.

| Guarantee | Details |
|-----------|---------|
| **No proxies** | Zero interception, zero latency impact |
| **100% local** | All data stays on your machine |
| **No accounts** | Works offline, no cloud sync |
| **No telemetry** | No usage data sent anywhere |
| **Optional pricing API** | LiteLLM pricing fetch can be disabled |

Only token counts and tool names are logged — **prompts and responses are never stored**.

---

## Common Problems Solved

**"Why does my agent auto-compact so quickly?"**
→ Token Audit shows which MCP tools and schemas push sessions over the context threshold.

**"Which MCP tools are expensive?"**
→ The TUI highlights per-tool token usage and flags chatty, high-variance, or burst-pattern tools.

**"What's the 'context tax' of my MCP servers?"**
→ Schema weight analysis shows the token cost of `list_tools` before any work happens.

**"How do I reduce costs in multi-step workflows?"**
→ Use post-session reports to find redundant calls, large payloads, and zombie tools.

---

## Interactive Dashboard

The `token-audit ui` command opens an interactive browser with seven views:

| View | Key | Description |
|------|:---:|-------------|
| Dashboard | `1` | Today's summary, weekly trends, top smells, recent sessions |
| Sessions | `2` | Full session list with filtering, search, and delete |
| Recommendations | `3` | Actionable optimization suggestions by confidence |
| Live | `4` | Real-time session monitoring with burn rate |
| Analytics | `5` | Usage trends by period (daily/weekly/monthly), project grouping |
| Smell Trends | `6` | Pattern frequency over time with severity indicators |
| Pinned Servers | `7` | Frequently-used MCP servers with usage stats |

**Hotkeys:** `j/k` navigate, `Enter` select, `:` command palette, `/` search, `d` date filter, `e` CSV, `x` JSON, `a` AI export, `q` quit.

**Modals:** Press `Delete` to confirm session deletion, use number keys for quick preset selection in date filter modal.

---

## 🛠️ CLI Reference

```bash
token-audit collect    # Live tracking (auto-detects platform)
token-audit ui         # Interactive dashboard
token-audit bucket     # Analyze token distribution by bucket (v1.0.4)
token-audit daily      # Usage summary
token-audit report     # Generate report (markdown/json/csv/ai)
token-audit --help     # Full command list
```

<details>
<summary><strong>All Commands</strong></summary>

### Core Commands

```bash
token-audit collect              # Real-time tracking (auto-detects platform)
token-audit ui                   # Interactive session browser
token-audit report PATH          # Generate report (markdown/json/csv/ai)
token-audit daily                # Daily usage summary
token-audit weekly               # Weekly usage summary
token-audit monthly              # Monthly usage summary
```

### Bucket Classification (v1.0.4)

```bash
token-audit bucket                         # Analyze token distribution by bucket
token-audit bucket --by-task               # Per-task bucket breakdown
token-audit bucket --format json           # JSON output for programmatic use
token-audit task start "Task name"         # Start tracking a logical task
token-audit task end                       # End current task
token-audit task list                      # List completed tasks with breakdown
token-audit task show "Task name"          # Detailed view of specific task
```

### Analysis

```bash
token-audit report PATH --smells           # Smell analysis mode
token-audit report PATH --format ai        # AI-ready export
token-audit best-practices                 # Export efficiency patterns
token-audit validate session.json          # Validate session file
```

### Export

```bash
token-audit export csv                     # Export sessions as CSV
token-audit export json                    # Export sessions as JSON
token-audit export ai                      # Generate AI analysis prompt
token-audit export ai --pinned-focus       # Include pinned server analysis
```

### Session Management

```bash
token-audit sessions list                  # List recent sessions
token-audit sessions show SESSION_ID       # View session details
token-audit sessions delete --older-than 30d  # Clean up old sessions
```

### Configuration

```bash
token-audit tokenizer setup                # Interactive tokenizer setup
token-audit tokenizer download             # Download Gemma tokenizer
token-audit pin SERVER                     # Pin server for focused analysis
```

</details>

<details>
<summary><strong>Command Options</strong></summary>

### collect

```
--platform          Platform: claude-code, codex-cli, gemini-cli, auto
--theme NAME        Color theme: auto, dark, light, mocha, latte, hc-dark, hc-light
--pin-server NAME   Pin server(s) at top of MCP section
--from-start        Include existing session data (Codex/Gemini only)
--quiet             Suppress display output (logs only)
--plain             Plain text output (for CI/logs)
```

### report

```
--format            Output: json, csv, markdown, ai (default: markdown)
--aggregate         Aggregate across multiple sessions
--top-n INT         Number of top tools to show (default: 10)
--smells            Enable smell analysis mode
--pinned-focus      Add dedicated section for pinned servers (with --format ai)
```

### daily/weekly/monthly

```
--platform NAME     Filter: claude-code, codex-cli, gemini-cli
--days/weeks/months Number of periods to show
--json              Output as JSON
--instances         Group by project/instance
--breakdown         Show per-model breakdown
```

</details>

---

<details>
<summary><strong>⚙️ Configuration</strong></summary>

### Pricing

Token Audit fetches current pricing from [LiteLLM API](https://github.com/BerriAI/litellm) (2,000+ models, cached 24h).

To disable and use static pricing only:

```toml
# token-audit.toml
[pricing.api]
enabled = false
```

### Zombie Tool Detection

Configure known tools to detect unused ("zombie") tools:

```toml
# token-audit.toml
[zombie_tools.zen]
tools = ["mcp__zen__thinkdeep", "mcp__zen__debug", "mcp__zen__refactor"]
```

### Themes

```bash
token-audit collect --theme mocha    # Catppuccin Mocha (dark)
token-audit collect --theme latte    # Catppuccin Latte (light)
token-audit collect --theme hc-dark  # High contrast (WCAG AAA)
```

</details>

---

## Data Storage

All data stays local:

| Data | Location |
|------|----------|
| Sessions | `~/.token-audit/sessions/` |
| Config | `./token-audit.toml` or `~/.token-audit/token-audit.toml` |
| Pricing cache | `~/.token-audit/pricing-cache.json` |
| Fallback pricing | `~/.token-audit/fallback-pricing.json` |

---

## Documentation

| Category | Links |
|----------|-------|
| **Getting Started** | [Guide](docs/getting-started.md) |
| **Platform Guides** | [Claude Code](docs/platforms/claude-code.md) · [Codex CLI](docs/platforms/codex-cli.md) · [Gemini CLI](docs/platforms/gemini-cli.md) |
| **Reference** | [MCP Server](docs/mcp-server-guide.md) · [Features](docs/features.md) · [Configuration](docs/configuration.md) · [API](docs/api.md) |
| **Help** | [Troubleshooting](docs/troubleshooting.md) · [FAQ](docs/faq.md) |
| **Examples** | [Debugging Slow Sessions](docs/examples/debugging-slow-session.md) · [All Examples](docs/examples/) |
| **Technical** | [Architecture](docs/architecture.md) · [Data Contract](docs/data-contract.md) · [Changelog](CHANGELOG.md) |

---

## Ecosystem

Token Audit focuses on **real-time tool profiling**. Where billing tools answer *how much*, Token Audit answers *why*. It complements other tools:

| Tool | Best For | Question Answered |
|:-----|:---------|:------------------|
| **Token Audit** | Deep profiling | "Which specific tool is eating my tokens?" |
| **[ccusage](https://github.com/ryoppippi/ccusage)** | Billing history | "How much did I spend last month?" |
| **[Claude Code Usage Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor)** | Session limits | "Will I hit my limit this hour?" |

---

## Roadmap

**Current:** v1.0.6 — 7 bug fixes for CLI stability (sessions list, task markers, validate, collect)

**Upcoming:**
- **v1.1.0** — Billing & Statusline: 5-hour billing block tracking, Claude Code statusline hook
- **v1.2.0** — Burn Rate: Cost projections, progress bars toward limits
- **v1.3.0** — MCP Profiler: Schema waste metrics, tool coverage analysis, spike detection

See [ROADMAP.md](ROADMAP.md) for full details. [Share ideas →](https://github.com/littlebearapps/token-audit/discussions/new?category=ideas)

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- **Bug reports:** [Open an Issue](https://github.com/littlebearapps/token-audit/issues/new?template=bug_report.md)
- **Feature ideas:** [Start a Discussion](https://github.com/littlebearapps/token-audit/discussions/new?category=ideas)
- **Questions:** [Ask in Discussions](https://github.com/littlebearapps/token-audit/discussions/new?category=q-a)

### Development Setup

```bash
git clone https://github.com/littlebearapps/token-audit.git
cd token-audit
pip install -e ".[dev]"
pytest
```

---

## License

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)

MIT License — see [LICENSE](LICENSE) for details.

**Third-Party:**
- [tiktoken](https://github.com/openai/tiktoken) (MIT) — Codex CLI token estimation
- [Gemma tokenizer](https://huggingface.co/google/gemma-2-2b) (Apache 2.0) — Optional, see [license terms](docs/gemma-tokenizer-license.md)

---

**Made with 🐻 by [Little Bear Apps](https://littlebearapps.com)**
