# MCP Audit Landing Page Copy

**Target URL:** littlebearapps.com/mcp-audit
**Version:** v0.9.0 content prep
**Last Updated:** 2025-12-14

---

## Hero Section

### Headline
**Real-time MCP token profiler for AI coding agents**

### Subheadline
Investigate context bloat and high token usage at the source. Track every MCP tool call across Claude Code, Codex CLI, and Gemini CLI.

### Primary CTA
**Get Started** → Links to Installation section or docs

### Secondary CTA
**View on GitHub** → https://github.com/littlebearapps/mcp-audit

---

## Problem Section

### Section Header
**Why your AI agent runs out of context**

### Pain Points

**1. Early Auto-Compaction**
Your sessions end prematurely because MCP tools silently consume more tokens than you expect. One chatty tool can burn through your context window before you finish your task.

**2. Hidden MCP Overhead**
Every MCP server adds "context tax" - schema definitions, tool descriptions, and payloads that eat into your available tokens. You can't optimize what you can't see.

**3. Unpredictable Costs**
Tokens add up faster than expected when switching models or using multiple MCP servers. Without visibility, you're flying blind on costs.

---

## Solution Section

### Section Header
**See exactly what's eating your tokens**

### Value Proposition
MCP Audit gives you real-time visibility into token consumption across your entire MCP stack. Track per-server, per-tool usage. Detect inefficient patterns automatically. Optimize your agent workflows for faster, cheaper, more predictable results.

### Key Benefits
- **Track every token** - Per-server, per-tool breakdown in real-time
- **Detect problems automatically** - 12 efficiency anti-patterns flagged instantly
- **Stay local** - No cloud uploads, no proxies, all data stays on your machine

---

## Features Section

### Feature 1: Real-Time Token Profiling
**Icon:** Chart/graph with live indicator

Track token usage as it happens. See per-server and per-tool breakdowns. Native support for Claude Code (100% accuracy), estimated for Codex CLI and Gemini CLI (99%+ accuracy).

### Feature 2: Smell Detection Engine
**Icon:** Warning indicator

12 efficiency anti-patterns detected automatically:
- HIGH_VARIANCE, TOP_CONSUMER, HIGH_MCP_SHARE
- CHATTY, LOW_CACHE_HIT, REDUNDANT_CALLS
- EXPENSIVE_FAILURES, BURST_PATTERN, LARGE_PAYLOAD
- SEQUENTIAL_READS, CACHE_MISS_STREAK, UNDERUTILIZED_SERVER

Plus: Zombie Tool Detection finds unused MCP tools wasting schema tokens.

### Feature 3: Multi-Model Intelligence
**Icon:** Multiple AI model icons

Track costs when switching between models mid-session. Dynamic pricing for 2,000+ models via LiteLLM API. See exactly which model consumed what.

### Feature 4: Privacy-First Design
**Icon:** Lock or shield

No proxies. No interception. No cloud uploads. All data stays local in `~/.mcp-audit/sessions/`. Works alongside existing workflows with zero setup overhead.

### Feature 5: Cross-Platform Support
**Icon:** Multiple platform logos

Works with the AI coding agents you already use:
- **Claude Code** - Native support, 100% token accuracy
- **Codex CLI** - Estimated tokens, 99%+ accuracy
- **Gemini CLI** - 100% accuracy with optional tokenizer download
- **Ollama** - Coming in v1.1.0

---

## Platforms Section

### Section Header
**Works with your AI coding stack**

| Platform | Accuracy | Notes |
|----------|----------|-------|
| Claude Code (Anthropic) | 100% | Native token tracking |
| Codex CLI (OpenAI) | 99%+ | Estimated tokens |
| Gemini CLI (Google) | 100%* | *With optional tokenizer |
| Ollama | Coming Soon | Planned for v1.1.0 |

**Compatibility:** Python 3.8-3.13 | macOS, Linux, Windows (WSL)

---

## Installation Section

### Section Header
**Get started in 30 seconds**

```bash
# Install
pipx install mcp-audit

# Start tracking
mcp-audit collect --platform claude-code

# Optional: Gemini tokenizer for 100% accuracy
mcp-audit tokenizer download
```

### What Happens Next
1. Run `mcp-audit collect` in one terminal
2. Use your AI agent normally in another
3. Watch real-time token usage in the TUI
4. Generate reports with `mcp-audit report`

---

## Use Cases Section

### MCP Server Developers
> "Is my MCP server too heavy?"

See exactly which tools and schemas consume tokens. Optimize before users hit context limits.

### AI Coding Power Users
> "Why did Claude Code auto-compact so quickly?"

Reveal which MCP tools drain your context window. Work longer without interruption.

### Cost-Conscious Teams
> "How can we reduce AI coding costs?"

Track usage across platforms and models. Achieve 40-60% cost savings.

---

## Comparison Section

| Feature | MCP Audit | ccusage | Usage Monitor |
|---------|-----------|---------|---------------|
| MCP token breakdown | Per-tool | No | No |
| Smell detection | 12 patterns | No | No |
| Multi-platform | 3 platforms | Claude only | Claude only |
| Real-time TUI | Yes | No | No |
| Cost tracking | Yes | Yes | Yes |
| Billing history | No | Yes | No |
| Session limits | No | No | Yes |

**MCP Audit** = Deep MCP profiling | **ccusage** = Billing history | **Usage Monitor** = Session limits

---

## CTA Section

### Section Header
**Start tracking your MCP tokens today**

```bash
pipx install mcp-audit
```

**No signup. No cloud account. Just install and start tracking.**

- [Get Started](docs) | [GitHub](https://github.com/littlebearapps/mcp-audit) | [PyPI](https://pypi.org/project/mcp-audit/)

---

## SEO Metadata

```yaml
title: "MCP Audit - Real-time Token Profiler for AI Coding Agents"
description: "Track MCP token usage in Claude Code, Codex CLI & Gemini CLI. Detect context bloat, optimize costs, and prevent early auto-compaction. Free and open source."
keywords: "mcp audit, mcp server, token tracking, claude code, codex cli, gemini cli, context window, llm costs, context bloat, auto-compaction"
og_image: "hero-demo.gif"
```
