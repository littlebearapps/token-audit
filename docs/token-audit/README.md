# Token Audit

> Cross-platform token usage tracking for AI coding assistants

---

## What It Does

Token Audit (part of token-audit) tracks token usage, costs, and tool calls across multiple AI coding platforms:

- **Claude Code** (Anthropic)
- **Codex CLI** (OpenAI)
- **Gemini CLI** (Google)

### Key Features

| Feature | Description |
|---------|-------------|
| **Token Tracking** | Input, output, cache, reasoning tokens per session |
| **Cost Calculation** | Real-time pricing from LiteLLM with fallbacks |
| **Tool Attribution** | Per-tool and per-server token breakdown |
| **Historical Reporting** | Daily, weekly, monthly aggregation |
| **Project Grouping** | Group usage by git repo or working directory |
| **Local-First** | All data stored locally, no cloud accounts |

---

## Quick Start

```bash
# Install
pip install token-audit

# Collect a Claude Code session
token-audit collect --platform claude-code

# View daily usage
token-audit daily

# View weekly with JSON output
token-audit weekly --json | jq '.[] | select(.cost_usd > 1)'

# Group by project
token-audit monthly --instances
```

---

## Historical Reporting (v1.0.0)

### Daily Usage
```bash
token-audit daily                    # Last 7 days, all platforms
token-audit daily --platform claude-code --days 14
token-audit daily --instances        # Group by project
token-audit daily --json             # Machine-readable
```

### Weekly Usage
```bash
token-audit weekly                   # Last 4 weeks
token-audit weekly --start-of-week sunday  # US-style weeks
```

### Monthly Usage
```bash
token-audit monthly                  # Last 3 months
token-audit monthly --breakdown      # Per-model breakdown
```

---

## Data Accuracy

Token accuracy varies by platform:

| Platform | Accuracy | Method |
|----------|----------|--------|
| Claude Code | Exact | Native Anthropic API |
| Codex CLI | ~95% | tiktoken estimation |
| Gemini CLI | ~90% | sentencepiece estimation |

See [capabilities-matrix.md](capabilities-matrix.md) for full details.

---

## Documentation

| Document | Description |
|----------|-------------|
| [capabilities-matrix.md](capabilities-matrix.md) | What works on each platform |
| [implementation-plan.md](implementation-plan.md) | Development roadmap |
| [ccusage-notes.md](ccusage-notes.md) | Inspiration from ccusage |
| [open-questions.md](open-questions.md) | Unresolved design decisions |

---

## Architecture

```
~/.token-audit/
├── sessions/
│   ├── claude-code/
│   │   ├── 2025-12-24/
│   │   │   ├── .index.json          # Daily index
│   │   │   └── session-*.jsonl      # Session data
│   │   └── .index.json              # Platform index
│   ├── codex-cli/
│   └── gemini-cli/
└── config/
    └── token-audit.toml               # User configuration
```

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| v1.0.0 | 2025-12-24 | Historical aggregation, CLI commands |
| v0.9.1 | 2025-12-15 | Project field, tiered pricing |
| v0.9.0 | 2025-12-14 | Performance optimization, benchmarks |

---

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) in the repository root.
