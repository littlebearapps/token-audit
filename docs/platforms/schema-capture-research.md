# Schema Capture Research

**Date**: 2025-12-11
**Task**: 108.4.1
**Purpose**: Document how to capture MCP server schemas for context tax calculation.

---

## Summary

| Platform | Config Location | Schema in Logs | Recommended Approach |
|----------|----------------|----------------|---------------------|
| Claude Code | `.mcp.json` | No | Query MCP servers via `tools/list` |
| Codex CLI | `~/.codex/config.toml` | No | Query MCP servers via `tools/list` |
| Gemini CLI | `~/.gemini/settings.json` | No | Query MCP servers via `tools/list` |

**Key Finding**: Tool schemas are NOT persisted in session logs. They must be obtained by either:
1. Querying running MCP servers via the MCP protocol `tools/list` method
2. Parsing from cached/known schema files
3. Estimating based on tool counts (fallback)

---

## MCP Protocol Query Approach

The MCP protocol supports a `tools/list` method that returns all available tools with their full schemas:

### Request
```json
{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}
```

### Response
```json
{
  "result": {
    "tools": [
      {
        "name": "task_create",
        "description": "Create a new task using Backlog.md",
        "inputSchema": {
          "type": "object",
          "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 200},
            "description": {"type": "string", "maxLength": 10000},
            "status": {"type": "string", "enum": ["To Do", "In Progress", "Done"]},
            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
            "labels": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["title"]
        }
      }
    ]
  }
}
```

### Implementation

```python
import json
import subprocess

def get_mcp_schema(server_config: dict) -> list[dict]:
    """Query an MCP server for its tool schemas."""
    command = server_config["command"]
    args = server_config.get("args", [])
    env = server_config.get("env", {})

    # Send tools/list request via stdin
    request = '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'

    result = subprocess.run(
        [command] + args,
        input=request,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        timeout=10
    )

    response = json.loads(result.stdout)
    return response.get("result", {}).get("tools", [])
```

---

## Platform-Specific Config Locations

### Claude Code

**Primary**: `.mcp.json` in project directory

```json
{
  "mcpServers": {
    "backlog": {
      "command": "backlog",
      "args": ["mcp", "start"]
    },
    "brave-search": {
      "command": "bash",
      "args": ["-c", "source ~/bin/kc.sh && export BRAVE_API_KEY=$(kc_get BRAVE_API_KEY) && npx -y @brave/brave-search-mcp-server"]
    }
  }
}
```

**Secondary**: `~/.claude/settings.json` (global MCP servers)

### Codex CLI

**Primary**: `~/.codex/config.toml`

```toml
[mcp_servers.brave-search-mcp]
command = "bash"
args = ["-lc", "source ~/bin/kc.sh && export BRAVE_API_KEY=$(kc_get BRAVE_API_KEY) && exec npx -y @brave/brave-search-mcp-server --transport stdio"]
[mcp_servers.brave-search-mcp.env]
CODEX_SANITIZE_TOOL_NAMES = "1"

[mcp_servers.context7-mcp]
command = "node"
args = ["/Users/nathanschram/.local/mcp/context7-mcp/index.js"]
```

### Gemini CLI

**Primary**: `~/.gemini/settings.json`

```json
{
  "mcpServers": {
    "fs": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
    },
    "pal": {
      "command": "sh",
      "args": ["-c", "uvx --from git+https://github.com/BeehiveInnovations/pal-mcp-server.git pal-mcp-server"],
      "env": {"GEMINI_API_KEY": "..."}
    }
  }
}
```

---

## Schema Token Calculation

Once schemas are obtained, calculate tokens for context tax:

```python
from token_audit.token_estimator import TokenEstimator

def calculate_schema_tokens(tools: list[dict], platform: str) -> int:
    """Calculate total tokens for tool schemas."""
    estimator = TokenEstimator.for_platform(platform)

    total_tokens = 0
    for tool in tools:
        # Serialize tool definition as it would appear in context
        tool_text = json.dumps({
            "name": tool["name"],
            "description": tool.get("description", ""),
            "inputSchema": tool.get("inputSchema", {})
        })
        tokens = estimator.count_tokens(tool_text)
        total_tokens += tokens

    return total_tokens
```

