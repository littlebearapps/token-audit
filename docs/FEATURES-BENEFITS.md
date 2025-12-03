# Features & Benefits by Audience

MCP Audit v0.3.11 - Features mapped to benefits for each target audience.

---

## At a Glance

| Feature | MCP Tool Developers | AI Coding Power Users |
|---------|---------------------|----------------------|
| Real-time TUI | See tool efficiency live | Watch context consumption |
| Per-tool metrics | Benchmark your implementations | Find expensive tools |
| Per-server breakdown | Isolate server-level issues | Compare MCP server costs |
| Cache analysis | Optimize cache behavior | Understand cache efficiency |
| Duplicate detection | Find redundant API calls | Spot wasted tokens |
| Cross-session reports | Track optimization progress | Long-term cost trends |
| Cost estimation | Price your tools accurately | Budget planning |
| Privacy-first design | Safe to use in production | No data leaves your machine |

---

## Audience 1: MCP Tool Developers

**Profile**: You build MCP servers (hand-coded or via AI CLI agents). You need data to optimize your implementations before shipping. You're investigating context bloat and high token usage in your tools.

### Core Benefits

| You Need | Feature | How It Helps |
|----------|---------|--------------|
| Know if your tools are efficient | **Per-tool token metrics** | See exact token consumption per tool call |
| Compare tool versions | **Cross-session analysis** | Track improvements across development cycles |
| Find bloated tools | **Top expensive tools ranking** | Instantly identify the worst offenders |
| Optimize cache behavior | **Cache analysis with AI-readable breakdown** | See which tools drive cache creation vs reuse |
| Catch redundant API patterns | **Duplicate detection** | Find repeated identical calls automatically |
| Ship with confidence | **Anomaly detection** | Get warnings for high-variance or high-frequency patterns |
| Investigate context bloat | **Server pinning** | Pin your server to monitor it closely during development |

### Key Features for Developers

**1. Per-Tool Token Breakdown**
```
Tool                              Calls    Tokens    Avg/Call
mcp__myserver__heavy_tool            12   450,231      37,519
mcp__myserver__light_tool            45    12,345         274
```
- Compare tool efficiency within your server
- Identify which tools need optimization
- Benchmark against expected performance

**2. Cache Analysis (AI-Readable)**
```json
{
  "cache_analysis": {
    "status": "inefficient",
    "top_cache_creators": [{"tool": "mcp__myserver__fetch", "tokens": 50000, "pct": 80}],
    "recommendation": "Consider batching related queries to reuse cached context."
  }
}
```
- Understand cache creation vs read patterns
- Get actionable recommendations
- Optimize for Anthropic's cache pricing model

**3. Duplicate Detection**
```json
{
  "redundancy_analysis": {
    "duplicate_calls": 3,
    "potential_savings": 15234,
    "details": [{"tool": "mcp__myserver__search", "count": 2, "tokens": 8765}]
  }
}
```
- Find identical tool calls that could be cached
- Quantify potential token savings
- Improve tool design to avoid redundancy

**4. Cross-Session Trend Analysis**
```bash
mcp-audit report ~/.mcp-audit/sessions/ --format csv --output analysis.csv
```
- Track optimization progress over time
- Compare before/after metrics
- Export to spreadsheet for deeper analysis

### Developer Workflow

```bash
# 1. Track while developing
mcp-audit collect --platform claude-code --pin-server myserver

# 2. Work with your MCP tools
# (Real-time TUI shows per-tool metrics)

# 3. Review session results
mcp-audit report ~/.mcp-audit/sessions/

# 4. Iterate and improve
# (Track new sessions to verify optimizations)
```

---

## Audience 2: AI Coding Power Users

**Profile**: You use Claude Code, Codex CLI, or Gemini CLI daily. You've hit context limits or seen unexpected costs. You want visibility.

### Core Benefits

| You Need | Feature | How It Helps |
|----------|---------|--------------|
| Know what's eating context | **Real-time TUI** | Watch tokens flow as you work |
| Find expensive MCP tools | **Per-server breakdown** | See exactly which servers cost most |
| Stay under context limits | **Cache efficiency tracking** | Understand how much context is reused |
| Control costs | **Cost estimation** | See estimated spend in real-time |
| Make informed tool choices | **Top tools ranking** | Know which tools to use sparingly |
| Understand usage patterns | **Cross-session reports** | Spot trends across your workflow |

### Key Features for Power Users

**1. Real-Time TUI Dashboard**
```
MCP Audit - Live Session
-------------------------------------------
Project: my-project | Platform: claude-code
Elapsed: 12m 34s | Model: claude-opus-4-5

Tokens:  45,231 input | 12,543 output | 125K cached
Cost:    $0.12 (estimated)
Cache:   93% efficiency | Savings: $0.89

MCP Servers & Tools (42 calls)
  zen (28 calls, 234K tokens)
    chat ............ 15 calls, 45K tokens
    thinkdeep ....... 8 calls, 156K tokens
    debug ........... 5 calls, 33K tokens
  brave-search (14 calls, 89K tokens)
    brave_web_search  14 calls, 89K tokens
```
- See everything at a glance
- No manual tracking or spreadsheets
- Updates in real-time as you work

