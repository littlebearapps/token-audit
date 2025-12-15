# Example: AI-Assisted Review

Use MCP Audit's AI export feature to get intelligent analysis of your sessions.

---

## The Problem

You have MCP Audit data but want:
- Deeper insights than the built-in reports provide
- Natural language recommendations
- Pattern analysis across multiple sessions
- Custom analysis tailored to your workflow

**Goal:** Export session data in a format optimized for AI analysis.

---

## Prerequisites

- MCP Audit installed with tracked sessions
- Access to an AI assistant (Claude, GPT, Gemini, etc.)
- Understanding of your typical workflow patterns

---

## Step-by-Step Solution

### Step 1: Track a Session

Track a typical work session:

```bash
mcp-audit collect --platform claude-code
```

Work normally for 15-30 minutes, then stop tracking (`Ctrl+C`).

### Step 2: Export for AI Analysis

Use the AI export format:

```bash
mcp-audit export ai-prompt
```

This generates a structured prompt optimized for AI analysis:

```markdown
# MCP Audit Session Analysis Request

## Session Overview
- Platform: Claude Code
- Duration: 28 minutes
- Model: claude-sonnet-4-20250514
- Total tokens: 234,567

## Token Breakdown
| Category | Tokens | Cost |
|----------|--------|------|
| Input | 189,432 | $0.57 |
| Output | 45,135 | $0.68 |
| Cached | 156,000 | $0.05 |

## MCP Tool Usage
| Server | Tool | Calls | Tokens |
|--------|------|-------|--------|
| zen | thinkdeep | 8 | 125,000 |
| zen | chat | 15 | 45,000 |
| brave-search | brave_web_search | 6 | 12,000 |
| jina | read_url | 3 | 8,000 |

## Smells Detected
1. EXPENSIVE_CALLS (severity: high)
   - Tool: mcp__zen__thinkdeep
   - Avg tokens/call: 15,625

2. LOW_CACHE_RATIO (severity: medium)
   - Cache hit ratio: 45%
   - Expected: >70%

## Analysis Request
Please analyze this session and provide:
1. Cost optimization recommendations
2. Tool usage pattern insights
3. Suggested workflow improvements
4. Comparison to typical efficient sessions
```

### Step 3: Submit to AI Assistant

Copy the export and paste into your preferred AI assistant:

**Claude:**
```
Here's my MCP Audit session data. Please analyze it and suggest improvements:

[paste export]
```

**ChatGPT:**
```
Analyze this AI coding session data and identify inefficiencies:

[paste export]
```

### Step 4: Review AI Recommendations

Example AI response:

```markdown
## Session Analysis

### Key Findings

1. **Expensive thinkdeep Usage**
   Your 8 thinkdeep calls consumed 53% of total tokens. Each call
   averaged 15,625 tokens, which is high.

   **Recommendation:** Reserve thinkdeep for truly complex reasoning.
   For simpler questions, use the chat tool instead (avg 3,000 tokens).

2. **Low Cache Efficiency**
   Your 45% cache ratio is below the 70% target. This means you're
   re-processing context that could be cached.

   **Recommendation:**
   - Group related queries together
   - Avoid context-switching between unrelated tasks
   - Consider larger, fewer requests vs. many small ones

3. **Underutilized Search**
   Only 6 web searches for 28 minutes of work. You may be asking
   the AI questions it could answer faster with current information.

   **Recommendation:** Use brave_web_search for:
   - Documentation lookups
   - API references
   - Recent changes to libraries

### Projected Savings
Implementing these changes could reduce costs by 30-40%:
- Current session: $1.30
- Optimized estimate: $0.78-0.91
```

### Step 5: Apply Recommendations

Based on AI feedback, adjust your workflow:

1. **Reduce thinkdeep calls**: Use for architecture decisions only
2. **Batch related work**: Don't context-switch mid-task
3. **Search before asking**: Use web search for factual queries

### Step 6: Track and Compare

After applying changes, track another session:

```bash
mcp-audit collect --platform claude-code
# Work with new approach
# Stop tracking

mcp-audit export ai-prompt > after-optimization.md
```

Compare before/after metrics:

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Cost | $1.30 | $0.85 | -35% |
| thinkdeep calls | 8 | 3 | -63% |
| Cache ratio | 45% | 72% | +27% |

---

## Expected Output

### AI Export Format

```markdown
# MCP Audit Session Analysis Request

## Session Overview
- Platform: Claude Code
- Duration: 28 minutes
- Model: claude-sonnet-4-20250514
- Total tokens: 234,567
- Cost: $1.30

## Token Breakdown
| Category | Tokens | Percentage | Cost |
|----------|--------|------------|------|
| Input | 189,432 | 80.7% | $0.57 |
| Output | 45,135 | 19.3% | $0.68 |
| Cached | 156,000 | 66.5% | $0.05 |

## MCP Server Summary
| Server | Tools | Calls | Tokens | % of Total |
|--------|-------|-------|--------|------------|
| zen | 2 | 23 | 170,000 | 72.5% |
| brave-search | 1 | 6 | 12,000 | 5.1% |
| jina | 1 | 3 | 8,000 | 3.4% |

## Tool Detail
| Tool | Calls | Tokens | Avg/Call |
|------|-------|--------|----------|
| mcp__zen__thinkdeep | 8 | 125,000 | 15,625 |
| mcp__zen__chat | 15 | 45,000 | 3,000 |
| mcp__brave-search__brave_web_search | 6 | 12,000 | 2,000 |
| mcp__jina__read_url | 3 | 8,000 | 2,667 |

## Smells Detected
### EXPENSIVE_CALLS (high severity)
- Tool: mcp__zen__thinkdeep
- 8 calls consuming 125,000 tokens (53% of total)
- Recommendation: Consider using lighter alternatives

### LOW_CACHE_RATIO (medium severity)
- Current ratio: 45%
- Target ratio: 70%
- Recommendation: Batch related queries to improve caching

## Recommendations
1. Replace thinkdeep with chat for simple queries
2. Group related work to improve cache efficiency
3. Use web search for factual lookups

## Analysis Request
Please analyze this session data and provide:
1. Specific cost optimization strategies
2. Tool usage pattern insights
3. Workflow improvement suggestions
4. Estimated savings from recommended changes
```

---

## Key Takeaways

1. **AI export is structured** — Optimized for AI consumption
2. **Include context** — AI can provide better recommendations with full data
3. **Iterative improvement** — Track, analyze, adjust, repeat
4. **Cross-reference with smells** — AI can explain why patterns are problematic
5. **Quantify improvements** — Compare before/after metrics

---

## Advanced: Custom Analysis Prompts

Tailor your analysis request:

**Cost-focused:**
```
Focus on cost reduction. What are the top 3 changes that would
have the biggest impact on reducing my AI spending?
```

**Performance-focused:**
```
I'm experiencing slow response times. Analyze the token usage
patterns and suggest how to get faster responses.
```

**Tool-focused:**
```
I have these MCP servers configured but I'm not sure I need all
of them. Which ones are providing value and which should I remove?
```

**Comparison:**
```
Here are two sessions - one efficient, one inefficient. What are
the key differences and what can I learn from the efficient one?

[Session 1 export]
[Session 2 export]
```

---

## Related Examples

- [Debugging a Slow Session](debugging-slow-session.md) — Manual debugging
- [Optimizing MCP Config](optimizing-mcp-config.md) — Server optimization

---

*See [Feature Reference](../FEATURES.md#ai-export) for export format details.*