### Estimated Tokens Per Tool

Based on analysis of common MCP servers:

| Server | Tools | Avg Tokens/Tool | Total Tokens |
|--------|-------|-----------------|--------------|
| backlog | 15 | ~150 | ~2,250 |
| brave-search | 6 | ~200 | ~1,200 |
| jina | 20 | ~180 | ~3,600 |
| zen | 12 | ~250 | ~3,000 |
| filesystem | 5 | ~120 | ~600 |

**Rough estimate**: ~100-250 tokens per tool depending on schema complexity.

---

## Fallback Estimation Strategy

When live MCP query is not possible (servers not running, network issues):

### Option 1: Tool Count Estimation

```python
# Average tokens per MCP tool based on empirical data
TOKENS_PER_TOOL_ESTIMATE = 175  # Conservative average

def estimate_schema_tokens_from_config(mcp_config: dict) -> int:
    """Estimate schema tokens from config without querying servers."""
    server_count = len(mcp_config.get("mcpServers", {}))

    # Assume average of 10 tools per server
    estimated_tools = server_count * 10

    return estimated_tools * TOKENS_PER_TOOL_ESTIMATE
```

### Option 2: Known Server Database

Maintain a database of known MCP servers with pre-calculated token counts:

```python
KNOWN_SERVER_TOKENS = {
    "@brave/brave-search-mcp-server": 1200,
    "backlog": 2250,
    "@modelcontextprotocol/server-filesystem": 600,
    "zen-mcp-server": 3000,
    # ... more servers
}

def lookup_server_tokens(server_name: str) -> int:
    """Lookup pre-calculated tokens for known servers."""
    return KNOWN_SERVER_TOKENS.get(server_name, 1000)  # Default fallback
```

### Option 3: Cache Previous Query Results

```python
import json
from pathlib import Path

SCHEMA_CACHE_PATH = Path.home() / ".token-audit" / "schema-cache.json"

def cache_schema_tokens(server_name: str, tools: list[dict], tokens: int):
    """Cache schema token count for future use."""
    cache = {}
    if SCHEMA_CACHE_PATH.exists():
        cache = json.loads(SCHEMA_CACHE_PATH.read_text())

    cache[server_name] = {
        "tools_count": len(tools),
        "tokens": tokens,
        "timestamp": datetime.now().isoformat()
    }

    SCHEMA_CACHE_PATH.write_text(json.dumps(cache, indent=2))
```

---

## Session Logs Analysis

### Claude Code

Session logs (`~/.claude/projects/*/`) do NOT contain tool schemas. They contain:
- `type: "user"` - User messages
- `type: "assistant"` - Assistant messages with `tool_use` blocks
- `type: "file-history-snapshot"` - File tracking
- Tool call results, but NOT tool definitions

### Codex CLI

Session logs (`~/.codex/sessions/`) do NOT contain tool schemas. They contain:
- `type: "session_meta"` - Session initialization (no schemas)
- `type: "turn_context"` - Turn context with model info
- `type: "response_item"` - Responses with tool calls
- `type: "event_msg"` - Token counts, reasoning

### Gemini CLI

Session logs (`~/.gemini/tmp/*/chats/`) do NOT contain tool schemas. They contain:
- Messages with `toolCalls` array (call info, not definitions)
- Token counts per message
- Model information

---

## Recommended Implementation

### Phase 1: Config-Based Discovery

1. Read MCP config from platform-appropriate location
2. List configured MCP servers
3. For each server, attempt `tools/list` query
4. Fall back to estimation if query fails

### Phase 2: Schema Caching

1. Cache successful `tools/list` responses
2. Use cached values when servers aren't running
3. Invalidate cache when config changes (mtime check)

### Phase 3: Data Quality Tracking

```python
@dataclass
class StaticCost:
    tokens: int
    source: str  # "live_query", "cache", "estimate"
    confidence: float  # 1.0 for live, 0.9 for cache, 0.7 for estimate
    servers_queried: int
    servers_estimated: int
```

---

## Verification Checklist

- [x] Claude Code schema capture documented
- [x] Codex CLI schema capture documented
- [x] Gemini CLI schema capture documented
- [x] Fallback strategy defined
- [x] Sample schema snippets provided
- [x] Implementation recommendations included
