# Example: Optimizing MCP Server Configuration

Remove underutilized MCP servers to reduce context overhead.

---

## The Problem

Your `.mcp.json` has 5+ MCP servers configured, but you suspect:
- Some servers are rarely used
- Server schemas are consuming context before any work begins
- You're paying a "context tax" for servers you don't need

**Goal:** Identify which servers to keep and which to remove.

---

## Prerequisites

- MCP Audit installed
- Multiple MCP servers configured
- A few tracked sessions (for accurate analysis)

---

## Step-by-Step Solution

### Step 1: Track a Typical Session

Start MCP Audit and work normally for 15-30 minutes:

```bash
mcp-audit collect --platform claude-code
```

### Step 2: Review the Context Tax Panel

During tracking, look at the Context Tax panel:

```
Context Tax
─────────────────────────────────────
Total: 8,750 tokens (static overhead)

Per Server:
  zen ............. 3,000 tokens
  brave-search .... 1,200 tokens
  jina ............ 3,600 tokens
  context7 ........ 750 tokens
  unused-server ... 200 tokens

Zombie Tax: +450 tokens (unused tools)
```

This shows 8,750 tokens consumed before any work begins.

### Step 3: Check Server Utilization

Look at the MCP Servers panel:

```
MCP Servers (5 servers, 45 tools, 28 calls)
──────────────────────────────────────
  zen ............. 20 calls
  brave-search .... 8 calls
  jina ............ 0 calls    ← Never used
  context7 ........ 0 calls    ← Never used
  unused-server ... 0 calls    ← Never used
```

Three servers have zero calls this session.

### Step 4: Configure Zombie Tool Detection

Create or edit `~/.mcp-audit/mcp-audit.toml`:

```toml
[zombie_tools.zen]
tools = [
    "mcp__zen__thinkdeep",
    "mcp__zen__chat",
    "mcp__zen__debug",
    "mcp__zen__refactor",
    "mcp__zen__precommit"
]

[zombie_tools.brave-search]
tools = [
    "mcp__brave-search__brave_web_search",
    "mcp__brave-search__brave_local_search"
]
```

### Step 5: Track Another Session

With zombie detection configured:

```bash
mcp-audit collect --platform claude-code
```

Now you'll see zombie tools reported:

```json
{
  "zombie_tools": {
    "zen": ["mcp__zen__refactor", "mcp__zen__precommit"],
    "jina": ["all 20 tools"]
  }
}
```

### Step 6: Analyze Across Sessions

Generate an aggregate report:

```bash
mcp-audit report ~/.mcp-audit/sessions/ --aggregate
```

Look for patterns:
- Servers with <10% utilization across sessions
- Tools never called across multiple sessions

### Step 7: Remove Underutilized Servers

Edit your MCP configuration (`.mcp.json` or equivalent):

**Before:**
```json
{
  "mcpServers": {
    "zen": { "command": "..." },
    "brave-search": { "command": "..." },
    "jina": { "command": "..." },
    "context7": { "command": "..." },
    "unused-server": { "command": "..." }
  }
}
```

**After:**
```json
{
  "mcpServers": {
    "zen": { "command": "..." },
    "brave-search": { "command": "..." }
  }
}
```

### Step 8: Verify Improvement

Track a new session and compare:

**Before:** 8,750 tokens context tax
**After:** 4,200 tokens context tax
**Savings:** 4,550 tokens (52% reduction)

---

## Expected Output

After removing underutilized servers:
- Lower initial context overhead
- Faster session starts
- More context available for actual work
- Later auto-compaction

---

## Key Takeaways

1. **Context tax is real** — Server schemas consume tokens just by existing
2. **Zombie tools add overhead** — Tools you never call still cost tokens
3. **Less is more** — Keep only servers you actively use
4. **Track before removing** — Use data to make decisions, not guesses

---

## Zombie Tool Configuration Template

Add this to `~/.mcp-audit/mcp-audit.toml` for common servers:

```toml
[zombie_tools.zen]
tools = [
    "mcp__zen__thinkdeep",
    "mcp__zen__chat",
    "mcp__zen__debug",
    "mcp__zen__refactor",
    "mcp__zen__precommit",
    "mcp__zen__codereview",
    "mcp__zen__planner"
]

[zombie_tools.brave-search]
tools = [
    "mcp__brave-search__brave_web_search",
    "mcp__brave-search__brave_local_search",
    "mcp__brave-search__brave_news_search",
    "mcp__brave-search__brave_image_search"
]

[zombie_tools.jina]
tools = [
    "mcp__jina__read_url",
    "mcp__jina__search_web",
    "mcp__jina__search_arxiv"
]
```

---

## Related Examples

- [Debugging a Slow Session](debugging-slow-session.md) — Find expensive individual tools
- [AI-Assisted Review](ai-assisted-review.md) — Get AI recommendations for optimization

---

*See [Feature Reference](../FEATURES.md#context-tax-tracking) for details on context tax.*
