# Features & Benefits by Audience

Token Audit v1.0.0 - Features mapped to benefits for each target audience.

---

## At a Glance

| Feature | MCP Tool Developers | AI Coding Power Users |
|---------|---------------------|----------------------|
| Real-time TUI | See tool efficiency live | Watch context consumption |
| Per-tool metrics | Benchmark your implementations | Find expensive tools |
| Per-server breakdown | Isolate server-level issues | Compare MCP server costs |
| Built-in tool tracking | Monitor CLI-native tools | See total tool usage |
| Cache analysis | Optimize cache behavior | Understand cache efficiency |
| Duplicate detection | Find redundant API calls | Spot wasted tokens |
| Cross-session reports | Track optimization progress | Long-term cost trends |
| Cost estimation | Price your tools accurately | Budget planning |
| Privacy-first design | Safe to use in production | No data leaves your machine |
| **Smell detection** (v0.5.0) | Find anti-patterns in your tools | Identify inefficient usage |
| **AI prompt export** (v0.5.0) | Export for automated analysis | Let AI analyze your sessions |
| **Zombie tool detection** (v0.5.0) | Find unused tools in schema | Reduce context overhead |
| **Data quality indicators** (v0.5.0) | Know estimation accuracy | Understand data confidence |
| **Multi-model tracking** (v0.6.0) | Track model switches mid-session | Per-model cost breakdown |
| **Dynamic pricing** (v0.6.0) | Auto-fetch current pricing | Always accurate costs |
| **Context tax tracking** (v0.6.0) | Measure MCP schema overhead | See static context cost per server |
| **Rate metrics** (v0.7.0) | See tokens/min and calls/min | Monitor session velocity |
| **Cache hit ratio** (v0.7.0) | Token-based cache utilization | Understand cache effectiveness |
| **Unique tools count** (v0.7.0) | Tool diversity in MCP panel | See tool spread at a glance |
| **Performance optimization** (v0.9.0) | Sub-ms TUI refresh for production | Smooth real-time monitoring |
| **API stability tiers** (v0.9.0) | Stable APIs for integration | Know which APIs won't break |
| **Profiling guide** (v0.9.0) | cProfile/tracemalloc docs | Optimize your own MCP tools |
| **Tiered pricing** (v0.9.1) | Accurate costs for large sessions | Better budget estimates |
| **Fallback pricing persistence** (v0.9.1) | Offline resilience | Always have pricing data |
| **Session recommendations storage** (v0.9.1) | Programmatic access to suggestions | AI analysis of sessions |
| **MCP Server Mode** (v1.0.0) | Real-time efficiency feedback | In-agent monitoring |
| **8 MCP tools** (v1.0.0) | Track, analyze, recommend in-agent | Live metrics + guidance |
| **Best practices system** (v1.0.0) | 10 MCP design patterns | Learn curated guidance |
| **Config analyzer** (v1.0.0) | Security issue detection | Find misconfigurations |
| **LiveTracker JSONL** (v1.0.0) | Real-time streaming writes | Incremental session data |
| **MCP resources** (v1.0.0) | Resource-based pattern access | Queryable best practices |

---

## v1.0.0 Features: MCP Server Mode

v1.0.0 introduces **MCP Server Mode** — real-time efficiency tracking directly inside your AI coding agent. No separate terminal needed.

### MCP Server Overview

Run token-audit as an MCP server that your AI agent can query directly:

```bash
# Start as MCP server (stdio transport)
token-audit-server
```

**8 MCP Tools available:**

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `start_tracking` | Begin live session tracking | `platform`, `project_name` |
| `get_metrics` | Query current session stats | `include_smells`, `include_breakdown` |
| `get_recommendations` | Get optimization suggestions | `severity_filter`, `max_recommendations` |
| `analyze_session` | Deep session analysis | `session_id` |
| `get_best_practices` | Query MCP design patterns | `category`, `topic` |
| `analyze_config` | Multi-platform config discovery | `platform` |
| `get_pinned_servers` | Detect pinned servers | `source` |
| `get_trends` | Cross-session aggregation | `date_range`, `platform` |

### LiveTracker (JSONL Streaming)

Real-time session tracking with incremental JSONL writes:

