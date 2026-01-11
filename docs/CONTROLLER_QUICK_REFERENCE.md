# Sprint-15 Controller Quick Reference

## Overview
Sprint-15 implements an Application Controller Layer that orchestrates real-time ingestion → analysis → results.

## Quick Start

### Basic Setup
```python
from soc_copilot.phase4.controller import AppController

controller = AppController(models_dir="data/models")
controller.initialize()
```

### Process Batch
```python
records = [
    {"raw_line": "log line 1"},
    {"raw_line": "log line 2"}
]

result = controller.process_batch(records)

if result:
    print(f"Alerts: {len(result.alerts)}")
    print(f"Processed: {result.stats.processed_records}")
```

### With Kill Switch
```python
from soc_copilot.phase3.governance import KillSwitch

killswitch = KillSwitch("data/governance/governance.db")

controller = AppController(
    models_dir="data/models",
    killswitch_check=lambda: killswitch.is_enabled()
)
```

## Complete Integration Example

```python
from soc_copilot.phase4.ingestion import IngestionController
from soc_copilot.phase4.controller import AppController
from soc_copilot.phase3.governance import KillSwitch

# Setup governance
killswitch = KillSwitch("data/governance/governance.db")

# Setup controller
app_controller = AppController(
    models_dir="data/models",
    killswitch_check=lambda: killswitch.is_enabled()
)
app_controller.initialize()

# Setup ingestion
ingestion = IngestionController(
    batch_interval=5.0,
    killswitch_check=lambda: killswitch.is_enabled()
)
ingestion.set_batch_callback(app_controller.process_batch)
ingestion.add_file_source("/var/log/access.log")

# Start real-time analysis
ingestion.start()

# ... runs continuously ...

# View results
results = app_controller.get_results(limit=10)
for result in results:
    print(f"Batch {result.batch_id}:")
    for alert in result.alerts:
        print(f"  {alert.priority}: {alert.classification}")

# Stop
ingestion.stop()
```

## API Reference

### AppController

**Initialize:**
```python
controller = AppController(
    models_dir="data/models",
    killswitch_check=None  # Optional
)
controller.initialize()
```

**Process Batch:**
```python
result = controller.process_batch(records)
# Returns AnalysisResult or None (if kill switch enabled)
```

**Get Results:**
```python
# Latest N results
results = controller.get_results(limit=10)

# Specific result
result = controller.get_result_by_id("batch-123")

# Statistics
stats = controller.get_stats()
```

**Clear Results:**
```python
controller.clear_results()
```

### AnalysisResult

```python
result.batch_id          # str
result.timestamp         # datetime
result.alerts            # List[AlertSummary]
result.stats             # PipelineStats
result.raw_count         # int
```

### AlertSummary

```python
alert.alert_id           # str
alert.priority           # str (e.g., "P1-High")
alert.classification     # str (e.g., "BruteForce")
alert.confidence         # float (0.0-1.0)
alert.anomaly_score      # float (0.0-1.0)
alert.risk_score         # float (0.0-1.0)
alert.source_ip          # Optional[str]
alert.destination_ip     # Optional[str]
alert.timestamp          # datetime
alert.reasoning          # str
alert.suggested_action   # str
```

### PipelineStats

```python
stats.total_records              # int
stats.processed_records          # int
stats.alerts_generated           # int
stats.risk_distribution          # Dict[str, int]
stats.classification_distribution # Dict[str, int]
stats.processing_time            # float (seconds)
```

## Kill Switch Behavior

### Enabled (Phase-3 Disabled)
```python
result = controller.process_batch(records)
# Returns None (batch discarded)
```

### Disabled (Phase-3 Enabled)
```python
result = controller.process_batch(records)
# Returns AnalysisResult (batch processed)
```

## Result Storage

### Max Results
```python
# Default: 1000 results
controller = AppController(models_dir="data/models")

# Custom limit
controller.result_store = ResultStore(max_results=500)
```

### FIFO Eviction
- When max reached, oldest results are removed
- Latest results always available

### Thread Safety
- All operations are thread-safe
- Safe for concurrent access

## Error Handling

### Pipeline Not Initialized
```python
try:
    result = controller.process_batch(records)
except RuntimeError:
    print("Call initialize() first")
```

### Empty Batch
```python
result = controller.process_batch([])
# Returns None (no processing)
```

### Invalid Records
```python
records = [{"other": "data"}]  # No raw_line
result = controller.process_batch(records)
# Returns None (no valid lines)
```

## Performance Tips

1. **Initialize Once**: Call `initialize()` once at startup
2. **Batch Size**: Larger batches = more efficient (but slower per batch)
3. **Result Limit**: Increase if you need more history
4. **Clear Periodically**: Clear old results to free memory

## Monitoring

### Controller Stats
```python
stats = controller.get_stats()
print(f"Pipeline loaded: {stats['pipeline_loaded']}")
print(f"Results stored: {stats['results_stored']}")
```

### Result Count
```python
count = controller.result_store.count()
print(f"Total results: {count}")
```

### Latest Results
```python
results = controller.get_results(limit=5)
for result in results:
    print(f"{result.timestamp}: {len(result.alerts)} alerts")
```

## Common Patterns

### Alert Filtering
```python
results = controller.get_results(limit=100)

# High priority only
high_priority = [
    alert
    for result in results
    for alert in result.alerts
    if alert.priority in ["P0-Critical", "P1-High"]
]
```

### Statistics Aggregation
```python
results = controller.get_results(limit=100)

total_alerts = sum(len(r.alerts) for r in results)
total_processed = sum(r.stats.processed_records for r in results)

print(f"Total alerts: {total_alerts}")
print(f"Total processed: {total_processed}")
```

### Export Results
```python
import json

results = controller.get_results(limit=100)

export_data = [
    {
        "batch_id": r.batch_id,
        "timestamp": r.timestamp.isoformat(),
        "alert_count": len(r.alerts),
        "processed": r.stats.processed_records
    }
    for r in results
]

with open("results.json", "w") as f:
    json.dump(export_data, f, indent=2)
```

## Testing

Run tests:
```bash
python -m pytest tests/unit/test_controller_sprint15.py -v
```

## Troubleshooting

### No Results
```python
stats = controller.get_stats()
if not stats["pipeline_loaded"]:
    print("Pipeline not initialized")
    controller.initialize()
```

### Kill Switch Blocking
```python
from soc_copilot.phase3.governance import KillSwitch

killswitch = KillSwitch("data/governance/governance.db")
state = killswitch.get_state()

if state["enabled"]:
    print("Kill switch is enabled - analysis blocked")
```

### Memory Usage
```python
# Clear old results
controller.clear_results()

# Or reduce max results
controller.result_store = ResultStore(max_results=100)
```

## Safety

- ✅ Kill switch enforced
- ✅ Thread-safe storage
- ✅ No Phase-1/2/3 modifications
- ✅ Read-only results
- ✅ No auto-actions
- ✅ No learning loops
- ✅ User-initiated only
