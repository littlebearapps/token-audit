# Performance Profiling Guide

This guide covers how to measure and optimize mcp-audit performance.

## Performance Targets (v0.9.0)

| Metric | Target | Measured |
|--------|--------|----------|
| TUI refresh | <100ms | ~0.2ms |
| Session load (1000 calls) | <500ms | ~2ms |
| Report generation (100 sessions) | <2s | ~20ms |
| Live tracking memory | <100MB | ~1MB |

## Running Benchmarks

### Quick Benchmark Run

```bash
# Run all performance benchmarks
pytest tests/benchmarks/ -v

# Run with timing details
pytest tests/benchmarks/ -v -s

# Run specific test class
pytest tests/benchmarks/test_performance.py::TestTUIPerformance -v -s
```

### CI Benchmarks

Performance benchmarks run automatically on every PR. Results are uploaded as artifacts.

```bash
# Export benchmark results as JSON
pytest tests/benchmarks/ --benchmark-json=benchmark.json
```

## Profiling with cProfile

### Profile TUI Rendering

```bash
python -c "
import cProfile
import pstats
from datetime import datetime
from mcp_audit.display.rich_display import RichDisplay
from mcp_audit.display.snapshot import DisplaySnapshot

# Create test snapshot
snapshot = DisplaySnapshot.create(
    project='profile-test',
    platform='claude-code',
    start_time=datetime.now(),
    duration_seconds=100.0,
    total_tokens=100000,
)

display = RichDisplay(refresh_rate=0.5)

# Profile 100 refreshes
profiler = cProfile.Profile()
profiler.enable()
for _ in range(100):
    display._build_layout(snapshot)
profiler.disable()

# Print stats
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
"
```

### Profile Session Loading

```bash
python -c "
import cProfile
import pstats
from pathlib import Path
from mcp_audit.session_manager import SessionManager

manager = SessionManager()

# Profile session load
profiler = cProfile.Profile()
profiler.enable()
session = manager.load_session(Path('~/.mcp-audit/sessions/claude_code/').expanduser())
profiler.disable()

stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
"
```

## Memory Profiling

### Using tracemalloc

```python
import tracemalloc
from mcp_audit.display.rich_display import RichDisplay
from mcp_audit.display.snapshot import DisplaySnapshot

tracemalloc.start()

# ... code to profile ...

current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

print(f"Current: {current / 1024 / 1024:.2f}MB")
print(f"Peak: {peak / 1024 / 1024:.2f}MB")
```

### Using memory_profiler

```bash
# Install
pip install memory_profiler

# Profile script
python -m memory_profiler your_script.py

# Line-by-line (add @profile decorator)
python -m memory_profiler -l your_script.py
```

## Optimization Techniques

### TUI Optimizations (v0.9.0)

1. **Dirty-flag tracking**: Only rebuild panels that changed
2. **Pre-sorted hierarchies**: Sort server_hierarchy in snapshot creation, not render
3. **Cached panels**: Store rendered panels between identical snapshots

### Session Loading Optimizations (v0.9.0)

1. **Header peeking**: Read first 4KB to extract metadata without full parse
2. **Mtime caching**: Cache file modification times to reduce stat() calls
3. **Streaming iterators**: Process large sessions without loading all to memory

### Report Generation Optimizations (v0.9.0)

1. **Parallel loading**: Use ThreadPoolExecutor for concurrent session loads
2. **Index pre-filtering**: Use platform indexes to skip irrelevant files
3. **Batch processing**: Process sessions in chunks to bound memory

## Benchmark Test Structure

```
tests/benchmarks/
├── __init__.py
└── test_performance.py
    ├── TestTUIPerformance           # TUI refresh benchmarks
    │   ├── test_tui_build_layout_performance
    │   ├── test_tui_unchanged_snapshot_performance
    │   ├── test_tui_header_build_performance
    │   └── test_tui_tools_build_performance
    ├── TestSessionLoadPerformance   # Session I/O benchmarks
    │   ├── test_session_load_1000_calls
    │   ├── test_session_list_performance
    │   └── test_session_json_parse_overhead
    ├── TestReportPerformance        # Report generation benchmarks
    │   └── test_multi_session_load_performance
    ├── TestMemoryUsage              # Memory benchmarks
    │   ├── test_display_snapshot_memory
    │   ├── test_tui_memory_usage
    │   └── test_session_load_memory
    └── TestBaselineMeasurements     # Baseline tracking
        ├── test_measure_index_update_baseline
        └── test_measure_snapshot_creation_baseline
```

## Adding New Benchmarks

When adding new benchmarks:

1. Add to appropriate test class in `tests/benchmarks/test_performance.py`
2. Include timing output with `print()` for visibility
3. Use `time.perf_counter()` for accurate timing
4. Add target to `TARGETS` dict if it's a critical path

Example:

```python
def test_new_operation_performance(self) -> None:
    """Description of what's being measured."""
    iterations = 10

    start = time.perf_counter()
    for _ in range(iterations):
        # operation to measure
        pass
    elapsed = (time.perf_counter() - start) / iterations
    elapsed_ms = elapsed * 1000

    print(f"\nOperation time: {elapsed_ms:.2f}ms")

    assert elapsed_ms < TARGET_MS, f"Operation took {elapsed_ms:.1f}ms, target <{TARGET_MS}ms"
```

## Interpreting Results

### What's Good

- TUI refresh <10ms: Smooth 60fps rendering
- Session load <100ms: Imperceptible delay
- Memory growth <1MB after 50 refreshes: No leaks

### Warning Signs

- TUI refresh >50ms: Noticeable lag
- Session load >1s: User-visible delay
- Memory growth >10MB: Potential leak

### When to Optimize

1. **Real user impact**: Measure with production-size data first
2. **Profile before optimizing**: Find actual bottlenecks
3. **Benchmark after changes**: Verify improvements
