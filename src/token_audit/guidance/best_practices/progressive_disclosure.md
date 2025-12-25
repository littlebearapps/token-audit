---
id: progressive_disclosure
title: Progressive Tool Disclosure
severity: high
category: efficiency
token_savings: "98%"
source: "Anthropic Engineering Blog"
related_smells: [UNDERUTILIZED_SERVER, HIGH_MCP_SHARE]
keywords: [context bloat, tool count, staging, on-demand]
---

## Problem

Loading all tool definitions upfront causes severe context bloat. A typical MCP setup with 10+ servers can inject 150K+ tokens of tool schemas into every conversation, consuming valuable context window space before any actual work begins.

This manifests as:
- Slow session startup times
- Reduced effective context for actual work
- Higher costs due to inflated token counts
- UNDERUTILIZED_SERVER smells (tools loaded but never used)

## Solution

Stage tool availability based on task complexity:

1. **Core Tools** (always available): Essential tools like file read/write, search
2. **Advanced Tools** (on-demand): Specialized tools loaded when needed
3. **Specialized Tools** (explicit request): Domain-specific tools for rare tasks

## Implementation

### MCP Server Configuration

```json
{
  "mcpServers": {
    "core": {
      "command": "mcp-server-core",
      "alwaysAllow": ["read", "write", "search"]
    },
    "advanced": {
      "command": "mcp-server-advanced",
      "lazy": true
    }
  }
}
```

### Claude Code Pattern

Use profile-based MCP configurations:
- `lean` profile: 3-5 essential servers
- `full` profile: All servers for complex tasks

Switch profiles based on task requirements rather than loading everything by default.

## Evidence

- **98% token reduction** observed: 150K tokens reduced to ~2K tokens with core-only loading
- Anthropic Engineering Blog documents this as a primary optimization strategy
- token-audit data shows UNDERUTILIZED_SERVER smell correlates with >10 loaded tools

## Detection

token-audit identifies progressive disclosure opportunities through:

- **UNDERUTILIZED_SERVER**: Triggers when <10% of a server's available tools are actually used
- **HIGH_MCP_SHARE**: Triggers when MCP tool schemas consume >80% of total session tokens
- **Session Reports**: Tool count per server and usage frequency help identify staging candidates