```json
{"event": "session_start", "timestamp": "2025-12-17T10:00:00Z", "platform": "claude-code"}
{"event": "tool_call", "tool": "mcp__zen__chat", "input_tokens": 1234, "output_tokens": 567}
{"event": "smell_detected", "pattern": "CHATTY", "severity": "warning", "tool": "mcp__zen__chat"}
{"event": "session_end", "total_tokens": 45000, "cost_usd": 0.12}
```

- Thread-safe incremental writes
- Graceful JSONL → JSON conversion on completion
- In-memory metrics for fast queries

### Best Practices System

10 curated MCP design patterns with severity levels:

| Category | Pattern | Severity |
|----------|---------|----------|
| Security | Credential protection, input validation | critical |
| Progressive Disclosure | Minimal prompts, on-demand details | high |
| Tool Design | Single responsibility, clear naming | high |
| Caching Strategy | Cache-friendly operations, TTL hints | medium |
| Error Handling | Graceful degradation, informative errors | high |
| Schema Design | Minimal required fields, versioning | medium |
| Performance | Batch operations, lazy loading | medium |
| Testing | Mock servers, integration tests | low |
| Observability | Structured logging, metrics exposure | low |
| Versioning | Semantic versioning, deprecation warnings | medium |

Export patterns:
```bash
token-audit export best-practices --format markdown
token-audit export best-practices --category security --format json
```

### Config Analyzer

Multi-platform MCP configuration discovery and security analysis:

```bash
# Analyze config via CLI
token-audit analyze-config

# Via MCP tool
# Returns: servers, pinned servers, security issues
```

**Detects issues:**
- Credential exposure (hardcoded API keys, tokens)
- Excessive server count (>15 servers)
- Path issues (invalid/missing paths)
- Duplicate servers
- Parse errors

**Pinned server detection** (3 methods):
1. Explicit JSON config (`SOURCE_EXPLICIT`)
2. Project CLAUDE.md files
3. Global settings

### MCP Resources

Three resource endpoints for pattern access:

| URI | Returns |
|-----|---------|
| `token-audit://best-practices` | Index of all patterns by severity |
| `token-audit://best-practices/{id}` | Detailed pattern content |
| `token-audit://best-practices/category/{category}` | Patterns filtered by category |

---

## v0.9.1 Features: Pricing & Reliability

v0.9.1 introduces pricing enhancements and reliability fixes for production use.

### Tiered Pricing Support

Accurate cost calculation for sessions exceeding token thresholds:

| Model Family | Threshold | Above-Threshold Pricing |
|--------------|-----------|------------------------|
| Claude models | 200K tokens | Higher input/output rates |
| Gemini models | 128K tokens | Higher input/output rates |

Automatic detection based on model name — no configuration needed.

### Fallback Pricing Persistence

Pricing data persisted to `~/.token-audit/fallback-pricing.json`:

- Saved whenever LiteLLM API fetch succeeds
- Used when cache expires and API unavailable
- Never expires — always available as last resort

**Fallback chain**: API → cache (24h) → fallback file → TOML → defaults

### Session Recommendations Storage

Recommendations now included in session output:

```json
{
  "recommendations": [
    {
      "type": "REMOVE_UNUSED_SERVER",
      "confidence": 0.85,
      "evidence": "Server 'zen' has 3 unused tools",
      "action": "Consider removing unused tools from schema",
      "impact": {"token_savings": 450}
    }
  ]
}
```

Accessible for AI analysis via export:
```bash
token-audit report --format ai
```

### Bug Fixes

- **Session browser**: Fixed platform directory lookup (underscores vs hyphens)
- **Session browser**: Fixed file extension scanning (.jsonl + .json)
- **Codex CLI TUI**: Auto-detects completed sessions (>5 seconds old with data)

---

## v0.9.0 Features: Polish + Stability

v0.9.0 introduces the "Polish + Stability" theme — performance optimization and API stability for production readiness.

### Performance Optimization

Sub-millisecond TUI refresh with dirty-flag caching:

- **TUI dirty-flag caching**: Only rebuild panels whose data changed (15x faster)
- **Storage mtime caching**: 60-second TTL reduces stat() calls (33% faster)
- **Header peeking**: 4KB reads for metadata (10-100x faster metadata queries)

### API Stability Tiers

30 public exports with explicit stability classification:

- **stable** (16 APIs): Guaranteed backward-compatible through v1.x
- **evolving** (13 APIs): Stable interface, implementation may change
- **deprecated** (1 API): `estimate_tool_tokens` → use `TokenEstimator.estimate_tool_call()`

