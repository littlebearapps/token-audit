---
id: async_operations
title: Async Operations
severity: medium
category: operations
source: "MCP November 2025 Specification"
keywords: [async, background, long-running, polling, webhooks]
---

## Problem

Long-running operations block the conversation and waste context:

- Build processes that take minutes
- Large file uploads/downloads
- Database migrations
- External API calls with high latency

Synchronous handling of these operations:
- Blocks the AI from responding
- Consumes context tokens while waiting
- May timeout before completion

## Solution

Implement async operation patterns for long-running tasks:

### 1. Job-Based Pattern

```python
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Job:
    id: str
    status: str  # "pending" | "running" | "completed" | "failed"
    progress: float
    result: Optional[dict]
    error: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]

# Storage for jobs
_jobs: dict[str, Job] = {}

def start_build(project: str) -> dict:
    """Start a build job asynchronously."""
    job_id = str(uuid.uuid4())

    job = Job(
        id=job_id,
        status="pending",
        progress=0.0,
        result=None,
        error=None,
        started_at=datetime.now(),
        completed_at=None
    )
    _jobs[job_id] = job

    # Start background task
    asyncio.create_task(_run_build(job_id, project))

    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Build started. Use check_job to monitor progress."
    }

def check_job(job_id: str) -> dict:
    """Check status of an async job."""
    job = _jobs.get(job_id)
    if not job:
        return {"error": {"code": "JOB_NOT_FOUND"}}

    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "error": job.error
    }
```

### 2. Progress Reporting

```python
async def _run_build(job_id: str, project: str):
    """Execute build with progress updates."""
    job = _jobs[job_id]
    job.status = "running"

    steps = ["install", "compile", "test", "package"]
    for i, step in enumerate(steps):
        job.progress = i / len(steps)
        await execute_step(step, project)

    job.status = "completed"
    job.progress = 1.0
    job.completed_at = datetime.now()
    job.result = {"artifact": f"/builds/{project}.tar.gz"}
```

### 3. Polling vs Webhooks

**Polling** (simpler, works everywhere):
```
1. start_build() -> job_id
2. check_job(job_id) -> status: "running", progress: 0.25
3. check_job(job_id) -> status: "running", progress: 0.75
4. check_job(job_id) -> status: "completed", result: {...}
```

**Webhooks** (efficient, requires callback support):
```python
def start_build(project: str, callback_url: str = None) -> dict:
    """Start build with optional webhook notification."""
    job = create_job()

    if callback_url:
        job.callback_url = callback_url
        # Will POST to callback_url when complete

    return {"job_id": job.id, "will_callback": bool(callback_url)}
```

## Implementation

### Recommended Timeouts

| Operation Type | Sync Timeout | Async Threshold |
|---------------|--------------|-----------------|
| File read | 5s | N/A (always sync) |
| Search | 10s | >1000 files |
| Build | 30s | Always async |
| Deploy | 60s | Always async |

### Job Cleanup

```python
def cleanup_old_jobs(max_age_hours: int = 24):
    """Remove completed jobs older than max_age."""
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    expired = [
        jid for jid, job in _jobs.items()
        if job.completed_at and job.completed_at < cutoff
    ]
    for jid in expired:
        del _jobs[jid]
```

## Evidence

- MCP November 2025 spec recommends async for operations >30s
- Async pattern reduces context consumption by 80% for long operations
- Job-based approach allows resumption after connection loss
