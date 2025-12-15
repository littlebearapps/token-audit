# Roadmap

This document outlines the planned development direction for MCP Audit. For completed features, see the [Changelog](CHANGELOG.md).

## Current Status

**Version**: v0.9.0
**Stage**: Polish + Stability — Performance Optimization, API Stability, Profiling Guide

MCP Audit provides stable support for Claude Code, Codex CLI, and Gemini CLI. v0.9.0 adds sub-millisecond TUI refresh, 14 performance benchmarks in CI, explicit API stability tiers for all 30 public exports, and comprehensive profiling documentation.

---

## ✅ v0.5.0 — Insight Layer (Released)

**Theme:** "See What's Wrong"

The foundation for efficiency insights and AI-assisted analysis.

- ✅ **Smell Engine MVP** — Detect 5 efficiency patterns: HIGH_VARIANCE, TOP_CONSUMER, HIGH_MCP_SHARE, CHATTY, LOW_CACHE_HIT
- ✅ **Zombie Tool Detection** — Identify MCP tools defined but never called
- ✅ **Data Quality System** — Accuracy labels: exact/estimated/calls-only
- ✅ **AI Prompt Export MVP** — `mcp-audit export ai-prompt` for AI analysis
- ✅ **Schema v1.5.0** — `smells`, `data_quality`, `zombie_tools` blocks

**Success Metrics:**
- ✅ Users can identify inefficient MCP usage patterns
- ✅ AI assistants can consume session data for analysis
- ✅ Clear accuracy labeling for all metrics