### Profiling Guide

`docs/profiling.md` with cProfile and tracemalloc examples for profiling your own MCP tools.

---

## v0.7.0 Features: UI Layer

v0.7.0 introduces the "UI Layer" — enhanced TUI metrics for monitoring session velocity and cache effectiveness.

### Rate Metrics

Real-time tokens/min and calls/min in the Token Usage panel:

```
Token Usage
──────────────────────────────────────
Input:       45,231    Output:    12,345
Cached:     125,000    Total:    182,576
Token Rate: 15.2K/min  Call Rate: 3.2/min
```

- **Tokens/min**: Shows session velocity — how fast you're consuming context
- **Calls/min**: Shows tool activity rate — higher rates may indicate chatty patterns
- Formats large rates automatically (K/min, M/min)

### Cache Hit Ratio

Token-based cache utilization (distinct from cost-based efficiency):

```
Cache Efficiency: 11.9% (cost-based)
Cache Hit:        95.2% (token-based)
```

| Metric | Formula | What It Shows |
|--------|---------|---------------|
| Cache Efficiency | Cost savings % | How much money cache saves |
| Cache Hit Ratio | `cache_read / (cache_read + input)` | What % of input comes from cache |

**Why both?** High cache hit doesn't always mean high cost savings (depends on pricing). Both metrics together give the full picture.

### Unique Tools Count

MCP Servers panel now shows tool diversity:

```
MCP Servers (4 servers, 12 tools, 47 calls)
```

- **Servers**: How many MCP servers are active
- **Unique tools**: Tool diversity (vs. relying on same tools repeatedly)
- **Total calls**: Overall MCP activity

### AI Export Enhancements

Rate metrics and cache hit ratio are now included in AI exports:

```bash
token-audit report --format ai
```

The export includes:
- Token rate and call rate metrics
- Cache hit ratio (token-based)
- Unique tools count
- All existing metrics and analysis

---

## v0.5.0 Features: Insight Layer

v0.5.0 introduces the "Insight Layer" — automatic detection of efficiency anti-patterns, AI-exportable session data, and data quality indicators.

### Smell Detection Engine

Automatically detect 5 efficiency anti-patterns during sessions:

| Pattern | Severity | Threshold | What It Means |
|---------|----------|-----------|---------------|
| `HIGH_VARIANCE` | warning | CV > 50% | Token counts vary wildly — consider batching |
| `TOP_CONSUMER` | info | >50% of tokens | Single tool dominates — investigate or optimize |
| `HIGH_MCP_SHARE` | info | >80% of tokens | Heavy MCP reliance — may be opportunity to use built-ins |
| `CHATTY` | warning | >20 calls | Too many calls — consider batching or caching |
| `LOW_CACHE_HIT` | warning | <30% ratio | Cache underutilized — reorder operations for reuse |

Smells appear in session logs with severity, description, and evidence:
```json
{
  "smells": [
    {
      "pattern": "CHATTY",
      "severity": "warning",
      "tool": "mcp__zen__chat",
      "description": "Called 25 times",
      "evidence": {"call_count": 25, "threshold": 20}
    }
  ]
}
```

### AI Prompt Export

Export session data for analysis by your AI assistant:

```bash
# Export as structured markdown
token-audit report --format ai

# Export as JSON for programmatic use
token-audit report --format ai-json
```

The export includes:
- Session summary (tokens, costs, duration)
- Top tools by token consumption
- Detected smells with evidence
- Data quality indicators
- Suggested analysis questions

### Zombie Tool Detection

Identify MCP tools defined in server schemas but never called:

```toml
# token-audit.toml
[zombie_tools.zen]
tools = [
    "mcp__zen__thinkdeep",
    "mcp__zen__debug",
    "mcp__zen__refactor"
]
```

Session logs report unused tools per server:
```json
{
  "zombie_tools": {
    "zen": ["mcp__zen__refactor", "mcp__zen__precommit"]
  }
}
```

Each unused tool's schema contributes to context overhead without providing value.

### Data Quality Indicators

Every session now includes accuracy metadata:

```json
{
  "data_quality": {
    "accuracy_level": "estimated",
    "token_source": "tiktoken",
    "token_encoding": "o200k_base",
    "confidence": 0.99,
    "notes": "Tokens estimated using tiktoken o200k_base (~99% accuracy)"
  }
}
```

