# Example: Comparing Platform Costs

Compare token usage and costs across Claude Code, Codex CLI, and Gemini CLI for the same task.

---

## The Problem

You use multiple AI coding platforms and want to understand:
- Which platform is most cost-effective for your workflow
- How token usage differs between platforms
- Whether caching efficiency varies by platform

**Goal:** Make data-driven decisions about which platform to use for different tasks.

---

## Prerequisites

- MCP Audit installed
- At least two AI platforms installed (Claude Code, Codex CLI, or Gemini CLI)
- A repeatable task you can perform on multiple platforms

---

## Step-by-Step Solution

### Step 1: Choose a Repeatable Task

Select a task you can perform identically on each platform:
- "Implement a function to validate email addresses"
- "Refactor this file to use async/await"
- "Write unit tests for the UserService class"

### Step 2: Track Claude Code Session

```bash
# Terminal 1: Start tracking
mcp-audit collect --platform claude-code
```

In Claude Code, perform your task. When done, press `Ctrl+C` and note the metrics:

```
Session Summary (Claude Code)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Input:      45,231    Output:     8,543
Cached:     32,000    Total:     85,774
Cost: $0.12
```

### Step 3: Track Codex CLI Session

```bash
# Terminal 1: Start tracking
mcp-audit collect --platform codex-cli
```

In Codex CLI, perform the same task. Press `Ctrl+C` when done:

```
Session Summary (Codex CLI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Input:      52,100    Output:     9,200
Cached:     45,000    Total:    106,300
Cost: $0.08
```

### Step 4: Track Gemini CLI Session

```bash
# Terminal 1: Start tracking
mcp-audit collect --platform gemini-cli
```

Perform the same task in Gemini CLI:

```
Session Summary (Gemini CLI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Input:      38,500    Output:     7,800
Cached:     28,000    Total:     74,300
Cost: $0.05
```

### Step 5: Generate Comparison Report

Generate reports for all sessions:

```bash
# List recent sessions
mcp-audit report --list

# Generate individual reports
mcp-audit report <claude-session-id>
mcp-audit report <codex-session-id>
mcp-audit report <gemini-session-id>
```

### Step 6: Analyze the Data

Create a comparison table:

| Metric | Claude Code | Codex CLI | Gemini CLI |
|--------|-------------|-----------|------------|
| Input tokens | 45,231 | 52,100 | 38,500 |
| Output tokens | 8,543 | 9,200 | 7,800 |
| Cache tokens | 32,000 | 45,000 | 28,000 |
| Cache ratio | 71% | 86% | 73% |
| Total cost | $0.12 | $0.08 | $0.05 |
| MCP calls | 12 | 8 | 15 |

### Step 7: Consider Task-Specific Factors

Different platforms may excel at different tasks:

**Claude Code**:
- Best for: Complex reasoning, nuanced code review
- Higher accuracy on edge cases
- Full cache visibility (create + read)

**Codex CLI**:
- Best for: Rapid iteration, shell-heavy workflows
- Better cache efficiency for repeated patterns
- Tool duration tracking available

**Gemini CLI**:
- Best for: Cost-sensitive tasks, large codebases
- Lower per-token pricing
- Reasoning tokens visible (Gemini 2.0+)

---

## Expected Output

After comparing multiple sessions:

```markdown
## Platform Comparison: Email Validation Feature

### Cost Analysis
| Platform | Total Cost | Cost/Token |
|----------|------------|------------|
| Claude Code | $0.12 | $0.0000014 |
| Codex CLI | $0.08 | $0.0000008 |
| Gemini CLI | $0.05 | $0.0000007 |

### Efficiency Analysis
| Platform | Cache Ratio | MCP Calls | Tokens/Call |
|----------|-------------|-----------|-------------|
| Claude Code | 71% | 12 | 7,148 |
| Codex CLI | 86% | 8 | 13,288 |
| Gemini CLI | 73% | 15 | 4,953 |

### Recommendation
For this task type, **Gemini CLI** offers the best cost efficiency
while maintaining acceptable quality.
```

---

## Key Takeaways

1. **Same task, different costs** — Platform choice significantly impacts cost
2. **Cache efficiency varies** — Some platforms cache more aggressively
3. **MCP call patterns differ** — Platforms use tools differently for same goals
4. **Match platform to task** — Use data to choose the right tool for each job
5. **Track over time** — Single comparisons may not reflect typical usage

---

## Advanced: Multi-Session Aggregation

For more robust comparisons, track multiple sessions per platform:

```bash
# Aggregate Claude Code sessions
mcp-audit report ~/.mcp-audit/sessions/ --platform claude-code --aggregate

# Aggregate Codex CLI sessions
mcp-audit report ~/.mcp-audit/sessions/ --platform codex-cli --aggregate

# Aggregate Gemini CLI sessions
mcp-audit report ~/.mcp-audit/sessions/ --platform gemini-cli --aggregate
```

This provides statistically meaningful comparisons across typical usage patterns.

---

## Related Examples

- [Debugging a Slow Session](debugging-slow-session.md) — Optimize individual sessions
- [Team-Wide Tracking](team-wide-tracking.md) — Aggregate across projects

---

*See [Platform Guides](../platforms/) for platform-specific details.*
