# Benign Event Deduplication Patch

## Problem
Benign (Low risk, P4-Info) events were repeatedly re-evaluated and logged, causing:
- Debug log spam
- Unnecessary CPU usage
- Runaway evaluation loop

## Solution
Implemented event deduplication with stable fingerprinting and cooldown mechanism.

## Changes

### 1. New Module: `deduplication.py`
**Location**: `src/soc_copilot/models/ensemble/deduplication.py`

**Key Features**:
- `EventDeduplicator` class with configurable cooldown (default 60s)
- Stable event fingerprinting using: classification + anomaly_score_bucket + source_ip
- Automatic cleanup of old entries to prevent memory growth
- Score bucketing (0.1 precision) to reduce noise

### 2. Pipeline Integration: `pipeline.py`
**Location**: `src/soc_copilot/models/ensemble/pipeline.py`

**Changes**:
- Added `benign_cooldown` parameter to `AnalysisPipelineConfig` (default 60s)
- Integrated `EventDeduplicator` into `AnalysisPipeline`
- Modified `analyze()` to return `Optional[AnalysisResult]` (None for deduplicated events)
- Terminal lifecycle state: deduplicated benign events return None immediately
- Periodic cleanup every 1000 analyses to prevent memory growth
- Updated `analyze_batch()` to skip None results

### 3. Main Pipeline: `pipeline.py` (SOCCopilot)
**Location**: `src/soc_copilot/pipeline.py`

**Changes**:
- Handle None results from deduplication in `analyze_records()`
- Skip deduplicated events with `continue` statement

### 4. Logging Reduction
**Locations**: 
- `src/soc_copilot/models/ensemble/coordinator.py`
- `src/soc_copilot/models/ensemble/alert_generator.py`

**Changes**:
- Suppress debug logging for benign/low-risk events in coordinator
- Remove "alert_not_required" debug spam in alert generator

### 5. Module Exports: `__init__.py`
**Location**: `src/soc_copilot/models/ensemble/__init__.py`

**Changes**:
- Export `EventDeduplicator` for external use

## Behavior

### Alert Events (P2-Medium and above)
- **Always processed** - no deduplication
- Full logging and alert generation
- Immediate action required

### Benign Events (P4-Info, Low risk)
- **First occurrence**: Processed and logged
- **Duplicates within cooldown**: Suppressed (terminal state, returns None)
- **After cooldown**: Processed again
- Minimal logging

## Configuration

Default cooldown: **60 seconds**

To customize:
```python
from soc_copilot.models.ensemble import AnalysisPipelineConfig

config = AnalysisPipelineConfig(
    models_dir="data/models",
    benign_cooldown=120.0  # 2 minutes
)
```

## Testing

Run tests:
```bash
python tests/test_deduplication.py
```

Tests verify:
- Basic deduplication with cooldown
- Fingerprint stability
- Score bucketing
- Different events get different fingerprints
- Cleanup functionality

## Impact

### Preserved
✓ Existing detection logic and thresholds unchanged
✓ Alert flow for P2+ events unchanged
✓ No UI changes required
✓ All alerts still generated

### Improved
✓ Eliminated benign event spam
✓ Reduced CPU usage for duplicate benign events
✓ Cleaner logs
✓ Terminal lifecycle state for non-alert duplicates

## Memory Management

- Automatic cleanup every 1000 analyses
- Old entries (>1 hour) removed automatically
- Fingerprint cache bounded by time, not count
- Minimal memory footprint (~16 bytes per unique event)

## Backward Compatibility

✓ Fully backward compatible
✓ Default behavior: 60s cooldown for benign events
✓ Can be disabled by setting `benign_cooldown=0.0`