| Accuracy Level | Description | Platforms |
|----------------|-------------|-----------|
| `exact` | Native platform tokens | Claude Code |
| `estimated` | Tokenizer-based estimation | Codex CLI, Gemini CLI |
| `calls-only` | Only call counts, no tokens | Ollama CLI (v1.1.0) |

---

## v0.6.0 Features: Multi-Model Intelligence

v0.6.0 introduces "Multi-Model Intelligence" — track sessions that switch between models, auto-fetch current pricing from LiteLLM, and measure MCP schema overhead.

### Multi-Model Per-Session Tracking

Track token usage when sessions switch between models (e.g., claude-3-5-sonnet → claude-3-5-haiku):

```
Models Used: claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022
───────────────────────────────────────────────────────────────
Model                          Input      Output    Cost
claude-3-5-sonnet-20241022     45,231     12,345    $0.2134
claude-3-5-haiku-20241022      8,765      2,100     $0.0087
```

Session logs include per-model breakdown:
```json
{
  "models_used": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
  "model_usage": {
    "claude-3-5-sonnet-20241022": {
      "input_tokens": 45231,
      "output_tokens": 12345,
      "cost_usd": 0.2134,
      "call_count": 15
    },
    "claude-3-5-haiku-20241022": {
      "input_tokens": 8765,
      "output_tokens": 2100,
      "cost_usd": 0.0087,
      "call_count": 5
    }
  }
}
```

### Dynamic Pricing via LiteLLM

