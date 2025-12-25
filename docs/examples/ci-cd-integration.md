# Example: CI/CD Integration

Integrate Token Audit into your CI/CD pipeline for automated cost monitoring.

---

## The Problem

You want to:
- Track AI costs as part of your development workflow
- Fail builds if AI usage exceeds thresholds
- Generate reports automatically after AI-assisted work

**Goal:** Automate Token Audit tracking and alerting in CI/CD pipelines.

---

## Prerequisites

- Token Audit installed (`pip install token-audit`)
- CI/CD platform (GitHub Actions, GitLab CI, Jenkins, etc.)
- AI coding assistant configured in CI environment

---

## Step-by-Step Solution

### Step 1: Install in CI Environment

```yaml
# GitHub Actions example
- name: Install Token Audit
  run: pip install token-audit
```

### Step 2: Create Cost Threshold Check

Create a script for checking cost thresholds:

```python
#!/usr/bin/env python3
"""check_ai_costs.py - Fail if AI costs exceed threshold"""

import sys
import json
from pathlib import Path

def check_costs(session_file: str, max_cost: float = 5.0) -> bool:
    """Check if session cost exceeds threshold."""
    with open(session_file) as f:
        data = json.load(f)

    cost = data.get("cost_usd", 0.0)

    print(f"Session cost: ${cost:.2f}")
    print(f"Threshold: ${max_cost:.2f}")

    if cost > max_cost:
        print(f"ERROR: Cost ${cost:.2f} exceeds threshold ${max_cost:.2f}")
        return False

    print("OK: Cost within threshold")
    return True

if __name__ == "__main__":
    session_file = sys.argv[1] if len(sys.argv) > 1 else "session.json"
    max_cost = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0

    success = check_costs(session_file, max_cost)
    sys.exit(0 if success else 1)
```

### Step 3: GitHub Actions Workflow

```yaml
# .github/workflows/ai-cost-check.yml
name: AI Cost Monitoring

on:
  workflow_run:
    workflows: ["AI-Assisted Development"]
    types: [completed]

jobs:
  check-costs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Token Audit
        run: pip install token-audit

      - name: Download session artifact
        uses: actions/download-artifact@v4
        with:
          name: ai-session
          path: ./session-data

      - name: Generate report
        run: |
          token-audit report ./session-data/*.jsonl --format json > report.json
          cat report.json

      - name: Check cost threshold
        run: |
          python scripts/check_ai_costs.py report.json 10.0

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: ai-cost-report
          path: report.json
```

### Step 4: Generate Session Artifacts

When running AI-assisted tasks, capture session data:

```yaml
# In your AI-assisted workflow
- name: Run AI task
  run: |
    # Start background tracking
    token-audit collect --platform claude-code --headless &
    TRACKER_PID=$!

    # Run your AI-assisted task
    ./run-ai-task.sh

    # Stop tracking
    kill $TRACKER_PID

- name: Export session
  run: |
    token-audit export json > session-export.json

- name: Upload session artifact
  uses: actions/upload-artifact@v4
  with:
    name: ai-session
    path: session-export.json
```

### Step 5: Add Budget Alerts

Create a workflow for budget alerts:

```yaml
# .github/workflows/weekly-ai-budget.yml
name: Weekly AI Budget Check

on:
  schedule:
    - cron: '0 9 * * 1'  # Monday 9am UTC

jobs:
  budget-check:
    runs-on: ubuntu-latest
    steps:
      - name: Aggregate weekly costs
        run: |
          pip install token-audit

          # Aggregate all sessions from past week
          token-audit report --since "1 week ago" --format json > weekly.json

          COST=$(jq '.cost_usd' weekly.json)
          echo "Weekly cost: $COST"

          if (( $(echo "$COST > 100" | bc -l) )); then
            echo "::warning::Weekly AI cost ($COST) exceeds $100 budget"
          fi

      - name: Post to Slack
        if: always()
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "Weekly AI Cost Report: ${{ env.WEEKLY_COST }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

### Step 6: PR Cost Comments

Add AI cost summaries to pull requests:

```yaml
# .github/workflows/pr-ai-summary.yml
name: PR AI Cost Summary

on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  summarize:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - name: Generate summary
        run: |
          pip install token-audit

          # Get sessions from PR branch work
          token-audit report --format markdown > summary.md

      - name: Comment on PR
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const summary = fs.readFileSync('summary.md', 'utf8');

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## AI Usage Summary\n\n${summary}`
            });
```

---

## Expected Output

### Build Log

```
=== AI Cost Monitoring ===

Generating report...
Session: claude-code-2024-12-14-abc123
Duration: 45 minutes
Platform: Claude Code

Token Usage:
  Input: 125,432
  Output: 23,456
  Cached: 89,000

Cost: $4.23

Checking threshold...
Session cost: $4.23
Threshold: $10.00
OK: Cost within threshold

Build passed
```

### PR Comment

```markdown
## AI Usage Summary

| Metric | Value |
|--------|-------|
| Sessions | 3 |
| Total tokens | 456,789 |
| Total cost | $12.34 |
| Avg cost/session | $4.11 |

### MCP Tool Usage
| Tool | Calls | Tokens |
|------|-------|--------|
| brave_web_search | 12 | 15,000 |
| thinkdeep | 5 | 125,000 |
| chat | 8 | 45,000 |

### Smells Detected
- EXPENSIVE_CALLS: 2 occurrences
- LOW_CACHE_RATIO: 1 occurrence
```

---

## Key Takeaways

1. **Automate tracking** — Don't rely on manual session capture
2. **Set thresholds** — Fail builds that exceed cost limits
3. **Report on PRs** — Make costs visible in code review
4. **Weekly summaries** — Track trends over time
5. **Alert on anomalies** — Catch unusual spending early

---

## Advanced: Headless Mode

For CI environments without TTY:

```bash
# Run in headless mode (no TUI)
token-audit collect --platform claude-code --headless --output session.jsonl

# Generate report from captured data
token-audit report session.jsonl
```

---

## Related Examples

- [Team-Wide Tracking](team-wide-tracking.md) — Aggregate across team members
- [AI-Assisted Review](ai-assisted-review.md) — Use AI to analyze sessions

---

*See [API Reference](../api.md) for programmatic integration options.*
