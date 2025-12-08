# MCP Audit

**Find + fix context bloat & high token usage in your MCP tools.**

Whether you build MCP servers or use **Claude Code**, **Codex CLI**, or **Gemini CLI**, `mcp-audit` shows you exactly where your tokens go—per server, per tool, in real-time.

![MCP Audit real-time TUI showing token usage](https://raw.githubusercontent.com/littlebearapps/mcp-audit/main/docs/images/demo.gif)
> *Real-time token tracking & MCP tool profiling — understand exactly where your tokens go.*

[![PyPI version](https://img.shields.io/pypi/v/mcp-audit?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/mcp-audit/)
[![Downloads](https://img.shields.io/pypi/dm/mcp-audit?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/mcp-audit/)
[![CI](https://img.shields.io/github/actions/workflow/status/littlebearapps/mcp-audit/ci.yml?branch=main&label=CI&style=for-the-badge&logo=github&logoColor=white)](https://github.com/littlebearapps/mcp-audit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](https://opensource.org/licenses/MIT)

---

## ⚡ Quick Install

```bash
pipx install mcp-audit
```

<details>
<summary>Alternative: pip or uv</summary>

```bash
pip install mcp-audit
```

```bash
uv pip install mcp-audit
```

</details>

> [!TIP]
> **Gemini CLI Users:** For 100% accurate token counts (instead of ~95%), run `mcp-audit tokenizer download` after installing.
> ```bash
> mcp-audit tokenizer download
> ```

---

## 👥 Who Is This For?

<table>
<tr>
<td width="50%" valign="top">

### 🛠️ The Builder
**"Is my MCP server (or the one I downloaded) too heavy?"**

You build MCP servers and want visibility into token consumption patterns.

**You need:** Per-tool token breakdown, usage trends.

<br>

</td>
<td width="50%" valign="top">

### 💻 The Vibecoder
**"Why did my CLI Agent auto-compact so quickly?"**

You use Cursor/Claude daily and hit context limits without knowing why.

**You need:** Real-time cost tracking, session telemetry.

<br>

</td>
</tr>
</table>

---

### 🛡️ How It Works (Safe & Passive)

`mcp-audit` is a **passive observer**. It watches your local session logs and artifacts in real-time.
* **No Proxies:** It does not intercept your network traffic or API calls.
* **No Latency:** It runs as a sidecar process, adding zero overhead to your agent.
* **Local Only & Private:** All data remains on your machine.
* **Telemetry Only:** Provides signals and metrics — you (or your AI) decide what to do with them.

**Note:** MCP Audit is telemetry-only — no recommendations or optimizations are performed automatically.  
Use the AI export (coming in v0.5.0) to analyze your results with your preferred AI CLI.

---

## 🚀 What's New in v0.4.0

- **High-Accuracy Token Estimation:** Session-level tokens are **99-100% accurate** for Codex CLI and Gemini CLI (using tiktoken/Gemma tokenizers). Per-tool estimates are also highly accurate.
- **Theme Support:** Full theme support including **Catppuccin Mocha/Latte** and High Contrast modes.
- **Ultra Light:** Core package size reduced from 5MB to **<500KB** (~2.5MB with optional Gemma tokenizer).

---

## 🔍 What to Look For (The "Audit")

Once you're running `mcp-audit`, watch for these common patterns in your telemetry:

1. **The "Context Tax" (High Initial Load):**
   - *Signal:* Your session starts with 10k+ tokens before you type a word.
   - *What this might indicate:* Large `list_tools` schemas can increase context usage on each turn (detailed telemetry coming in v0.6.0+).

2. **The "Payload Spike" (Unexpected Cost):**
   - *Signal:* A single tool call consumes far more tokens than expected.
   - *What this might indicate:* Large file reads or verbose API responses.

3. **The "Zombie Tool":** *(detection coming in v0.5.0)*
   - *Signal:* A tool appears in your schema but is never called.
   - *What this might indicate:* Unused tools consuming schema tokens on every turn.

---

## 🎮 Quick Start

### 1. Start Tracking

Open a separate terminal window and run (see [Platform Guides](#-documentation) for detailed setup):

```bash
# Auto-detects your platform (or specify with --platform)
mcp-audit collect --platform claude-code
mcp-audit collect --platform codex-cli
mcp-audit collect --platform gemini-cli
```

### 2. Work Normally

Go back to your agent (Claude Code, Codex CLI, or Gemini CLI) and start working. The MCP Audit TUI updates in real-time as you use tools.

> **TUI runs automatically.** Other display options: `--quiet` (logs only), `--plain` (CI/pipelines), `--no-logs` (display only).

### 3. Analyze Later

Generate a post-mortem report to see where the money went:

```bash
# See the top 10 most expensive tools
mcp-audit report ~/.mcp-audit/sessions/ --top-n 10

# Session logs are stored by default in ~/.mcp-audit/sessions/
```

---

## 🤖 Supported Agents

![Claude Code](https://img.shields.io/badge/Claude%20Code-D97757?style=for-the-badge&logo=anthropic&logoColor=white)
![OpenAI Codex](https://img.shields.io/badge/Codex%20CLI-412991?style=for-the-badge&logo=openai&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Gemini%20CLI-8E75B2?style=for-the-badge&logo=google%20gemini&logoColor=white)

| Platform | Token Accuracy | Tracking Depth | Notes |
| :--- | :--- | :--- | :--- |
| **Claude Code** | **Native** (100%) | Full (Per-Tool) | Shows exact server-side usage. |
| **Codex CLI** | **Estimated** (99%+) | Session + Tool | Uses `o200k_base` tokenizer for near-perfect precision. |
| **Gemini CLI** | **Estimated** (100%) | Session + Tool | Uses `Gemma` tokenizer (requires download) or fallback (~95%). |
| **Ollama CLI** | — | — | Coming soon. |

- Session-level token accuracy is 99–100% for Codex CLI and Gemini CLI.  
  *(Per-tool token counts are estimated and highly accurate in most cases.)*

> **Want support for another CLI platform?** [Start a discussion](https://github.com/littlebearapps/mcp-audit/discussions/new?category=ideas) and let us know what you need!

<details>
<summary><strong>Detailed Platform Capabilities</strong></summary>
<br>

| Capability | Claude Code | Codex CLI | Gemini CLI |
|------------|:-----------:|:---------:|:----------:|
| Session tokens | ✅ Full | ✅ Full | ✅ Full |
| Per-tool tokens | ✅ Native | ✅ Estimated | ✅ Estimated |
| Reasoning tokens | ❌ Not exposed | ✅ o-series | ✅ Gemini 2.0+ |
| Cache tracking | ✅ Create + Read | ✅ Read only | ✅ Read only |
| Cost estimates | ✅ Accurate | ✅ Accurate | ✅ Accurate |

</details>

---

## 🤝 The Token Ecosystem (When to use what)

`mcp-audit` focuses on **real-time MCP inspection**. It fits perfectly alongside other tools in your stack:

| Tool | Best For... | The Question it Answers |
| :--- | :--- | :--- |
| **MCP Audit** (Us) | ⚡ **Deep Profiling** | "Which specific tool is eating my tokens right now?" |
| **[ccusage](https://github.com/ryoppippi/ccusage)** | 📅 **Billing & History** | "How much did I spend last month?" |
| **[Claude Code Usage Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor)** | 🛑 **Session Limits** | "Will I hit my limit in the next hour?" |

---

## ⚙️ Configuration & Theming

**New in v0.4.0:** Customize your dashboard look!

```bash
# Use the Catppuccin Mocha theme
mcp-audit collect --theme mocha

# Use Catppuccin Latte (light)
mcp-audit collect --theme latte

# Use High Contrast (Accessibility - WCAG AAA)
mcp-audit collect --theme hc-dark
```

*Supported Themes:* `auto`, `dark`, `light`, `mocha`, `latte`, `hc-dark`, `hc-light`

> **Note:** Advanced features such as smell detection, zombie tool detection,  
> AI prompt export, and multi-model sessions are part of the upcoming v0.5.0+ releases.

### Pricing Configuration

Customize model pricing in `mcp-audit.toml`:

```toml
[pricing.claude]
"claude-opus-4-5-20251101" = { input = 5.00, output = 25.00 }

[pricing.openai]
"gpt-5.1" = { input = 1.25, output = 10.00 }
```

Prices in USD per million tokens. See [Pricing Configuration](docs/PRICING-CONFIGURATION.md) for all models.

---

## 💻 CLI Reference

```bash
# Most common usage - just run this and start working
mcp-audit collect

# Specify your platform explicitly
mcp-audit collect --platform claude-code
mcp-audit collect --platform codex-cli
mcp-audit collect --platform gemini-cli

# Use a dark theme (try: mocha, latte, hc-dark, hc-light)
mcp-audit collect --theme mocha

# See where your tokens went after a session
mcp-audit report ~/.mcp-audit/sessions/

# Gemini CLI users: download tokenizer for 100% accuracy
mcp-audit tokenizer download
```

### collect

Track a live session.

```
Options:
  --platform          Platform: claude-code, codex-cli, gemini-cli, auto
  --project TEXT      Project name (auto-detected from directory)
  --theme NAME        Color theme (default: auto)
  --pin-server NAME   Pin server(s) at top of MCP section
  --from-start        Include existing session data (Codex/Gemini only)
  --quiet             Suppress display output (logs only)
  --plain             Plain text output (for CI/logs)
  --no-logs           Skip writing logs to disk (real-time display only)
```

### report

Generate usage report.

```
Options:
  --format           Output: json, csv, markdown (default: markdown)
  --output PATH      Output file (default: stdout)
  --aggregate        Aggregate across multiple sessions
  --top-n INT        Number of top tools to show (default: 10)
```

### tokenizer

Manage optional tokenizers.

```bash
mcp-audit tokenizer download   # Download Gemma tokenizer (~4MB)
mcp-audit tokenizer status     # Check tokenizer availability
```

### Uninstall

```bash
# If installed with pipx
pipx uninstall mcp-audit

# If installed with pip
pip uninstall mcp-audit
```

---

## ❓ FAQ

<details open>
<summary><strong>How accurate is token estimation for Codex CLI and Gemini CLI?</strong></summary>

<br>

**Very accurate.** In v0.4.0, we use the same tokenizers as the underlying models:

- **Codex CLI (OpenAI):** Uses `tiktoken` with the `o200k_base` encoding — the same tokenizer OpenAI uses. Session-level accuracy is **99%+**.
- **Gemini CLI (Google):** Uses the official `Gemma` tokenizer (via `mcp-audit tokenizer download`). Session-level accuracy is **100%**. Without it, we fall back to `tiktoken` at ~95% accuracy.

**Per-tool token estimates** are also highly accurate in most cases, though platforms don't provide native per-tool attribution (only Claude Code does).

Claude Code provides native token counts directly from Anthropic's servers, so no estimation is needed there.

</details>

<details>
<summary><strong>Why am I seeing 0 tokens or no activity?</strong></summary>

<br>

1. **Started mcp-audit after the agent** — Only new activity is tracked. Start `mcp-audit` first, then your agent.
2. **Wrong directory** — mcp-audit looks for session files based on your current working directory.
3. **No MCP tools used yet** — Built-in tools (Read, Write, Bash) are tracked separately. Try using an MCP tool.

</details>

<details>
<summary><strong>Where is my data stored?</strong></summary>

<br>

**All data stays on your machine:**
- Session data: `~/.mcp-audit/sessions/`
- Configuration: `~/.mcp-audit/mcp-audit.toml`
- No network requests, no telemetry

Only token counts and tool names are logged—**prompts and responses are never stored**.

</details>

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Features & Benefits](docs/FEATURES-BENEFITS.md) | Detailed feature guide |
| [Architecture](docs/architecture.md) | System design and adapters |
| [Data Contract](docs/data-contract.md) | Schema v1.4.0 format |
| [Claude Code Guide](docs/platforms/claude-code.md) | Getting started & help guide |
| [Codex CLI Guide](docs/platforms/codex-cli.md) | Getting started & help guide |
| [Gemini CLI Guide](docs/platforms/gemini-cli.md) | Getting started & help guide |
| [Privacy & Security](docs/privacy-security.md) | Data handling policies |
| [Manual Tokenizer Install](docs/manual-tokenizer-install.md) | For firewalled networks |
| [Changelog](CHANGELOG.md) | Version history |
| [Roadmap](ROADMAP.md) | Planned features |

---

## 🗺️ Roadmap

**Current**: v0.4.x — Stable for daily use

**Coming in v0.5.0:**
- Smell detection signals (HIGH_VARIANCE, TOP_CONSUMER, CHATTY)
- AI-friendly session export for analysis prompts
- Zombie tool detection

**Coming in v0.6.0+:**
- Multi-model session tracking
- TUI session browser
- Static/dynamic payload metrics
- Ollama CLI support (minimal)

See the full [Roadmap](ROADMAP.md) for details.

**Have an idea or feature request?** [Start a discussion](https://github.com/littlebearapps/mcp-audit/discussions/new?category=ideas)

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for how to build new platform adapters.

### Development Setup

```bash
git clone https://github.com/littlebearapps/mcp-audit.git
cd mcp-audit
pip install -e ".[dev]"
pytest
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

**Third-Party:**
- [tiktoken](https://github.com/openai/tiktoken) (MIT) — Bundled for Codex CLI token estimation
- [Gemma tokenizer](https://huggingface.co/google/gemma-2-2b) (Apache 2.0) — Optional download for Gemini CLI. See [Gemma Tokenizer License](docs/gemma-tokenizer-license.md) for terms.

---

**Made with 🐻 by [Little Bear Apps](https://littlebearapps.com)**

[Issues](https://github.com/littlebearapps/mcp-audit/issues) · [Discussions](https://github.com/littlebearapps/mcp-audit/discussions) · [Roadmap](ROADMAP.md)