Auto-fetch current pricing for 2,000+ models from the [LiteLLM pricing database](https://github.com/BerriAI/litellm):

```toml
# token-audit.toml — configure pricing behavior
[pricing.api]
enabled = true           # Enable API pricing (default: true)
cache_ttl_hours = 24     # Cache pricing for 24 hours
offline_mode = false     # Use TOML-only pricing
```

**Fallback chain**: API → TOML config → built-in defaults

Session logs include pricing source:
```json
{
  "data_quality": {
    "pricing_source": "api",
    "pricing_freshness": "2025-12-12T10:30:00Z"
  }
}
```

| Source | Description | Models |
|--------|-------------|--------|
| `api` | LiteLLM API (auto-refresh) | 2,000+ |
| `toml` | Local token-audit.toml | Custom |
| `default` | Built-in fallback | ~20 |

### Context Tax Tracking

Measure the "context tax" — the static token overhead from MCP server schemas that consume context before any work begins:

```
Context Tax
─────────────────────────────────────
Total: 6,450 tokens (static overhead)
Confidence: 80%

Per Server:
  zen ............. 3,000 tokens
  backlog ......... 2,250 tokens
  brave-search .... 1,200 tokens

Zombie Tax: +450 tokens (unused tools)
```

| Source | Description | Confidence |
|--------|-------------|------------|
| `known_db` | Pre-measured tool counts | 90% |
| `estimate` | Default 10 tools × 175 tokens | 70% |
| `mixed` | Combination of known + estimated | Weighted average |

Session logs include static cost breakdown:
```json
{
  "static_cost": {
    "total_tokens": 6450,
    "source": "mixed",
    "by_server": {
      "zen": 3000,
      "backlog": 2250,
      "brave-search": 1200
    },
    "confidence": 0.8
  }
}
```

**TUI Panel**: When context tax is detected, a dedicated panel shows:
- Total static token overhead
- Per-server breakdown with token counts
- Zombie tool context tax (unused tools adding overhead)
- Confidence indicator based on data source

**Known Servers Database**: Pre-measured token counts for popular MCP servers:
- `backlog` (15 tools, ~2,250 tokens)
- `brave-search` (6 tools, ~1,200 tokens)
- `zen` (12 tools, ~3,000 tokens)
- `jina` (20 tools, ~3,600 tokens)
- `context7` (5 tools, ~750 tokens)

Unknown servers use conservative estimate: 10 tools × 175 tokens/tool.

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
token-audit report ~/.token-audit/sessions/ --format csv --output analysis.csv
```
- Track optimization progress over time
- Compare before/after metrics
- Export to spreadsheet for deeper analysis

### Developer Workflow

```bash
# 1. Track while developing
token-audit collect --platform claude-code --pin-server myserver

# 2. Work with your MCP tools
# (Real-time TUI shows per-tool metrics)

# 3. Review session results
token-audit report ~/.token-audit/sessions/

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
Token Audit - Live Session
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
# 1. Start token-audit BEFORE starting Claude Code
token-audit collect --platform claude-code

# 2. Work normally in Claude Code
# (Real-time TUI shows token consumption)

# 3. Stop with Ctrl+C when done
# (Session saved automatically)

# 4. Review weekly/monthly patterns
token-audit report ~/.token-audit/sessions/
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
| Built-in tool summary | Track Bash, Read, Edit, Glob usage in session files |

**Pain Point Addressed**: "Why did I hit the context limit?"

### Codex CLI Users

| Feature | Benefit |
|---------|---------|
| Direct cost tracking | Know exactly what you're paying |
| OpenAI model pricing | Accurate cost estimates |
| Cross-platform normalization | Same analysis format as Claude Code |
| Real-time monitoring | Watch costs accumulate |
| Reasoning token tracking | See thinking tokens for o-series models (v1.3.0) |
| Built-in tool call counts | Track shell, read_file, apply_patch, etc. |

**Pain Point Addressed**: "What am I actually spending on Codex?"

**Note**: Codex CLI provides turn-level tokens only. Built-in tool call counts are tracked but per-tool token attribution is not available from the platform. Reasoning tokens (from o1, o3 models) are tracked separately from output tokens.

### Gemini CLI Users

| Feature | Benefit |
|---------|---------|
| Native session parsing | No OTEL setup required |
| Reasoning token tracking | See thinking/reasoning costs separately (v1.3.0) |
| Google model pricing | Accurate cost estimates |
| Tool call detection | Track MCP and built-in tool usage |
| Built-in tool call counts | Track read_file, list_directory, etc. |
| Optional Gemma tokenizer | 100% accurate token estimation (v0.4.0) |

**Pain Point Addressed**: "How does Gemini CLI compare to alternatives?"

**Note**: Gemini CLI provides message-level tokens only. Built-in tool call counts are tracked but per-tool token attribution is not available from the platform. Reasoning tokens (Gemini's `thoughts` field) are tracked separately from output tokens.

**Token Estimation** (v0.4.0): For 100% accurate MCP tool token estimation, run `token-audit tokenizer download` to get the Gemma tokenizer from GitHub Releases (no account required). Without it, token-audit uses tiktoken (~95% accuracy) and displays a hint during collection.

---

## token-audit vs ccusage

| Tool | Focus | Use Case |
|------|-------|----------|
| [ccusage](https://github.com/ryoppippi/ccusage) | Historical trends | "What did I spend this month?" |
| token-audit | Session tracking | "What's eating context right now?" |

ccusage is a historical analyzer—it tracks long-term usage trends (daily, monthly, all-time). token-audit is a **session tracker**—real-time visibility into what's happening *right now*, with per-tool granularity to investigate context bloat & high token usage as it happens.

---

## Universal Benefits

### For Everyone

| Feature | Benefit |
|---------|---------|
| **Privacy-first** | All data stays local, no prompts stored |
| **Free & open-source** | MIT license, no cost to use |
| **Lightweight install** | `pip install token-audit` (~500KB, optional tokenizer) |
| **Zero config needed** | Works out of the box |
| **Signal handling** | Ctrl+C saves data gracefully |
| **Multiple output formats** | JSON, CSV, Markdown reports |
| **Configurable pricing** | TOML file for custom model pricing |
| **Schema documentation** | Clear data contract for automation |
| **Theme support** | Catppuccin dark/light, high-contrast, auto-detect |
| **Accessibility** | ASCII mode, NO_COLOR standard, WCAG AAA themes |

### Privacy Guarantees

- **No prompts stored** - Only token counts and tool names
- **No network requests** - Zero telemetry, no cloud sync
- **Local storage only** - All data in `~/.token-audit/`
- **Redaction hooks** - Customize what gets logged

---

## Feature Comparison: Free vs What You'd Build

| Capability | Manual (grep + spreadsheets) | token-audit |
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
pip install token-audit
```

### Track a Session
```bash
token-audit collect --platform claude-code
```

### Generate Report
```bash
token-audit report ~/.token-audit/sessions/
```

### More Information
- [README](../README.md) - Full documentation
- [Architecture](architecture.md) - System design
- [Data Contract](data-contract.md) - Schema guarantees
- [Privacy & Security](privacy-security.md) - Data handling

---

*v1.0.0 | Schema v1.7.0 | MIT License*
