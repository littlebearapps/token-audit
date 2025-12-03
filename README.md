# MCP Audit

**Are your MCP tools eating context and you don't know which ones?**

Whether you're building your own MCP servers or using Claude Code, Codex CLI, or Gemini CLI daily, mcp-audit shows you exactly where tokens go—per server, per tool, in real-time. Investigate and fix context bloat and high token usage at the source.

```bash
pip install mcp-audit
```

[![PyPI version](https://img.shields.io/pypi/v/mcp-audit.svg)](https://pypi.org/project/mcp-audit/)
[![PyPI downloads](https://img.shields.io/pypi/dm/mcp-audit.svg)](https://pypi.org/project/mcp-audit/)
[![Python 3.8+](https://img.shields.io/pypi/pyversions/mcp-audit.svg)](https://pypi.org/project/mcp-audit/)
[![CI](https://img.shields.io/github/actions/workflow/status/littlebearapps/mcp-audit/ci.yml?branch=main&label=CI)](https://github.com/littlebearapps/mcp-audit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

![MCP Audit real-time TUI showing token usage per MCP server and tool](https://raw.githubusercontent.com/littlebearapps/mcp-audit/main/docs/images/demo.gif)

> Real-time token tracking per MCP server and tool—see exactly what's eating your context.

<details>
<summary><strong>📑 Table of Contents</strong></summary>
<br>

- [Features](#features)
- [Who Is This For?](#-who-is-this-for)
- [Why mcp-audit?](#-why-mcp-audit)
  - [How mcp-audit Compares](#how-mcp-audit-compares)
- [Quick Start](#-quick-start)
- [Platform Support](#️-platform-support)
- [Feature Details](#-feature-details)
- [Configuration](#️-configuration)
- [Documentation](#-documentation)
- [CLI Reference](#-cli-reference)
- [Data Storage](#-data-storage)
- [FAQ](#-faq)
- [Roadmap](#️-roadmap)
- [Contributing](#-contributing)
- [License](#-license)

</details>

### Features

- ⚡ **Real-time TUI** — Watch tokens flow as you work
- 📊 **Per-tool breakdown** — See exactly which MCP tools eat context
- 💰 **Cost estimates** — Know what you're paying before the bill
- 🔍 **Anomaly detection** — Spot duplicates and outliers automatically
- 🗄️ **Cache analysis** — Understand if caching helps or hurts
- 🔒 **Privacy-first** — Local-only, no prompts stored
- 🪶 **Lightweight** — <500KB install, single dependency (rich)

---

## 👥 Who Is This For?

<table>
<tr>
<td width="50%" valign="top">

### 🛠️ MCP Tool Developers

You built an MCP server. Now you need answers:
- How efficient are my tools?
- Which ones bloat context?
- Am I shipping something optimized?

</td>
<td width="50%" valign="top">

### 💻 Daily Users (Power Users)

You use Claude Code, Codex CLI, or Gemini CLI daily:
- Hit context limits and don't know why?
- Seeing unexpected costs?
- Which MCP servers are responsible?

</td>
</tr>
</table>

---

## 💡 Why mcp-audit?

**mcp-audit** is a real-time session tracker that shows you exactly which MCP tools are eating your context—per server, per tool, per session. Whether you're building MCP servers or using them daily, mcp-audit gives you the granular data you need to investigate and fix context bloat & high token usage at the source.

No other tool provides this level of MCP-specific visibility. It starts with the data.

---

### How mcp-audit Compares

#### vs. [ccusage](https://github.com/ryoppippi/ccusage) ⭐ 9K+

ccusage is a fantastic **historical analyzer**—it tracks your Claude Code usage over time (daily, monthly, all-time reports). Use it to understand long-term spending trends and budget planning.

| | ccusage | mcp-audit ✓ |
|---|---------|:------------|
| **Focus** | Historical trends | ✅ Real-time sessions |
| **Question answered** | "What did I spend this month?" | ✅ "What's eating my context *right now*?" |
| **Granularity** | Session/day/month totals | ✅ Per-MCP-server, per-tool breakdown |
| **Best for** | Cost tracking over time | ✅ Investigating specific tool issues |

#### vs. [Claude-Code-Usage-Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor) ⭐ 5.8K+

Claude-Code-Usage-Monitor is a great **session limit tracker**—it predicts when you'll hit your token limit and shows burn rate. Use it to manage your session pacing.

| | Claude-Code-Usage-Monitor | mcp-audit ✓ |
|---|---------------------------|:------------|
| **Focus** | Session limits & predictions | ✅ MCP tool analysis |
| **Question answered** | "Will I run out of tokens?" | ✅ "Which MCP tool is causing this?" |
| **Granularity** | Total session tokens | ✅ Per-server, per-tool tokens |
| **Best for** | Session pacing | ✅ Debugging MCP tool efficiency |

#### Why mcp-audit for MCP Tool Development

If you're **building or optimizing MCP servers**, mcp-audit is the only tool that:

- 🔍 **Breaks down tokens per MCP tool** — See exactly which tools bloat context
- 📌 **Pins specific servers** — Monitor your server while you develop
- 🔄 **Detects duplicates** — Find redundant tool calls automatically
- 📊 **Tracks cache efficiency** — Understand if caching helps or hurts
- 🚨 **Flags anomalies** — Get warnings for high-variance patterns

> [!TIP]
> **Use them together**: ccusage for monthly cost trends, Claude-Code-Usage-Monitor for session pacing, and mcp-audit for MCP tool-level investigation.

---

## 🚀 Quick Start

### 1. Track a Session

```bash
# Track Claude Code session
mcp-audit collect --platform claude-code

# Track Codex CLI session
mcp-audit collect --platform codex-cli

# Track Gemini CLI session
mcp-audit collect --platform gemini-cli
```

Sessions are automatically saved to `~/.mcp-audit/sessions/`.

### 2. Generate a Report

```bash
# View summary of all sessions
mcp-audit report ~/.mcp-audit/sessions/

# Export detailed CSV
mcp-audit report ~/.mcp-audit/sessions/ --format csv --output report.csv

# Generate markdown report
mcp-audit report ~/.mcp-audit/sessions/ --format markdown --output report.md
```

### 3. Review Results

```
Top 10 Most Expensive Tools (Total Tokens)
═══════════════════════════════════════════════════════════════
Tool                              Calls    Tokens    Avg/Call
mcp__zen__thinkdeep                  12   450,231      37,519
mcp__brave-search__web               45   123,456       2,743
mcp__zen__chat                       89    98,765       1,109

Estimated Total Cost: $2.34 (across 15 sessions)
```

### Typical Session

```bash
# Terminal 1: Start tracking before your Claude Code session
mcp-audit collect --platform claude-code

# Terminal 2: Work normally in Claude Code
# (TUI shows tokens accumulating in real-time as you use MCP tools)

# When done, press Ctrl+C in Terminal 1
# Session auto-saved to ~/.mcp-audit/sessions/
```

---

## 🖥️ Platform Support

| Platform | Status | Pain Point Solved |
|----------|--------|-------------------|
| Claude Code | **Stable** | Stop wondering why you hit the context limit |
| Codex CLI | **Stable** | Know exactly what you're paying for |
| Gemini CLI | **Stable** | Native session file parsing with thinking tokens |
| Ollama CLI | *Coming Soon* | Time-based tracking (no token costs locally) |

Want support for another CLI platform? Have a feature request? [Start a discussion](https://github.com/littlebearapps/mcp-audit/discussions)!

---

## ✨ Feature Details

### ⚡ Real-Time TUI

Watch tokens flow as you work—no manual tracking:

```
MCP Audit v0.3.11
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Project: my-project │ Claude Opus 4.5 │ 12m 34s

Tokens
  Input: 45,231 │ Output: 12,543 │ Cache: 125K (93%)
  Cost: $0.12 │ Cache Savings: $0.89

MCP Servers & Tools (42 calls)
  zen (28 calls, 234K tokens)
    thinkdeep ........ 8 calls, 156K tokens
    chat ............. 15 calls, 45K tokens
  brave-search (14 calls, 89K tokens)
    brave_web_search . 14 calls, 89K tokens
```

**Investigating context bloat?** Pin your MCP server to monitor it closely during development:

```bash
mcp-audit collect --platform claude-code --pin-server myserver
```

### 📊 Cross-Session Analysis

Aggregate insights across all your sessions:

```bash
mcp-audit report ~/.mcp-audit/sessions/ --aggregate
```

- Top expensive tools by total tokens
- Most frequently called tools
- Anomaly detection (high variance, duplicates)
- Per-server cost breakdowns

### 🔍 Duplicate Detection

Spot wasted tokens from redundant tool calls:

```json
{
  "redundancy_analysis": {
    "duplicate_calls": 3,
    "potential_savings": 15234
  }
}
```

### 🗄️ Cache Analysis

Understand whether caching is helping or hurting. Session logs include AI-readable insights:

```json
{
  "cache_analysis": {
    "status": "efficient",
    "summary": "Good cache reuse (85% efficiency). Savings: $0.89",
    "top_cache_creators": [{"tool": "mcp__zen__thinkdeep", "pct": 45}],
    "recommendation": "Cache is working well for this session."
  }
}
```

### 🔒 Privacy-First

- **No prompts stored** - Only token counts and tool names
- **Local-only** - All data stays on your machine
- **Redaction hooks** - Customize what gets logged

---

## ⚙️ Configuration

Customize model pricing in `mcp-audit.toml`. Searched in order: `./mcp-audit.toml` (project), `~/.mcp-audit/mcp-audit.toml` (user).

> [!NOTE]
> Prices in **USD per million tokens**.

```toml
[pricing.claude]
"claude-opus-4-5-20251101" = { input = 5.00, output = 25.00, cache_create = 6.25, cache_read = 0.50 }
"claude-sonnet-4-5-20250929" = { input = 3.00, output = 15.00, cache_create = 3.75, cache_read = 0.30 }

[pricing.openai]
"gpt-5.1" = { input = 1.25, output = 10.00, cache_read = 0.125 }
"gpt-4o" = { input = 2.50, output = 10.00, cache_read = 1.25 }

[pricing.gemini]
"gemini-3-pro-preview" = { input = 2.00, output = 12.00, cache_read = 0.20 }
"gemini-2.5-pro" = { input = 1.25, output = 10.00, cache_read = 0.125 }
"gemini-2.5-flash" = { input = 0.30, output = 2.50, cache_read = 0.03 }
```

See [Pricing Configuration](docs/PRICING-CONFIGURATION.md) for the full list of supported models.

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Features & Benefits](docs/FEATURES-BENEFITS.md) | Detailed feature guide by audience |
| [Architecture](docs/architecture.md) | System design, data model, adapters |
| [Data Contract](docs/data-contract.md) | Schema v1.1.0 format and guarantees |
| [Platform Guides](docs/platforms/) | Claude Code, Codex CLI, Gemini CLI setup |
| [Contributing](docs/contributing.md) | How to add platform adapters |
| [Privacy & Security](docs/privacy-security.md) | Data handling policies |
| [Changelog](CHANGELOG.md) | Version history and release notes |
| [Roadmap](ROADMAP.md) | Planned features and long-term vision |

---

## 💻 CLI Reference

```bash
mcp-audit --help

Commands:
  collect   Track a live session
  report    Generate usage report

Options:
  --version  Show version
  --help     Show help
```

### collect

```bash
mcp-audit collect [OPTIONS]

Options:
  --platform          Platform to track (claude-code, codex-cli, gemini-cli, auto)
  --project TEXT      Project name (auto-detected from directory)
  --output PATH       Output directory (default: ~/.mcp-audit/sessions)
  --tui               Use rich TUI display (default when TTY available)
  --plain             Use plain text output (for CI/logs)
  --quiet             Suppress all display output (logs only)
  --refresh-rate NUM  TUI refresh rate in seconds (default: 0.5)
  --pin-server NAME   Pin server(s) at top of MCP section (can repeat)
  --no-logs           Skip writing logs to disk (real-time display only)
```

#### Display Modes

MCP Audit automatically detects whether you're running in a terminal (TTY) and chooses the best display mode:

- **TUI mode** (default for terminals): Beautiful Rich-based dashboard with live updating
- **Plain mode** (default for CI/pipes): Simple scrolling text output
- **Quiet mode**: No display output, only writes logs to disk

### report

```bash
mcp-audit report [OPTIONS] SESSION_DIR

Arguments:
  SESSION_DIR        Session directory or parent directory containing sessions

Options:
  --format           Output format: json, csv, markdown (default: markdown)
  --output PATH      Output file (default: stdout)
  --aggregate        Aggregate data across multiple sessions
  --top-n INT        Number of top tools to show (default: 10)
```

---

## 📁 Data Storage

Sessions are stored at `~/.mcp-audit/sessions/` organized by date:

```
~/.mcp-audit/sessions/
├── 2025-12-02/
│   ├── mcp-audit-2025-12-02T09-15-30.json
│   └── mcp-audit-2025-12-02T14-30-45.json
└── 2025-12-01/
    └── mcp-audit-2025-12-01T10-20-00.json
```

Each session is a self-describing JSON file (schema v1.1.0). See [Data Contract](docs/data-contract.md) for format details.

---

## ❓ FAQ

<details open>
<summary><strong>Does mcp-audit work with resumed/continued sessions?</strong></summary>
<br>

**Yes.** If you start mcp-audit and then resume a Claude Code session from yesterday, it will track all new activity from that point forward. Claude Code appends new events to the existing session file, and mcp-audit monitors for new content regardless of when the session originally started.

</details>

<details>
<summary><strong>What if I start mcp-audit after Claude Code is already running?</strong></summary>
<br>

**It works, but you'll only capture activity from that point forward.** When mcp-audit starts, it records the current position in all session files. Any new events written after that point are tracked. Events that occurred before you started mcp-audit are not captured.

> [!TIP]
> Start mcp-audit first, then start or resume your Claude Code session.

</details>

<details>
<summary><strong>Does mcp-audit track historical data or only new activity?</strong></summary>
<br>

**Only new activity.** mcp-audit is designed for real-time monitoring. It deliberately skips historical data to avoid:
- Re-processing old sessions you've already analyzed
- Inflating token counts with past activity
- Confusion about what happened "this session" vs "last week"

If you need to analyze historical sessions, use `mcp-audit report` on previously saved session files.

</details>

<details>
<summary><strong>Can I track multiple Claude Code windows or projects?</strong></summary>
<br>

**Yes, but each requires its own mcp-audit instance.** Each Claude Code project has its own session file in `~/.claude/projects/`. If you're working in multiple directories simultaneously:

```bash
# Terminal 1: Track project A
cd ~/projects/project-a
mcp-audit collect --platform claude-code

# Terminal 2: Track project B
cd ~/projects/project-b
mcp-audit collect --platform claude-code
```

Each mcp-audit instance monitors the session files for its working directory.

</details>

<details>
<summary><strong>Why am I seeing 0 tokens or no activity?</strong></summary>
<br>

Common causes:

1. **Started mcp-audit after Claude Code** - Only new activity is tracked. Try making a request in Claude Code after starting mcp-audit.

2. **Wrong directory** - mcp-audit looks for session files based on your working directory. Make sure you're in the same directory as your Claude Code session.

3. **No MCP tools used** - mcp-audit tracks MCP server tools (like `mcp__zen__chat`). Built-in tools (Read, Write, Bash) are tracked separately. If you're not using MCP tools, you'll see low/zero MCP activity.

4. **Session file not found** - Check that Claude Code has created a session file:
   ```bash
   ls ~/.claude/projects/
   ```

</details>

<details>
<summary><strong>Where is my data stored? Is it sent anywhere?</strong></summary>
<br>

**All data stays on your machine.** mcp-audit is completely local:

- Session data: `~/.mcp-audit/sessions/`
- Configuration: `~/.mcp-audit/mcp-audit.toml`
- No network requests, no telemetry, no cloud sync

Only token counts and tool names are logged—**prompts and responses are never stored**.

</details>

<details>
<summary><strong>How do I stop tracking without losing data?</strong></summary>
<br>

**Press Ctrl+C.** mcp-audit handles interrupts gracefully:

1. Catches the interrupt signal
2. Completes the session summary
3. Writes all data to disk
4. Exits cleanly

You'll see a confirmation message:
```
Session saved to: ~/.mcp-audit/sessions/2025-12-02/mcp-audit-2025-12-02T14-30-45.json
```

> [!WARNING]
> Avoid `kill -9` or force-quitting the terminal, which may result in incomplete session data.

</details>

<details>
<summary><strong>Can I track multiple platforms at the same time?</strong></summary>
<br>

**Yes.** Run separate mcp-audit instances for each platform:

```bash
# Terminal 1: Track Claude Code
mcp-audit collect --platform claude-code

# Terminal 2: Track Codex CLI
mcp-audit collect --platform codex-cli
```

Sessions are organized by date in `~/.mcp-audit/sessions/`.

</details>

---

## 🗺️ Roadmap

**Current**: v0.3.x (Beta) — Stable for daily use

### Coming Soon
- Multi-model session tracking
- Enhanced CLI commands and report filters
- Ollama CLI support (local models)
- Dynamic pricing via LiteLLM

See the full [Roadmap](ROADMAP.md) for details and long-term vision.

**Have an idea?** [Start a discussion](https://github.com/littlebearapps/mcp-audit/discussions/new?category=ideas) — we'd love to hear from you!

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- How to add new platform adapters
- Testing requirements
- PR workflow

### Development Setup

```bash
git clone https://github.com/littlebearapps/mcp-audit.git
cd mcp-audit
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pytest
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

🐻 **Made with care by [Little Bear Apps](https://littlebearapps.com)**

[Issues](https://github.com/littlebearapps/mcp-audit/issues) · [Discussions](https://github.com/littlebearapps/mcp-audit/discussions) · [Roadmap](ROADMAP.md)
