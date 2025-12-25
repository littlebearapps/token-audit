# Changelog

All notable changes to Token Audit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Note:** Starting with v0.5.0, feature entries link to GitHub Issues where applicable (e.g., `[#16](url)`).
> Bug fixes always link to their issue. Earlier versions reference internal task IDs.

## [1.0.0] - 2025-12-17

First public release with MCP server mode and best practices guidance system.

### Added

#### MCP Server Mode
- **8 MCP Tools** — Full MCP server implementation for AI agent integration
  - `start_tracking`: Start live session tracking with JSONL streaming
  - `get_metrics`: Get current session metrics with rate/cache stats
  - `get_recommendations`: AI-consumable efficiency suggestions
  - `analyze_session`: Deep session analysis with smells detection
  - `get_best_practices`: MCP design patterns and guidance
  - `analyze_config`: Multi-platform config discovery and analysis
  - `get_pinned_servers`: Pinned server detection (3 methods)
  - `get_trends`: Cross-session smell aggregation
- **token-audit-server CLI** — New entry point for MCP server mode
- **LiveTracker** — JSONL streaming for real-time session updates
- **3 MCP Resources** — Best practices exposed via MCP resource protocol
  - `token-audit://best-practices` — Index of all patterns by severity
  - `token-audit://best-practices/{id}` — Detailed pattern content
  - `token-audit://best-practices/category/{category}` — Filtered by category

#### Best Practices System
- **Guidance Module** — 10 curated MCP design patterns
  - Security, Progressive Disclosure, Tool Design, Caching Strategy
  - Error Handling, Schema Design, Performance, Testing, Observability, Versioning
- **get_best_practices Tool** — Query patterns by category or search by topic
- **CLI Command** — `token-audit best-practices` for exporting patterns
  - JSON, YAML, and Markdown output formats
  - Filter by `--category` (efficiency, security, design, operations)
  - Filter by `--severity` (high, medium, low)
  - File output with `--output` option

#### Config Analyzer
- **Multi-Platform Discovery** — Detect MCP configs across Claude/Codex/Gemini
- **Pinned Server Detection** — 3-method detection (explicit JSON, project CLAUDE.md, global settings)
- **Config Issue Detection** — Identify misconfigurations and security concerns

#### Security Enhancements
- **CREDENTIAL_EXPOSURE Smell** — Detect plaintext credentials in tool calls
- **Input Validation** — Path sanitization and parameter validation for MCP server
- **Security Documentation** — `docs/security.md` with security considerations

#### Documentation
- **Integration Guides** — Platform-specific setup documentation
  - `docs/platforms/claude-code.md`
  - `docs/platforms/codex-cli.md`
  - `docs/platforms/gemini-cli.md`
- **MCP Server Guide** — `docs/mcp-server-guide.md` with tool reference
- **Migration Guide** — `docs/MIGRATION-v1.0.md` for v0.9.x → v1.0 upgrade

#### Performance
- **MCP Server Benchmarks** — CI-integrated performance tests for all 8 tools
  - Target: <100ms for most tools, <200ms for analysis operations
  - Target: >1000 events/sec for JSONL streaming
  - Added `TestMCPServerPerformance` class with 9 benchmarks
- **Profiling Documentation** — Updated `docs/profiling.md` with MCP server targets

#### Historical Aggregation (Token Audit)
- **Aggregation Engine** — Cross-session token usage analysis
  - `DailyAggregate`, `WeeklyAggregate`, `MonthlyAggregate` data structures
  - Project grouping with git repo detection
  - Per-model usage breakdown support
  - Microdollar cost storage for precision
- **CLI Commands** — Historical reporting commands
  - `token-audit daily` — Daily usage summary (7/14/30+ days)
  - `token-audit weekly` — Weekly usage with configurable week start (Monday/Sunday)
  - `token-audit monthly` — Monthly usage trends
  - `--json` flag for machine-readable output
  - `--instances` flag for project grouping
  - `--breakdown` flag for per-model details
- **Token Audit Documentation** — `docs/token-audit/` directory
  - Feature overview and quick start guide
  - Capabilities matrix with platform accuracy
  - Implementation plan and design decisions

### Changed

#### CLI Consolidation (9 → 7 commands)
- **`report --format ai`** — Merged `export ai-prompt` into report command
  - Use `--format ai` for AI analysis export
  - Added `--pinned-focus`, `--full-mcp-breakdown`, `--pinned-servers` options
- **`report --smells`** — Merged `smells` command into report
  - Use `--smells` flag to enable smell analysis mode
  - Added `--days`, `--project`, `--min-frequency` options
- **`best-practices`** — Promoted to top-level command (was `export best-practices`)
- **`tokenizer --interactive`** — Added interactive setup wizard (replaces `init`)

- **Storage Architecture** — New `active/` directory for live JSONL streaming sessions
- **API Exports** — Added MCP server components to public API

### Removed
- **`init` command** — Use `token-audit tokenizer --interactive` instead
- **`smells` command** — Use `token-audit report --smells` instead
- **`export` command** — Subcommands merged into `report` and `best-practices`

