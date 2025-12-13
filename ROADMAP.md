# Roadmap

This document outlines the planned development direction for MCP Audit. For completed features, see the [Changelog](CHANGELOG.md).

## Current Status

**Version**: v0.7.0
**Stage**: UI Layer — Rate Metrics, Cache Hit Ratio, Unique Tools Display

MCP Audit provides stable support for Claude Code, Codex CLI, and Gemini CLI. v0.7.0 adds real-time rate metrics (tokens/min, calls/min), cache hit ratio tracking, and unique tools display in the TUI.

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

## v0.8.0 — Analysis Layer

**Theme:** "Understand Your Usage"

Deeper analysis capabilities and improved AI integration.

- **Expanded Smell Categories** — 7+ new patterns (REDUNDANT_CALLS, BURST_PATTERN, etc.)
- **Recommendation Context** — Non-automatic suggestions for AI consumption
- **Cross-Session Aggregation** — Smell trends and frequencies across sessions
- **Improved AI Export** — Richer context, comparison data, structured recommendations
- **Schema v1.7.0** — Expanded smell taxonomy, recommendations block

**Success Metrics:**
- 12+ smell patterns detected
- AI exports include actionable recommendations
- Users can see smell trends across sessions

➡️ [View Milestone](https://github.com/littlebearapps/mcp-audit/milestone/4)

---

## v0.9.0 — Polish + Stability

**Theme:** "Ready for Production"

Prepares for v1.0 with documentation, examples, and API stability.

- **Documentation Overhaul** — Comprehensive guides for all features
- **Usage Examples** — 5+ real-world scenario walkthroughs
- **API Cleanup** — Deprecate unstable APIs, document public surface
- **Final Schema v1.0.0** — Stability guarantees, JSON Schema validation
- **Performance Optimization** — <100ms TUI refresh, <500ms session load
- **Landing Page Content** — Draft copy and assets for website

**Success Metrics:**
- Complete documentation for all features
- 5+ real-world usage examples
- No breaking API changes after this release
- Sub-100ms TUI refresh performance

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

### v1.2+ — Developer Insight
- Context window tracking (per-turn token load)
- TUI: Tool Detail mode
- Platform capability warnings

### v1.3+ — Payload Analysis
- Dynamic payload heatmap
- Full schema tokenizer
- Description density scoring

### v1.4+ — Cross-Model Analysis
- Model behavior differences
- Tool families/categories
- Baseline session support

### v1.5+ — Comparison Suite
- Session drift detection
- Enhanced TUI comparison mode

### v2.0+ — Long-Term Vision
- Cross-session trend engine (time-series analysis)
- Team/enterprise features (aggregate tracking)
- Plugin architecture (dynamic adapters)
- Cross-platform unified dashboard

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

**Last Updated**: December 2025
