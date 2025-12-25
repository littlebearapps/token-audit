# Example: Team-Wide Tracking

Aggregate Token Audit data across multiple projects and team members.

---

## The Problem

Your team uses AI coding assistants across multiple projects:
- Each developer has their own usage patterns
- Cost allocation is unclear
- Best practices aren't being shared

**Goal:** Establish team-wide visibility into AI tool usage and costs.

---

## Prerequisites

- Token Audit installed on all team member machines
- Multiple projects being tracked
- Shared configuration strategy

---

## Step-by-Step Solution

### Step 1: Standardize Configuration

Create a team-wide `token-audit.toml` configuration:

```toml
# team-token-audit.toml
# Distribute to all team members at ~/.token-audit/token-audit.toml

[pricing.anthropic]
"claude-sonnet-4-20250514" = { input = 3.00, output = 15.00, cache_create = 3.75, cache_read = 0.30 }
"claude-opus-4-5-20251101" = { input = 15.00, output = 75.00, cache_create = 18.75, cache_read = 1.50 }

[pricing.openai]
"gpt-5.1" = { input = 1.25, output = 10.00, cache_read = 0.125 }
"o4-mini" = { input = 4.00, output = 16.00, cache_read = 1.00 }

[pricing.google]
"gemini-2.5-pro" = { input = 1.25, output = 10.00, cache_read = 0.125 }

[zombie_tools.zen]
tools = [
    "mcp__zen__thinkdeep",
    "mcp__zen__chat",
    "mcp__zen__debug",
    "mcp__zen__refactor"
]
```

### Step 2: Establish Session Naming Convention

Use consistent project identifiers:

```bash
# Before starting work, navigate to project directory
cd /path/to/project-name
token-audit collect --platform claude-code
```

Sessions are automatically tagged with the working directory path.

### Step 3: Collect Individual Reports

Each team member generates their reports:

```bash
# Weekly report
token-audit report --since "1 week ago"

# Export to JSON for aggregation
token-audit export json > ~/reports/$(whoami)-$(date +%Y%m%d).json
```

### Step 4: Aggregate Team Data

Collect JSON exports from all team members:

```bash
# On aggregation machine
mkdir -p /shared/token-audit-reports

# Team members copy their exports
# alice: scp ~/reports/*.json admin@server:/shared/token-audit-reports/
# bob: scp ~/reports/*.json admin@server:/shared/token-audit-reports/
```

### Step 5: Generate Team Dashboard

Create a simple aggregation script:

```python
#!/usr/bin/env python3
"""team_dashboard.py - Aggregate team Token Audit data"""

import json
from pathlib import Path
from collections import defaultdict

def aggregate_reports(report_dir: str):
    reports = Path(report_dir).glob("*.json")

    team_totals = defaultdict(lambda: {
        "sessions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "mcp_calls": 0
    })

    for report_file in reports:
        # Extract username from filename
        username = report_file.stem.split("-")[0]

        with open(report_file) as f:
            data = json.load(f)

        team_totals[username]["sessions"] += 1
        team_totals[username]["input_tokens"] += data.get("input_tokens", 0)
        team_totals[username]["output_tokens"] += data.get("output_tokens", 0)
        team_totals[username]["cost_usd"] += data.get("cost_usd", 0.0)
        team_totals[username]["mcp_calls"] += data.get("mcp_calls", 0)

    return dict(team_totals)

if __name__ == "__main__":
    totals = aggregate_reports("/shared/token-audit-reports")

    print("Team AI Usage Summary")
    print("=" * 60)

    grand_total = 0.0
    for user, stats in sorted(totals.items()):
        print(f"\n{user}:")
        print(f"  Sessions: {stats['sessions']}")
        print(f"  Tokens: {stats['input_tokens']:,} in / {stats['output_tokens']:,} out")
        print(f"  MCP Calls: {stats['mcp_calls']}")
        print(f"  Cost: ${stats['cost_usd']:.2f}")
        grand_total += stats["cost_usd"]

    print(f"\n{'=' * 60}")
    print(f"TEAM TOTAL: ${grand_total:.2f}")
```

### Step 6: Identify Best Practices

Analyze patterns across the team:

```bash
# Find most efficient sessions
# Look for: high cache ratios, low tokens/call, minimal smells

# Example analysis
token-audit report --smells  # See what patterns to avoid
```

Share findings:
- Which MCP servers are most valuable
- Common anti-patterns to avoid
- Optimal configuration settings

### Step 7: Establish Usage Guidelines

Create team guidelines based on data:

```markdown
## Team AI Usage Guidelines

### Recommended Practices
1. Use Claude Code for complex reasoning tasks
2. Use Gemini CLI for cost-sensitive bulk operations
3. Keep thinkdeep calls to <5 per session
4. Target >70% cache hit ratio

### MCP Server Configuration
- Required: brave-search, context7
- Optional: zen (for complex tasks only)
- Avoid: servers with <10% utilization

### Cost Targets
- Individual: <$50/week
- Team: <$500/week
- Alert threshold: >$20/day
```

---

## Expected Output

Weekly team dashboard:

```
Team AI Usage Summary (Week of Dec 9-15)
============================================================

alice:
  Sessions: 12
  Tokens: 456,000 in / 89,000 out
  MCP Calls: 145
  Cost: $32.50
  Top tools: brave_web_search (45), thinkdeep (12)

bob:
  Sessions: 8
  Tokens: 234,000 in / 56,000 out
  MCP Calls: 87
  Cost: $18.20
  Top tools: chat (34), read_url (28)

carol:
  Sessions: 15
  Tokens: 678,000 in / 124,000 out
  MCP Calls: 234
  Cost: $45.80
  Top tools: thinkdeep (45), debug (23)  ⚠️ High thinkdeep usage

============================================================
TEAM TOTAL: $96.50 (within $100 target)

Recommendations:
- Carol: Consider using chat instead of thinkdeep for simpler queries
- Team average cache ratio: 68% (target: 70%)
```

---

## Key Takeaways

1. **Standardize configuration** — Same pricing, same zombie tool detection
2. **Consistent naming** — Makes aggregation possible
3. **Regular reporting** — Weekly cadence works well
4. **Share learnings** — Turn data into actionable guidelines
5. **Set targets** — Use data to establish reasonable budgets

---

## Automation Ideas

### Slack/Teams Integration

```bash
# Weekly report to Slack
token-audit report --since "1 week ago" --format json | \
  curl -X POST -H 'Content-type: application/json' \
  --data @- https://hooks.slack.com/services/XXX
```

### Automated Alerts

```bash
# Alert if daily cost exceeds threshold
DAILY_COST=$(token-audit report --since "1 day ago" --format json | jq '.cost_usd')
if (( $(echo "$DAILY_COST > 20" | bc -l) )); then
  echo "High AI cost alert: $DAILY_COST"
fi
```

---

## Related Examples

- [Comparing Platform Costs](comparing-platform-costs.md) — Individual platform analysis
- [CI/CD Integration](ci-cd-integration.md) — Automated tracking

---

*See [Configuration Reference](../configuration.md) for full config options.*