### Notes
- Schema remains v1.7.0 (no data structure changes)
- Backward compatible: Existing sessions and workflows work unchanged

## [0.9.1] - 2025-12-15

### Added

#### Tiered Pricing Support ([#54](https://github.com/littlebearapps/token-audit/issues/54))
- **Tiered Cost Calculation** — Support for token threshold pricing
  - Claude models: 200K token threshold
  - Gemini models: 128K token threshold
  - Automatic model detection based on model name
- **`_calculate_tiered_cost()` helper** — Calculates cost with base/tiered rates
- **Tiered Pricing Fields** — Parse `input_above_200k`, `output_above_200k`, `input_above_128k`, `output_above_128k` from LiteLLM API

#### Fallback Pricing Auto-Update ([#53](https://github.com/littlebearapps/token-audit/issues/53))
- **Persistent Fallback File** — `~/.token-audit/fallback-pricing.json`
  - Saved whenever LiteLLM API fetch succeeds
  - Used when cache expires and API is unavailable
  - Never expires (always available as last resort)
- **`_save_fallback()`/`_load_fallback()` methods** — Manage fallback storage
- **Fallback Chain**: API → cache (fresh) → fallback → TOML → defaults

#### Session Recommendations Storage ([#69](https://github.com/littlebearapps/token-audit/issues/69))
- **`recommendations` field** — Added to Session dataclass
- **Automatic Generation** — Recommendations generated during `finalize_session()`
- **JSON Persistence** — Recommendations saved in session JSON output

### Fixed

#### Codex CLI TUI Zero Tokens ([#68](https://github.com/littlebearapps/token-audit/issues/68))
- **Auto-detect Completed Sessions** — When Codex CLI session is >5 seconds old with data
  - Automatically enables `--from-start` behavior
  - Prints detection message: "Auto-detected completed session (N lines, Xs old)"
  - Applied to both `monitor()` and `_start_file_tracking()` methods

#### Session Browser Not Finding Sessions
- **Platform Directory Fix** — Storage used underscore names (`claude_code`) but actual directories use hyphens (`claude-code`). Fixed by converting underscores to hyphens in `get_platform_dir()`.
- **File Extension Fix** — `list_sessions()` looked for `*.jsonl` but actual session files are `*.json`. Fixed by scanning for both extensions.

### Changed
- **Pricing API Source Property** — Added "fallback" source type to indicate persistent fallback usage
- **Test Suite** — Added 7 tiered pricing tests in `TestTieredPricing` class

## [0.9.0] - 2025-12-14

### Added

#### Performance Optimization ([#39](https://github.com/littlebearapps/token-audit/issues/39))
- **Performance Benchmarks** — CI-integrated benchmark suite
  - `tests/benchmarks/test_performance.py` with 14 benchmark tests
  - TUI refresh, session loading, memory usage metrics
  - Targets: TUI <100ms, session load <500ms, memory <100MB
  - All targets exceeded by 100-10000x margin
- **Profiling Guide** — `docs/profiling.md` with cProfile/tracemalloc examples

#### TUI Dirty-Flag Caching
- **Panel Caching** — Only rebuild panels whose data changed
  - `_detect_changes()` method compares snapshot fields
  - `_cached_panels` dict stores rendered panels
  - Header, tokens, tools, smells, context_tax panels cached
  - 15x faster refresh for unchanged snapshots (0.15ms → 0.01ms)

#### Storage Performance
- **Mtime Caching** — Reduce stat() calls in `list_sessions()`
  - 60-second TTL cache for file modification times
  - 33% faster session listing (0.69ms → 0.46ms)
- **Header Peeking** — `peek_session_header()` for fast metadata reads
  - Reads first 4KB instead of full JSON parse
  - 10-100x faster for metadata-only queries

#### API Cleanup & Stability (v0.9.0 - [#39](https://github.com/littlebearapps/token-audit/issues/39))
- **API Stability Tiers** — Explicit stability classification for all 30 public exports
  - `stable`: 16 APIs guaranteed backward-compatible through v1.x
  - `evolving`: 13 APIs with stable interface, implementation may change
  - `deprecated`: 1 API scheduled for removal in v1.1.0
- **API Stability Infrastructure** — Programmatic stability checking
  - `API_STABILITY` dictionary with tier classifications
  - `get_api_stability(name)` helper function
  - `StabilityTier` type alias for type hints
- **API-STABILITY.md** — Comprehensive stability policy documentation
  - Tier definitions and guarantees
  - Version compatibility promises
  - Migration guides for deprecated APIs
- **Deprecation Warnings** — Runtime warnings for deprecated APIs
  - `estimate_tool_tokens` now emits `DeprecationWarning`
  - Migration path: use `TokenEstimator.estimate_tool_call()` instead

### Changed
- **Benchmark CI Job** — Added to `.github/workflows/ci.yml`
- **RichDisplay** — Refactored `_build_layout()` for selective panel rebuilding
- **API.md** — Updated with stability tier indicators and new import examples