➡️ [View Milestone](https://github.com/littlebearapps/mcp-audit/milestone/1)

---

## ✅ v0.6.0 — Multi-Model Intelligence (Released)

**Theme:** "Track Everything"

Multi-model tracking and dynamic pricing infrastructure.

- ✅ **Multi-Model Tracking** — Per-model tokens/costs when switching models mid-session
- ✅ **Dynamic Pricing** — LiteLLM pricing API (2,000+ models) with 24h caching and TOML fallback
- ✅ **Static Cost Foundation** — Infrastructure for MCP schema "context tax" (full impl deferred)
- ✅ **Schema v1.6.0** — `models_used`, `model_usage`, `pricing_source` blocks

**Note:** Ollama CLI Adapter moved to v1.1.0 post-1.0 (requires API proxy approach).

**Success Metrics:**
- ✅ Sessions with model switches show per-model breakdown
- ✅ Pricing stays current via LiteLLM API
- ✅ 3 platforms supported: Claude Code, Codex CLI, Gemini CLI

➡️ [View Milestone](https://github.com/littlebearapps/mcp-audit/milestone/2)

---

## ✅ v0.7.0 — UI Layer (Released)

**Theme:** "Explore Your Data"

Enhanced TUI metrics and display improvements.

- ✅ **Rate Metrics** — Real-time tokens/min and calls/min in Token Usage panel
- ✅ **Cache Hit Ratio** — Token-based cache utilization (distinct from cost-based efficiency)
- ✅ **Unique Tools Count** — MCP Servers panel shows tool diversity
- ✅ **AI Export Enhancements** — Rate metrics and cache hit included in exports

**Success Metrics:**
- ✅ Users can see session velocity at a glance
- ✅ Cache effectiveness clearly distinguished from cost efficiency
- ✅ Tool diversity visible in MCP Servers panel

➡️ [View Milestone](https://github.com/littlebearapps/mcp-audit/milestone/3)

---

## ✅ v0.8.0 — Analysis Layer (Released)

**Theme:** "Understand Your Usage"

Deeper analysis capabilities and improved AI integration.

- ✅ **Expanded Smell Detection** — 12 patterns total (7 new: REDUNDANT_CALLS, EXPENSIVE_FAILURES, UNDERUTILIZED_SERVER, BURST_PATTERN, LARGE_PAYLOAD, SEQUENTIAL_READS, CACHE_MISS_STREAK)
- ✅ **Recommendations Engine** — AI-consumable suggestions from detected smells
- ✅ **Cross-Session Aggregation** — Smell trends, frequencies, and filtering across sessions
- ✅ **TUI Notification Bar** — Visual feedback for actions ("Ask AI copied to clipboard")
- ✅ **Enhanced AI Export** — Recommendations and smell context in exports
- ✅ **Schema v1.7.0** — Expanded smell taxonomy, recommendations block

**Success Metrics:**
- ✅ 12 smell patterns detected
- ✅ AI exports include actionable recommendations
- ✅ Users can see smell trends across sessions

➡️ [View Milestone](https://github.com/littlebearapps/mcp-audit/milestone/4)

---

## ✅ v0.9.0 — Polish + Stability (Released)

**Theme:** "Ready for Production"

Performance optimization and API stability for production readiness.

- ✅ **Performance Optimization** — Sub-millisecond TUI refresh, <500ms session load, <100MB memory
  - TUI dirty-flag caching: Only rebuild panels whose data changed (15x faster refresh)
  - Storage mtime caching: 60-second TTL reduces stat() calls (33% faster listing)
  - Header peeking: 4KB reads for metadata (10-100x faster metadata queries)
- ✅ **Performance Benchmarks** — 14 CI-integrated benchmark tests
- ✅ **API Stability Tiers** — 30 public exports classified (stable/evolving/deprecated)
- ✅ **API-STABILITY.md** — Comprehensive stability policy documentation
- ✅ **Profiling Guide** — `docs/profiling.md` with cProfile/tracemalloc examples

**Success Metrics:**
- ✅ Sub-100ms TUI refresh performance (achieved <1ms)
- ✅ API stability classification for all public exports
- ✅ Deprecation warnings for unstable APIs

➡️ [View Milestone](https://github.com/littlebearapps/mcp-audit/milestone/5)

---

## v1.0.0 — Product Hunt Launch

**Theme:** "Hello World"

The official stable release with full marketing launch.

- **Landing Page** — littlebearapps.com/mcp-audit
- **Press Kit** — Logos, screenshots, descriptions, one-pager
- **Blog Post** — v1.0 announcement with journey and features
- **Video Demos** — 6 demo videos covering all features
- **Product Hunt** — Full launch execution
- **Social Announcements** — Coordinated launch campaign
- **Final QA & Release** — Quality assurance and release execution

**Success Metrics:**
- Successful Product Hunt launch
- Landing page live with conversion tracking
- Press kit downloadable
- Blog post published
- Video demos created

➡️ [View Milestone](https://github.com/littlebearapps/mcp-audit/milestone/6)

---

## Post-v1.0 Vision

> **Note:** The following roadmap items represent our current thinking and are subject to change based on community feedback, ecosystem developments (particularly AAIF governance decisions), and technical discoveries during implementation. Features may be added, removed, reordered, or combined as we learn more.

### v1.1.0 — Ollama CLI Support

**Theme:** "Local Model Tracking"

Adds support for Ollama CLI via API proxy approach.

- **Ollama API Proxy** — `mcp-audit ollama-proxy` command for local model tracking
- **Exact Token Counts** — Track via `prompt_eval_count` and `eval_count`
- **Zero-Cost Sessions** — Sessions with $0 cost (local models)
- **Tool Call Tracking** — Capture Ollama's native tool format

**Success Metrics:**
- Ollama users can track local model sessions via proxy
- 4 platforms supported: Claude Code, Codex CLI, Gemini CLI, Ollama CLI

➡️ [View Milestone](https://github.com/littlebearapps/mcp-audit/milestone/10)

### v1.2.0 — Platform Expansion

**Theme:** "More Platforms"

Adds support for AAIF reference runtime and market-leading IDE.

- **goose Adapter** — Block's AAIF founding project (MCP-native, 24k+ GitHub stars)
- **Cursor Adapter** — Market-leading AI IDE (session format research required)
- **AGENTS.md Parsing** — Extract project context from OpenAI's agent config standard

**Success Metrics:**
- goose sessions fully tracked
- Cursor sessions tracked
- 6 platforms supported: Claude Code, Codex CLI, Gemini CLI, Ollama, goose, Cursor

### v1.3.0 — Developer Insight

**Theme:** "Deeper Analysis"

- Context window tracking (per-turn token load)
- Platform capability warnings
- TUI: Tool Detail mode

### v1.4.0 — IDE Extensions

**Theme:** "VS Code Ecosystem"

- **Cline Adapter** — Open source VS Code extension (2M+ installs)
- **Aider Adapter** — Popular open source CLI
- 8 platforms total

### v1.5.0 — Security Research (P0)

**Theme:** "Security Foundation"

**Why Security is Critical:** MCP security is the #1 ecosystem concern in 2025. Key vulnerabilities include CVE-2025-6515 (Prompt Hijacking), CVE-2025-6514 (mcp-remote RCE), and tool poisoning attacks. 88% of MCP servers require credentials; 53% use insecure long-lived tokens.

**Approach:** Hybrid — research both MCP-scan integration AND custom security patterns, then decide based on findings.

- **MCP-scan Integration Evaluation** — Assess Invariant Labs' detection capabilities
- **Custom Security Smells** — Design 5 new patterns:
  - `SUSPICIOUS_DESCRIPTION` — Hidden instructions in tool descriptions
  - `EXFILTRATION_RISK` — Data flow to external endpoints
  - `CREDENTIAL_EXPOSURE` — Plaintext secrets in tool calls
  - `CROSS_SERVER_SHADOWING` — Tool name conflicts
  - `UNAUTHORIZED_SCOPE` — Tools accessing unexpected resources
- **Tool Description Scanner** — Flag suspicious patterns in MCP tool definitions
- **Security Posture Scoring Prototype** — Per-session security rating (0-100)

### v1.6.0 — Payload Analysis

**Theme:** "Schema Intelligence"

- Dynamic payload heatmap
- Full schema tokenizer
- Description density scoring

### v1.7.0 — Cross-Platform Analysis

**Theme:** "Compare Everything"

- Platform efficiency comparison (Claude vs Cursor vs Gemini)
- Baseline session support
- Model behavior differences

### v1.8.0 — Security Implementation (P0)

**Theme:** "Security Layer"

Full implementation of security features based on v1.5.0 research findings.

- **Toxic Flow Analysis** — Map data exfiltration risks across tool calls
- **Security Posture Scoring** — Production-ready per-session security rating
- **Credential Exposure Detection** — Identify plaintext credentials in tool parameters
- **Security Panel in TUI** — Visual security indicators and alerts
- **Security Recommendations** — AI-consumable security suggestions

### v1.9.0 — Comparison Suite

**Theme:** "Session Intelligence"

- Session drift detection
- Enhanced TUI comparison mode
- Cross-session trend engine (time-series)

### v2.0.0 — Enterprise Platform

**Theme:** "Enterprise Ready"

Major platform release with breaking changes.

- **Plugin Architecture** — Dynamic adapter loading for community contributions
- **Schema v2.0** — Security blocks, multi-platform metadata (breaking changes)
- **Cross-Platform Dashboard** — Unified view across all platforms
- **Team Features** — Aggregate tracking, governance reports, cost allocation
- **Security Suite** — Full toxic flow analysis, security posture, credential detection
- **AAIF Compliance** — Verify sessions against MCP spec versions

**Context:** MCP was donated to the Linux Foundation's Agentic AI Foundation (AAIF) in December 2025. goose (Block) and AGENTS.md (OpenAI) are co-founding projects. v2.0 aligns mcp-audit with this vendor-neutral ecosystem.

---

## Contributing Ideas

We welcome community input on the roadmap!

- **Feature requests**: [Start a Discussion](https://github.com/littlebearapps/mcp-audit/discussions/new?category=ideas)
- **View all ideas**: [Ideas Board](https://github.com/littlebearapps/mcp-audit/discussions/categories/ideas)
- **Questions**: [Q&A Discussions](https://github.com/littlebearapps/mcp-audit/discussions/categories/q-a)

---

## Disclaimer

This roadmap represents our current development plans and is subject to change. Items may be added, removed, or reprioritized based on community feedback, technical constraints, and resource availability. This roadmap does not represent a commitment to deliver any specific feature by any particular date.

---

**Last Updated**: December 14, 2025
