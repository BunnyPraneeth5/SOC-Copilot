# Sprint-14 Ingestion Quick Reference

## Overview
Sprint-14 implements real-time log ingestion with micro-batching for SOC Copilot.

## Quick Start

### Basic File Tailing
```python
from soc_copilot.phase4.ingestion import IngestionController

def process_batch(records):
    for record in records:
        print(record["raw_line"])

controller = IngestionController(batch_interval=5.0)
controller.set_batch_callback(process_batch)
controller.add_file_source("/var/log/access.log")

controller.start()
# ... ingestion runs ...
controller.stop()
```

### Directory Watching
```python
controller = IngestionController(batch_interval=5.0)
controller.set_batch_callback(process_batch)
controller.add_directory_source("/var/log", pattern="*.log")

controller.start()
# ... watches for new .log files ...
controller.stop()
```

### Kill Switch Integration
```python
from soc_copilot.phase3.governance import KillSwitch

killswitch = KillSwitch("data/governance/governance.db")

controller = IngestionController(
    batch_interval=5.0,
    killswitch_check=lambda: killswitch.is_enabled()
)
```

## API Reference

### IngestionController

**Constructor:**
```python
IngestionController(
    batch_interval: float = 5.0,
    killswitch_check: Optional[Callable[[], bool]] = None
)
```

**Methods:**
- `add_file_source(filepath: str)` - Add file to tail
- `add_directory_source(directory: str, pattern: str = "*.log")` - Watch directory
- `set_batch_callback(callback: Callable[[List[dict]], None])` - Set batch processor
- `start()` - Start ingestion
- `stop()` - Stop ingestion (graceful)
- `is_running() -> bool` - Check if running
- `get_stats() -> dict` - Get statistics

**Statistics:**
```python
{
    "running": bool,
    "buffer_size": int,
    "sources_count": int,
    "batch_interval": float
}
```

### MicroBatchBuffer

**Constructor:**
```python
MicroBatchBuffer(
    batch_interval: float = 5.0,
    max_size: int = 10000
)
```

**Methods:**
- `add(record: dict) -> bool` - Add record (returns False if full)
- `flush() -> List[dict]` - Flush and return all records
- `should_flush() -> bool` - Check if should flush
- `size() -> int` - Get current size
- `clear()` - Clear buffer

### FileTailer

**Constructor:**
```python
FileTailer(
    filepath: str,
    callback: Callable[[str], None]
)
```

**Methods:**
- `start()` - Start tailing
- `stop()` - Stop tailing

### DirectoryWatcher

**Constructor:**
```python
DirectoryWatcher(
    directory: str,
    callback: Callable[[str], None],
    pattern: str = "*.log"
)
```

**Methods:**
- `start()` - Start watching
- `stop()` - Stop watching

## Record Format

Each record in batch:
```python
{
    "raw_line": str,      # Raw log line
    "timestamp": float    # Unix timestamp when ingested
}
```

## Configuration

### Batch Interval
Controls how often buffer is flushed:
```python
controller = IngestionController(batch_interval=5.0)  # 5 seconds
```

### Buffer Size
Maximum records before forced flush:
```python
buffer = MicroBatchBuffer(batch_interval=5.0, max_size=10000)
```

### File Pattern
Filter files in directory:
```python
controller.add_directory_source("/var/log", pattern="*.log")
controller.add_directory_source("/var/log", pattern="access*.log")
controller.add_directory_source("/var/log", pattern="*.txt")
```

## Examples

### Multiple Sources
```python
controller = IngestionController(batch_interval=5.0)
controller.set_batch_callback(process_batch)

# Multiple files
controller.add_file_source("/var/log/access.log")
controller.add_file_source("/var/log/error.log")

# Multiple directories
controller.add_directory_source("/var/log/app", pattern="*.log")
controller.add_directory_source("/var/log/web", pattern="access*.log")

controller.start()
```

### With Statistics
```python
controller = IngestionController(batch_interval=5.0)
controller.add_file_source("/var/log/access.log")

controller.start()

while controller.is_running():
    stats = controller.get_stats()
    print(f"Buffer: {stats['buffer_size']} records")
    time.sleep(1)

controller.stop()
```

### Integration with Detection Pipeline
```python
from soc_copilot.pipeline import create_soc_copilot
from soc_copilot.phase4.ingestion import IngestionController

# Load detection pipeline
copilot = create_soc_copilot("data/models")

def process_batch(records):
    # Extract raw lines
    lines = [r["raw_line"] for r in records]
    
    # Process through detection pipeline
    # (implementation depends on pipeline API)
    for line in lines:
        # Parse, analyze, generate alerts
        pass

controller = IngestionController(batch_interval=5.0)
controller.set_batch_callback(process_batch)
controller.add_file_source("/var/log/access.log")

controller.start()
```

## Performance Tips

1. **Batch Interval**: Larger intervals = fewer batches, more efficient
2. **Buffer Size**: Increase for high-volume logs
3. **Multiple Sources**: All sources share one buffer
4. **Kill Switch**: Check is lightweight (every flush cycle)

## Troubleshooting

### Buffer Filling Up
```python
stats = controller.get_stats()
if stats["buffer_size"] > 8000:
    print("Warning: Buffer nearly full")
```

### Check If Running
```python
if not controller.is_running():
    print("Ingestion stopped")
    controller.start()
```

### Graceful Shutdown
```python
try:
    controller.start()
    # ... run ...
finally:
    controller.stop()  # Always stop gracefully
```

## Testing

Run tests:
```bash
python -m pytest tests/unit/test_ingestion_sprint14.py -v
```

## Limitations

- **Not True Streaming**: Uses micro-batching (5s default)
- **File-Based Only**: No syslog listener yet
- **No Parsing**: Raw lines only
- **In-Memory Buffer**: No persistence
- **No Backpressure**: Buffer may fill if callback is slow

## Safety

- ✅ Thread-safe buffer
- ✅ Graceful shutdown
- ✅ Kill switch integration
- ✅ Overflow protection
- ✅ No Phase-1/2/3 modifications
- ✅ User-initiated only (no daemon)