### Deprecated
- **`estimate_tool_tokens`** — Use `TokenEstimator.estimate_tool_call()` instead
  - Deprecated in v0.9.0, will be removed in v1.1.0
  - See [API-STABILITY.md](docs/API-STABILITY.md) for migration guide

## [0.8.0] - 2025-12-14

### Added

#### Expanded Smell Detection (12 Patterns)
- **7 New Smell Patterns** — Enhanced efficiency detection ([#67](https://github.com/littlebearapps/token-audit/issues/67))
  - `REDUNDANT_CALLS`: Same tool called with identical content hash
  - `EXPENSIVE_FAILURES`: High-token tool calls that resulted in errors (>5K tokens)
  - `UNDERUTILIZED_SERVER`: MCP server with <10% tool utilization
  - `BURST_PATTERN`: >5 tool calls within 1 second (may indicate loop)
  - `LARGE_PAYLOAD`: Single tool call >10K tokens
  - `SEQUENTIAL_READS`: Multiple consecutive file reads that could be batched
  - `CACHE_MISS_STREAK`: 5+ consecutive cache misses

#### Recommendations Engine
- **AI-Consumable Recommendations** — Generate actionable suggestions from detected smells ([#68](https://github.com/littlebearapps/token-audit/issues/68))
  - 12 recommendation types mapped from smell patterns
  - Confidence scores (0.0-1.0) based on severity and evidence
  - Evidence strings explaining why each recommendation was triggered
  - Action strings with specific suggestions
  - Impact estimates (token savings) where applicable
  - Source smell linkage for traceability
- **Recommendations in AI Export** — `token-audit export ai-prompt` includes recommendations section
  - Sorted by confidence (highest first)
  - Included in both markdown and JSON formats

#### Cross-Session Smell Aggregation
- **Smell Trend Analysis** — Track smell patterns across session history ([#69](https://github.com/littlebearapps/token-audit/issues/69))
  - `SmellAggregator` class for querying smells across sessions
  - Frequency calculation (percent of sessions affected)
  - Total occurrences and sessions affected per pattern
  - Severity breakdown per smell pattern
- **Trend Detection** — Identify improving, worsening, or stable patterns
  - Compares recent sessions vs older sessions
  - Change percentage with direction indicator
  - Configurable stability threshold (default: 10%)
- **Filtering** — Query by platform, project, or date range
  - `--days N` for last N days
  - `--platform` for specific CLI
  - `--project` for specific project

#### TUI Enhancements
- **Notification Bar** — Visual feedback for user actions ([#70](https://github.com/littlebearapps/token-audit/issues/70))
  - Shows confirmation messages ("Copied to clipboard", "Session pinned", etc.)
  - Auto-fades after configurable duration
  - Non-blocking UI feedback

#### Schema v1.7.0
- **Expanded Smell Taxonomy** — All 12 smell patterns in schema ([#71](https://github.com/littlebearapps/token-audit/issues/71))
  - `smells[].pattern`: Extended pattern enumeration
  - `smells[].details`: Pattern-specific context (e.g., content hash for REDUNDANT_CALLS)
- **Recommendations Block** — New top-level `recommendations` array (generated on export)
  - `type`, `confidence`, `evidence`, `action`, `impact`, `source_smell`

### Changed
- **Smell Engine** — Refactored to support 12 patterns (was 5)
- **AI Export** — Enhanced with recommendations section, per-server/per-tool breakdown
- **Test Coverage** — 929 tests total (up from 723 in v0.6.0)

### Notes
- Schema v1.7.0 is backward compatible (additive changes only)
- Recommendations are generated dynamically, not stored in session files
- New files: `recommendations.py` (engine), `smell_aggregator.py` (cross-session)

➡️ [View Milestone](https://github.com/littlebearapps/token-audit/milestone/4)

## [0.7.0] - 2025-12-13

### Added

#### TUI Session Browser (`token-audit ui`)
- **Interactive Session Browser** — New `token-audit ui` command for exploring past sessions ([#27](https://github.com/littlebearapps/token-audit/issues/27))
  - Browse sessions across all platforms with list and detail views
  - Platform filter cycling with `f` key (all → claude-code → codex-cli → gemini-cli)
  - Date range filtering and search functionality
  - Drill-down into individual sessions with full token breakdown
- **Session Pinning** — Mark important sessions for quick access ([#28](https://github.com/littlebearapps/token-audit/issues/28))
  - `p` key to pin/unpin sessions
  - Pinned sessions persist across browser restarts
  - Preferences stored in `~/.token-audit/preferences.json`
- **Accuracy Display Indicators** — Visual accuracy labels in session browser ([#29](https://github.com/littlebearapps/token-audit/issues/29))
  - Shows `[exact]`, `[estimated]`, or `[calls-only]` per session
  - Helps identify which sessions have native vs estimated token counts
- **TUI Keybindings & Navigation** — Full keyboard navigation ([#31](https://github.com/littlebearapps/token-audit/issues/31))
  - `j/k` or arrows: Navigate sessions
  - `Enter`: View session details
  - `s`: Cycle sort order (date, cost, duration, tools)
  - `r`: Refresh session list
  - `q`: Quit browser
  - `?`: Show help overlay
- **Tool Detail View** — Drill-down into individual tool usage ([#58](https://github.com/littlebearapps/token-audit/issues/58))
  - View per-tool token consumption and call counts
  - Identify which tools consume most tokens

#### Live TUI Enhancements
- **Smells Panel** — Real-time efficiency issue detection in live TUI ([#30](https://github.com/littlebearapps/token-audit/issues/30))
  - Shows detected smells (HIGH_VARIANCE, TOP_CONSUMER, etc.) as they occur
  - Updates dynamically during session tracking
- **Static Cost & Zombie Tools in Header** — Schema overhead visibility ([#60](https://github.com/littlebearapps/token-audit/issues/60))
  - Header shows static cost when available
  - Zombie tool count displayed for quick awareness
- **Reasoning Tokens Display** — Thinking token tracking in TUI ([#63](https://github.com/littlebearapps/token-audit/issues/63))
  - Shows reasoning tokens for Gemini CLI and Codex CLI (o-series models)
  - Auto-hides for Claude Code (no thinking tokens exposed)
- **Session ID & Files Monitored** — Enhanced header information ([#64](https://github.com/littlebearapps/token-audit/issues/64))
  - Shows current session ID in header
  - Displays count of files being monitored
- **Rate Metrics** — Real-time tokens/min and calls/min ([#65](https://github.com/littlebearapps/token-audit/issues/65))
  - Automatically calculates based on session duration
  - Formats large rates (K/min, M/min) for readability
- **Cache Hit Ratio** — Token-based cache utilization metric ([#66](https://github.com/littlebearapps/token-audit/issues/66))
  - Shows percentage of input coming from cache
  - Distinct from cost-based efficiency (which factors in pricing)
- **Unique Tools Count** — MCP Servers panel shows tool diversity ([#66](https://github.com/littlebearapps/token-audit/issues/66))
  - Format: `MCP Servers (4 servers, 12 tools, 47 calls)`
  - Helps identify over-reliance on specific tools

#### Other
- **AI Export Enhancements** — Rate metrics and cache hit ratio included in exports
  - Both `token-audit export ai-prompt` and live TUI export updated
  - Provides richer context for AI analysis
- **Cross-platform Keyboard Input** — New `keyboard.py` module for consistent key handling
  - Works across macOS, Linux, and Windows terminals
  - Handles special keys (arrows, enter, escape, etc.)
- **Preferences System** — User preference persistence
  - New `preferences.py` module for storing user settings
  - Currently used for session pinning, extensible for future preferences

### Changed
- **Token Usage panel** — Increased from 8 to 9 rows to accommodate rate metrics
- **MCP Servers panel title** — Now includes server count, unique tools, and total calls
- **Project name detection** — Shows full worktree path (e.g., `project-name/main` instead of just `main`)

### Fixed
- **`models_used` empty for single-model sessions** — Now populated with session model even without MCP calls ([#55](https://github.com/littlebearapps/token-audit/issues/55))

### Notes
- Schema version remains v1.6.0 (no data structure changes)
- Backward compatible: All changes are display-only enhancements
- New files: `display/session_browser.py` (1259 lines), `display/keyboard.py`, `preferences.py`

➡️ [View Milestone](https://github.com/littlebearapps/token-audit/milestone/3)

## [0.6.0] - 2025-12-12

### Added
- **Multi-Model Per-Session Tracking** — Track token usage when sessions switch between models ([#23](https://github.com/littlebearapps/token-audit/issues/23))
  - `models_used`: Array of unique model identifiers used during session
  - `model_usage`: Per-model breakdown with tokens, cost, and call counts
  - `Call.model`: Track which model handled each tool call
  - TUI displays multi-model breakdown when multiple models detected
- **Dynamic Pricing via LiteLLM** — Auto-fetch current model pricing from LiteLLM API ([#24](https://github.com/littlebearapps/token-audit/issues/24))
  - 2,000+ models supported via [LiteLLM pricing database](https://github.com/BerriAI/litellm)
  - 24-hour local cache with automatic refresh
  - Graceful fallback chain: API → TOML config → built-in defaults
  - `pricing_source` field in `data_quality` block (api/toml/default)
  - Configure via `token-audit.toml`: enable/disable API, set cache TTL, offline mode
- **Static Cost Foundation** — Infrastructure for MCP schema overhead tracking ([#25](https://github.com/littlebearapps/token-audit/issues/25))
  - `StaticCost` dataclass for per-server schema weight
  - Schema documented in data-contract.md
  - Full implementation requires MCP protocol work (deferred to future release)
- **Schema v1.6.0** — Multi-model intelligence fields ([#26](https://github.com/littlebearapps/token-audit/issues/26))
  - `session.models_used`: List of models used
  - `session.model_usage`: Per-model statistics
  - `tool_calls[].model`: Model per call
  - `data_quality.pricing_source`: Where pricing came from
  - `data_quality.pricing_freshness`: Age of pricing data

### Changed
- **Pricing configuration** — New API-first approach with TOML fallback
  - Default behavior: Fetch from LiteLLM API, cache 24h, fall back to TOML
  - Offline mode: Set `[pricing.api] enabled = false` for TOML-only
- **Test coverage** — 56 new tests for v0.6.0 features (723 total)

### Notes
- **Ollama CLI support** deferred to v1.1.0 post-1.0 (requires API proxy approach)
- Backward compatible: All schema changes are additive

➡️ [View Milestone](https://github.com/littlebearapps/token-audit/milestone/2)

## [0.5.0] - 2025-12-11

### Added
- **Smell Detection Engine** — Automatically detect 5 efficiency anti-patterns ([#16](https://github.com/littlebearapps/token-audit/issues/16))
  - `HIGH_VARIANCE`: Token counts vary wildly (CV > 50%)
  - `TOP_CONSUMER`: Single tool dominates (>50% of tokens)
  - `HIGH_MCP_SHARE`: Heavy MCP reliance (>80% of tokens)
  - `CHATTY`: Too many calls (>20 calls per tool)
  - `LOW_CACHE_HIT`: Cache underutilized (<30% ratio)
- **Zombie Tool Detection** — Identify MCP tools defined but never called ([#17](https://github.com/littlebearapps/token-audit/issues/17))
  - Configure known tools in `token-audit.toml`
  - Session logs report unused tools per server
- **Data Quality System** — Accuracy labels for all metrics ([#18](https://github.com/littlebearapps/token-audit/issues/18))
  - `exact`: Native platform tokens (Claude Code)
  - `estimated`: Tokenizer-based estimation (Codex CLI, Gemini CLI)
  - `calls-only`: Only call counts, no tokens (Ollama CLI in v1.1.0)
  - Confidence scores and estimation method metadata
- **AI Prompt Export** — Export session data for AI analysis ([#19](https://github.com/littlebearapps/token-audit/issues/19))
  - `token-audit export ai-prompt` command
  - Markdown and JSON output formats
  - Includes suggested analysis questions
- **Schema v1.5.0** — New data blocks ([#21](https://github.com/littlebearapps/token-audit/issues/21))
  - `smells`: Detected efficiency anti-patterns with evidence
  - `zombie_tools`: Unused tools per MCP server
  - `data_quality`: Accuracy metadata (level, source, confidence)

➡️ [View Milestone](https://github.com/littlebearapps/token-audit/milestone/1)

## [0.4.3] - 2025-12-10

### Added
- **Socket.dev supply chain security scanning** (Task 111.15)
  - New `.github/workflows/socket.yml` workflow
  - Detects malicious packages, typosquatting, supply chain attacks
  - Runs on push to main and all PRs
  - Complements existing CodeQL and Dependabot scanning

### Changed
- **Enhanced first-run welcome message** - New users see a detailed welcome with:
  - Platform accuracy breakdown (Claude Code 100%, Codex CLI 99%+, Gemini CLI ~95%)
  - Dedicated Gemini CLI callout explaining optional tokenizer download
  - Clear messaging that tracking works immediately without extra setup
  - Link to documentation
- **Switched from CodeCov to py-cov-action** (Task 111.14)
  - GitHub-native coverage reporting (no external service)
  - PR comments with coverage diffs and line annotations
  - Coverage badge stored in git branch
  - No CODECOV_TOKEN needed
- **Coverage configuration improved** (Task 111.14)
  - Added `relative_files = true` to pyproject.toml for CI compatibility
  - Coverage XML now uses relative paths

## [0.4.2] - 2025-12-09

### Changed
- **README overhaul for better onboarding**
  - New "What token-audit Does (At a Glance)" section with categorized features
  - Highlighted platform Getting Started guides in Documentation section
  - Renamed FAQ sections: "MCP Problems token-audit Helps Solve" and "Usage & Support FAQ"
  - Consolidated Compatibility section (Python + Platform support)
  - Dynamic version badge in "What's New" section
- **PyPI page improvements**
  - All relative links converted to full GitHub URLs for PyPI compatibility
  - Fixed GitHub-only `[!TIP]` alert syntax for cross-platform rendering
  - Converted HTML table to Markdown for consistent rendering
  - Added `Source` and `Discussions` project URLs

### Fixed
- **PyPI URL verification** - Publish workflow now runs from public repo
  - OIDC token originates from `littlebearapps/token-audit` (public)
  - All GitHub URLs now eligible for PyPI "Verified" status
  - New `publish-pypi.yml` workflow for Trusted Publishing

## [0.4.1] - 2025-12-08

### Fixed
- **Demo GIF display on PyPI** - Use absolute URL for cross-platform compatibility

## [0.4.0] - 2025-12-08

### Added
- **MCP tool token estimation for Codex CLI and Gemini CLI** (Task 69)
  - `TokenEstimator` class with platform-specific tokenizers
  - Codex CLI: tiktoken o200k_base (~99-100% accuracy)
  - Gemini CLI: SentencePiece/Gemma (100%) or tiktoken fallback (~95%)
  - Per-tool estimated tokens shown in TUI and session logs
  - `FUNCTION_CALL_OVERHEAD` constant (25 tokens) for API formatting
- **Schema v1.4.0** - Per-call estimation metadata
  - `is_estimated` field indicates estimated vs native tokens
  - `estimation_method` field (tiktoken/sentencepiece/character)
  - `estimation_encoding` field (o200k_base/gemma/cl100k_base)
- **Theme system with Catppuccin support** (Task 83)
  - Catppuccin Mocha (dark) and Latte (light) color palettes
  - High-contrast themes (hc-dark, hc-light) meeting WCAG AAA
  - Auto-detection of terminal background color
  - `--theme` CLI option: auto, dark, light, hc-dark, hc-light
  - `TOKEN_AUDIT_THEME` environment variable
- **ASCII mode** for terminals without unicode support
  - `--ascii` flag or `TOKEN_AUDIT_ASCII=1` environment variable
  - Box-drawing with ASCII characters, no emoji
- **NO_COLOR standard compliance** - [no-color.org](https://no-color.org/)
  - Set `NO_COLOR=1` to disable all color output
- **GitHub Release download for Gemma tokenizer** (Task 96)
  - `token-audit tokenizer download` fetches from GitHub Releases (no signup)
  - `--source` flag (github/huggingface)
  - `--release` flag to download specific version
  - SHA256 checksum verification
  - Version tracking via `tokenizer.meta.json`
- **"Noisy fallback" pattern** - Users informed when using approximate accuracy
  - One-time hint during Gemini CLI collection about tokenizer download
  - `token-audit tokenizer status` shows accuracy implications
- **Manual installation guide** - `docs/manual-tokenizer-install.md` for corporate networks

### Changed
- **Package size reduced from ~5MB to <500KB** - Gemma tokenizer now optional download
  - Pip package no longer bundles the 4MB tokenizer
  - Tokenizer available via `token-audit tokenizer download`
  - Gemini CLI works immediately with ~95% accuracy (tiktoken fallback)
- **TUI enhancements**
  - Token panel title shows estimation method when applicable
  - Final summary shows estimation stats (e.g., "5 calls with tiktoken estimation")
  - Theme-aware colors throughout
- **Improved `token-audit tokenizer status` output** - Clearer terminology
  - Shows "Downloaded (persistent)" instead of "cached"
  - Displays version and download timestamp

### Security
- **Path traversal protection** for tarball extraction (`_validate_tarball_member()`)
- **SHA256 checksum verification** for downloaded tokenizer integrity

### Notes
- **Gemini CLI users**: Run `token-audit tokenizer download` for 100% token accuracy
- **Claude Code users**: No action needed - has native per-tool token attribution
- **Codex CLI users**: No action needed - uses tiktoken (~99-100% accuracy)
- Corporate network users: See `docs/manual-tokenizer-install.md`

## [0.3.14] - 2025-12-06

### Added
- **Schema v1.3.0: Reasoning tokens** - Track thinking/reasoning tokens separately from output
  - `reasoning_tokens` field in `token_usage` block
  - Codex CLI: maps to `reasoning_output_tokens` (o-series models)
  - Gemini CLI: maps to `thoughts` (Gemini 2.0+ responses)
  - Claude Code: always 0 (no thinking tokens exposed)
  - TUI displays "Reasoning" row only when > 0 (auto-hides for Claude Code)
- **Schema v1.2.0: Built-in tool tracking** - Persist built-in tool stats to session files
  - `builtin_tool_summary` block with per-tool calls and tokens
  - Claude Code: Full token attribution per built-in tool
  - Codex CLI / Gemini CLI: Call counts only (no per-tool tokens)
- **BUILTIN_TOOLS documentation** - Official tool names from upstream sources
  - `CLAUDE_CODE_BUILTIN_TOOLS` (18 tools) from anthropics/claude-code
  - `CODEX_BUILTIN_TOOLS` (11 tools) from openai/codex
  - `GEMINI_BUILTIN_TOOLS` (12 tools) from google-gemini/gemini-cli
- **Automated test harness** - Cross-platform testing scripts
  - `scripts/test-harness.sh` - Automated testing with `--platform` and `--quick` flags
  - `scripts/compare-results.sh` - Test result analysis and regression detection
  - `quickref/automated-testing-plan.md` - Complete test strategy documentation
  - `quickref/local-testing-guide.md` - Manual testing procedures
- **Comprehensive platform validation** - Tasks 75-77 completed
  - Claude Code, Codex CLI, and Gemini CLI thoroughly validated
  - Evidence directories with TUI captures and session analysis

### Changed
- **Data contract** - Updated to schema v1.3.0 with full backward compatibility
  - Added `reasoning_tokens` field documentation
  - Added `builtin_tool_summary` block documentation (v1.2.0)
  - Updated platform-specific behavior tables
- **Platform documentation** - Updated PLATFORM-TOKEN-CAPABILITIES.md
  - Documented reasoning token support per platform
  - Documented built-in tool tracking differences

### Fixed
- **Codex CLI token double-counting** (Task 79) - Critical bug fix
  - Root cause: Codex CLI native logs contain duplicate `token_count` events
  - Old behavior: Summing `last_token_usage` (delta) caused double-counting
  - New behavior: Use cumulative `total_token_usage` and REPLACE session totals
  - Accurate token tracking regardless of duplicate events in logs

## [0.3.13] - 2025-12-03

### Added
- **Gemini CLI adapter rewrite** - Complete rewrite to parse native JSON session files
  - No OTEL/telemetry setup required - reads `~/.gemini/tmp/<hash>/chats/session-*.json` directly
  - Project hash auto-detection from working directory (SHA256)
  - Per-message token tracking: input, output, cached, thoughts, tool, total
  - Thinking tokens tracked separately (`thoughts_tokens` field)
  - Tool call detection via `toolCalls` array with `mcp__` prefix filtering
  - Model detection from session data
- **Codex CLI adapter enhancements** - File-based session reading without subprocess wrapping
  - Session auto-discovery with `--latest` flag
  - Date range filtering with `--since` and `--until` options
  - File watcher for live session monitoring
- **Platform-aware reports** - New `--platform` filter for `token-audit report`
  - Multi-platform aggregation in reports
  - Platform breakdown in summary statistics
- **Unified cost comparison** - Cross-platform cost efficiency analysis
  - Cost per 1M tokens by platform
  - Cost per session by platform
  - "Most efficient platform" indicator
- **Setup guides** - Comprehensive documentation for each platform
  - `docs/codex-cli-setup.md` - Codex CLI installation and usage
  - `docs/gemini-cli-setup.md` - Gemini CLI installation and usage
- **Gemini model pricing** - Added Gemini 2.0, 2.5, and 3.0 series to `token-audit.toml`
- **Codex model pricing** - Added GPT-5 series and Codex-specific models

### Changed
- **Gemini CLI** - Removed OTEL telemetry dependency entirely
- **Documentation** - Updated architecture.md, ROADMAP.md, platform docs for new adapters
- **Examples** - Updated gemini-cli-session example with new JSON format

### Fixed
- **Gemini CLI tracking** - Now works out-of-the-box without any telemetry configuration

## [0.3.12] - 2025-12-02

### Fixed
- **Public sync workflow** - Fixed sync to include hidden files (.github/)
- **GitHub topics** - Synced 14 repository topics to public repo

## [0.3.11] - 2025-12-02

### Added
- **Collapsible table of contents** - README now has expandable TOC for easier navigation
- **GIF caption** - Demo GIF has descriptive caption like competitor ccusage
- **Lightweight badge** - Added <500KB install size feature highlight

### Changed
- **README overhaul** - Complete restructuring with competitor comparison, better messaging, and improved layout
  - Side-by-side audience cards for MCP developers and power users
  - Collapsible FAQ section with accordions
  - Enhanced "Why token-audit?" section with ccusage distinction
  - SEO improvements for discoverability
- **Repository hygiene** - Internal development files now gitignored (CLAUDE.md, quickref/, backlog/, etc.)

## [0.3.10] - 2025-12-01

### Added
- **Version display** - TUI header now shows token-audit version and session logs include `token_audit_version` field
- **Comprehensive adapter tests** - Added `test_codex_cli_adapter.py` with 28 tests for Codex CLI format

### Fixed
- **Codex CLI adapter** - Rewrote `parse_event()` to handle actual JSONL format correctly (#24)
  - `turn_context` events for model detection
  - `event_msg` with `token_count` for usage tracking
  - `response_item` with `function_call` for MCP tool calls
- **FAQ section** - Added common questions to README

## [0.3.9] - 2025-11-30

### Fixed
- **Claude Code tracking** - Fixed critical bug where new session files created during monitoring were missed
  - Root cause: `_find_jsonl_files()` filtered out empty files (`st_size > 0`)
  - When Claude Code creates a new session file (initially empty), token-audit excluded it
  - Once Claude Code wrote content, token-audit found the file but set position to END, missing all events
  - Fix: Include all .jsonl files, check file creation time for new files discovered during monitoring
  - If file created after tracking started, read from beginning (position 0)
  - If file created before, read only new content (position at END)

## [0.3.8] - 2025-11-30

### Fixed
- **Session token tracking** - Track session tokens for all assistant messages, not just MCP calls (#21)

## [0.3.7] - 2025-11-30

### Changed
- **Single source version** - Version now defined only in `pyproject.toml`, read dynamically via `importlib.metadata`
- **Email update** - Changed contact email from contact@ to help@littlebearapps.com
- **Release docs** - Added Releasing section to CLAUDE.md with version flow and checklist

### Fixed
- **Version mismatch** - CLI `--version` now always matches PyPI package version (was showing 0.3.4 when package was 0.3.5)

## [0.3.6] - 2025-11-30

### Fixed
- **Version sync** - Synced `__version__` in `__init__.py` with `pyproject.toml` (both now 0.3.6)

## [0.3.5] - 2025-11-30

### Added
- **Auto GitHub Releases** - Version bumps now auto-create GitHub Releases with generated notes
- **Dependencies badge** - Added libraries.io badge to README

### Changed
- **Model pricing** - Updated token-audit.toml with all current models (Claude, OpenAI, Gemini) with USD labels
- **TUI display** - Cost now shows "Cost (USD):" for clarity

### Removed
- **Legacy files** - Removed COMMANDS.md, model-pricing.json, usage-wp-nav.sh, live-session-tracker.sh
- **TestPyPI** - Removed unused TestPyPI job from publish workflow

## [0.3.4] - 2025-11-29

### Changed
- **Codebase cleanup** - Removed 12 legacy Python scripts from root directory (now in src/token_audit/)
- **Documentation updates** - Updated all docs to use `token-audit` CLI instead of npm scripts
- **PyPI keywords** - Updated keywords for better discoverability (context-window, token-tracking, llm-cost)

### Fixed
- **Type annotations** - Fixed all mypy strict mode errors in session_manager.py, cli.py, and storage.py
- **Project name detection** - Now correctly detects git worktree setups (project-name/main → project-name)
- **Troubleshooting docs** - Complete rewrite to use `token-audit` CLI commands

## [0.3.2] - 2025-11-25

### Added
- **CodeQL workflow** - Explicit `codeql.yml` for badge compatibility and consistent security scanning
- **Auto-tag workflow** - Automatic git tagging on version bumps for seamless PyPI publishing
- **Release documentation** - Added Releasing section to CONTRIBUTING.md

## [0.3.1] - 2025-11-25

### Added
- **GitHub topics** - 10 topics for discoverability (mcp, claude-code, codex-cli, etc.)
- **CONTRIBUTING.md** - Root-level contributing guide (GitHub standard location)
- **Makefile** - Build targets for gpm verify (lint, typecheck, test, build)

### Changed
- **README badges** - Updated to shields.io format with PyPI version/downloads
- **Installation docs** - Added pipx as installation option
- **CLAUDE.md** - Added explicit PR merge approval requirement

### Fixed
- **CI workflow** - Hardened publish.yml to require CI pass before PyPI publish
- **gpm integration** - Fixed mypy verification to only check src/ directory

## [0.3.0] - 2025-11-25

### Added
- **PyPI distribution** - Now installable via `pip install token-audit` or `pipx install token-audit`
- **Rich TUI display** - Beautiful terminal dashboard with live updating panels
  - Auto TTY detection (TUI for terminals, plain text for CI)
  - Display modes: `--tui`, `--plain`, `--quiet`
  - Configurable refresh rate with `--refresh-rate`
- **Gemini CLI adapter** - Full support for tracking Gemini CLI sessions via OpenTelemetry
- **Display adapter pattern** - Modular display system (RichDisplay, PlainDisplay, NullDisplay)
- **CLI command** - `token-audit` command with `collect` and `report` subcommands
- **Proper package structure** - Modern `src/` layout following Python packaging best practices
- **Type hints** - Full type annotations with `py.typed` marker for editor support
- **GitHub Actions** - Automated CI/CD pipeline with PyPI publishing on releases
- **JSONL storage system** - Efficient session storage with indexing for fast queries
- **Platform adapters** - Modular architecture for adding new platform support

### Changed
- Restructured project from flat files to `src/token_audit/` package
- Updated from Phase 1 (Foundation) to Phase 2 (Public Beta)
- Improved test organization with dedicated `tests/` directory
- Enhanced pyproject.toml with modern Python packaging standards

### Fixed
- License deprecation warnings in setuptools
- Test imports for new package structure

## [0.2.0] - 2025-11-24

### Added
- **BaseTracker abstraction** - Platform-agnostic tracker base class
- **Schema v1.0.0** - Locked data schema with backward compatibility guarantees
- **Pricing configuration** - TOML-based model pricing with Claude and OpenAI support
- **CI/CD pipeline** - GitHub Actions with pytest, mypy, ruff, and black
- **JSONL storage** - Session persistence with 57 comprehensive tests
- **Complete documentation** - Architecture docs, data contract, contributing guide

### Changed
- Migrated from single-file scripts to modular architecture
- Added strict mypy type checking
- Standardized code formatting with black

## [0.1.0] - 2025-11-18

### Added
- Initial implementation
- Claude Code session tracking
- Codex CLI session tracking
- Real-time token usage display
- Cross-session analysis
- Duplicate detection
- Anomaly detection

---

[1.0.0]: https://github.com/littlebearapps/token-audit/compare/v0.9.1...v1.0.0
[0.9.1]: https://github.com/littlebearapps/token-audit/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/littlebearapps/token-audit/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/littlebearapps/token-audit/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/littlebearapps/token-audit/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/littlebearapps/token-audit/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/littlebearapps/token-audit/compare/v0.4.3...v0.5.0
