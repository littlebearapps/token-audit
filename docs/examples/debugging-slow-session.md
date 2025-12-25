# Example: Debugging a Slow Claude Code Session

Find which MCP tools are consuming excessive tokens and causing early auto-compaction.

---

## The Problem

Your Claude Code session is running slowly:
- Responses take longer than usual
- Auto-compaction happens frequently
- You suspect an MCP tool is consuming too many tokens

**Goal:** Identify the expensive tool(s) and understand the token consumption pattern.

---

## Prerequisites

- Token Audit installed
- Active Claude Code session exhibiting slow behavior
- MCP servers configured in Claude Code

---

## Step-by-Step Solution

### Step 1: Start Token Audit

Open a new terminal in your project directory:

```bash
cd /path/to/your/project
token-audit collect --platform claude-code
```

### Step 2: Reproduce the Slow Behavior

In your Claude Code session, work as you normally would. Pay attention to the TUI dashboard in the Token Audit terminal.

Watch for:
- **Token panel**: Is input growing rapidly?
- **MCP panel**: Which server/tool has the most tokens?
- **Rate metrics**: Is tokens/min unusually high?

### Step 3: Analyze the TUI

After 5-10 minutes of work, examine the TUI:

```
Token Usage
──────────────────────────────────────
Input:      456,789    Output:     12,345
Cached:     125,000    Total:     594,134
Token Rate:  45.2K/min  Call Rate:  8.5/min
```

**Red flags:**
- Token rate >50K/min → Rapid context growth
- Input >>10x output → Heavy context, light responses
- Single tool >50% of tokens → Concentrated overhead

### Step 4: Identify the Culprit

Look at the MCP Servers panel:

```
MCP Servers (3 servers, 8 tools, 42 calls)
──────────────────────────────────────
  zen ............. 28 calls, 450K tokens (75%)
    thinkdeep ..... 8 calls, 400K tokens
    chat .......... 20 calls, 50K tokens
  brave-search .... 14 calls, 50K tokens (8%)
```

In this example, `mcp__zen__thinkdeep` is consuming 67% of all tokens with just 8 calls.

### Step 5: Generate a Report

Stop tracking (`Ctrl+C`) and generate a detailed report:

```bash
token-audit report --top-n 10
```

Output:

```markdown
## Top 10 Tools by Token Usage

| Tool | Calls | Tokens | Avg/Call | % Total |
|------|-------|--------|----------|---------|
| mcp__zen__thinkdeep | 8 | 400,000 | 50,000 | 67.3% |
| mcp__zen__chat | 20 | 50,000 | 2,500 | 8.4% |
| mcp__brave-search__web | 14 | 50,000 | 3,571 | 8.4% |
```

### Step 6: Take Action

Based on findings, choose a strategy:

**If single tool dominates (like thinkdeep):**
- Use it sparingly for complex analysis only
- Prefer lighter alternatives (`chat`) for simple questions
- Consider batching related questions

**If many chatty calls:**
- Look for patterns that could be batched
- Check for redundant tool calls

**If large file operations:**
- Use targeted reads (specific lines/functions)
- Avoid reading entire large files

---

## Expected Output

After implementing changes, your next session should show:
- Lower tokens/min rate
- More balanced tool distribution
- Longer time before auto-compaction

---

## Key Takeaways

1. **Token rate is the leading indicator** — High tokens/min predicts auto-compaction
2. **Look for the "fat" tool** — Often one tool dominates token usage
3. **Average tokens per call matters** — 50K/call is expensive; 500/call is reasonable
4. **Use reports for patterns** — TUI for real-time, reports for analysis

---

## Related Examples

- [Optimizing MCP Config](optimizing-mcp-config.md) — Remove servers causing overhead
- [AI-Assisted Review](ai-assisted-review.md) — Get AI analysis of your patterns

---

*See [Feature Reference](../features.md) for details on smell detection and recommendations.*