**2. Cost Estimation**
```
Estimated Cost:  $0.12
```
- Real-time cost tracking based on model pricing
- Configurable pricing for different models
- Cache savings factored in

**3. Cache Efficiency Insights**
```
Cache efficiency:  93%
Cache Savings:    $0.89

(or if inefficient)
Net Cost:         $0.05 (high creation, low reuse)
```
- Understand whether cache is helping or hurting
- See potential savings from cache hits
- Know when to optimize query patterns

**4. Server-Level Breakdown**
```
MCP Servers & Tools
  zen (28 calls, 234K tokens) ............... 72%
  brave-search (14 calls, 89K tokens) ....... 28%
```
- Compare costs across different MCP servers
- Make informed decisions about which servers to use
- Pin servers you want to monitor closely

**5. Session Summary on Exit**
```
Session Complete
-------------------------------------------
Duration:     45m 12s
Total Tokens: 1,234,567
  Input:      456,789
  Output:     123,456
  Cached:     654,322

Estimated Cost: $2.34
Cache Savings:  $1.56

Top Tools:
  mcp__zen__thinkdeep ...... 450K tokens (36%)
  mcp__brave-search__web ... 123K tokens (10%)
```
- Clear summary when you're done
- Useful for comparing sessions
- Export for team sharing

### Power User Workflow

```bash
# 1. Start mcp-audit BEFORE starting Claude Code
mcp-audit collect --platform claude-code

# 2. Work normally in Claude Code
# (Real-time TUI shows token consumption)

# 3. Stop with Ctrl+C when done
# (Session saved automatically)

# 4. Review weekly/monthly patterns
mcp-audit report ~/.mcp-audit/sessions/
```

---

## Platform-Specific Benefits

### Claude Code Users

| Feature | Benefit |
|---------|---------|
| Cache tracking | Understand Anthropic's cache efficiency |
| Context limit visibility | Know when you're approaching limits |
| Model detection | See which Claude model is being used |
| Session file monitoring | Zero-config automatic tracking |

**Pain Point Addressed**: "Why did I hit the context limit?"

### Codex CLI Users

| Feature | Benefit |
|---------|---------|
| Direct cost tracking | Know exactly what you're paying |
| OpenAI model pricing | Accurate cost estimates |
| Cross-platform normalization | Same analysis format as Claude Code |
| Real-time monitoring | Watch costs accumulate |

**Pain Point Addressed**: "What am I actually spending on Codex?"

### Gemini CLI Users

| Feature | Benefit |
|---------|---------|
| Native session parsing | No OTEL setup required |
| Thinking token tracking | See reasoning costs separately |
| Google model pricing | Accurate cost estimates |
| Tool call detection | Track MCP server usage |

**Pain Point Addressed**: "How does Gemini CLI compare to alternatives?"

---

## mcp-audit vs ccusage

| Tool | Focus | Use Case |
|------|-------|----------|
| [ccusage](https://github.com/ryoppippi/ccusage) | Historical trends | "What did I spend this month?" |
| mcp-audit | Session tracking | "What's eating context right now?" |

ccusage is a historical analyzer—it tracks long-term usage trends (daily, monthly, all-time). mcp-audit is a **session tracker**—real-time visibility into what's happening *right now*, with per-tool granularity to investigate context bloat & high token usage as it happens.

---

## Universal Benefits

### For Everyone

| Feature | Benefit |
|---------|---------|
| **Privacy-first** | All data stays local, no prompts stored |
| **Free & open-source** | MIT license, no cost to use |
| **Easy installation** | `pip install mcp-audit` |
| **Zero config needed** | Works out of the box |
| **Signal handling** | Ctrl+C saves data gracefully |
| **Multiple output formats** | JSON, CSV, Markdown reports |
| **Configurable pricing** | TOML file for custom model pricing |
| **Schema documentation** | Clear data contract for automation |

### Privacy Guarantees

- **No prompts stored** - Only token counts and tool names
- **No network requests** - Zero telemetry, no cloud sync
- **Local storage only** - All data in `~/.mcp-audit/`
- **Redaction hooks** - Customize what gets logged

---

## Feature Comparison: Free vs What You'd Build

| Capability | Manual (grep + spreadsheets) | mcp-audit |
|------------|------------------------------|-----------|
| Real-time tracking | Not possible | Live TUI |
| Per-tool metrics | Hours of parsing | Automatic |
| Cache analysis | Complex calculation | Built-in |
| Cross-session trends | Manual aggregation | One command |
| Cost estimation | Manual lookup | Auto pricing |
| Signal handling | Data loss risk | Graceful save |

---

## Quick Reference

### Installation
```bash
pip install mcp-audit
```

### Track a Session
```bash
mcp-audit collect --platform claude-code
```

### Generate Report
```bash
mcp-audit report ~/.mcp-audit/sessions/
```

### More Information
- [README](../README.md) - Full documentation
- [Architecture](architecture.md) - System design
- [Data Contract](data-contract.md) - Schema guarantees
- [Privacy & Security](privacy-security.md) - Data handling

---

*v0.3.11 | Schema v1.1.0 | MIT License*
