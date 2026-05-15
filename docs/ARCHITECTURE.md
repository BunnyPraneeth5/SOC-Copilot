# System Architecture

SOC Copilot follows a **layered architecture** with clear separation of concerns. Each layer is independently testable and replaceable.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER (PyQt6)                       │
│                                                                     │
│  Dashboard  │  Alerts View  │  AI Assistant  │  Config Panel        │
│  Real-time  │  Filter/Sort  │  Explanations  │  Settings            │
│  metrics    │  drill-down   │  per alert     │  thresholds          │
├─────────────┴───────────────┴────────────────┴──────────────────────┤
│                    CONTROLLER BRIDGE (QThread)                       │
│           Offloads heavy processing from the UI thread               │
├─────────────────────────────────────────────────────────────────────┤
│                    CONTROLLER LAYER                                  │
│                                                                     │
│  AppController ─── orchestrates both detection layers:               │
│  ┌────────────────────┐   ┌───────────────────────────┐             │
│  │ Text Log Classifier│   │ Network-Flow ML Pipeline  │             │
│  │ (12 features, RF)  │   │ (64-78 features, IF + RF) │             │
│  └────────────────────┘   └───────────────────────────┘             │
│         ↓ merge alerts             ↓                                 │
│  ┌──────────────────────────────────────────────┐                   │
│  │        Unified Alert Stream + Dedup          │                   │
│  └──────────────────────────────────────────────┘                   │
├─────────────────────────────────────────────────────────────────────┤
│                    DATA LAYER                                        │
│                                                                     │
│  Log Ingestion ─── Preprocessing ─── Feature Engineering            │
│  • CSV/TSV         • Cleaning        • Statistical (33)             │
│  • JSON/JSONL      • Normalizing     • Temporal (9)                 │
│  • Syslog          • Validating      • Behavioral (10)              │
│  • EVTX            • Encoding        • Network (12)                 │
│  • Custom Text                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                    INGESTION LAYER                                   │
│                                                                     │
│  File Tailer ─── Directory Watcher ─── System Log Reader            │
│  Micro-Batch Buffer ─── Kill Switch                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Raw Logs → Parser Factory → Parsed Records → Preprocessor
     ↓
Feature Pipeline (64–78 features)
     ↓
┌────────────────┐    ┌─────────────────┐
│ Isolation Forest│    │  Random Forest   │
│ (anomaly score) │    │ (classification) │
└───────┬────────┘    └────────┬─────────┘
        └──────┐    ┌──────────┘
         Ensemble Coordinator
               ↓
        Risk Score + Priority
               ↓
        Alert Generation
               ↓
        Deduplication (5-min window)
               ↓
        Dashboard Display
```

## Module Reference

### `src/soc_copilot/core/`
Base infrastructure — `BaseParser`, configuration management (`Config`), and structured logging via `structlog`.

### `src/soc_copilot/data/log_ingestion/`
Multi-format log parser with automatic format detection. The `ParserFactory` routes files to the correct parser (CSV, JSON, Syslog, EVTX) based on extension and content heuristics.

### `src/soc_copilot/data/preprocessing/`
Data cleaning pipeline: missing value imputation, type normalization, label encoding, and outlier handling.

### `src/soc_copilot/data/feature_engineering/`
Four parallel feature extractors that produce a 64–78 dimensional vector per log record. Each extractor specializes in one feature category (statistical, temporal, behavioral, network).

### `src/soc_copilot/models/`
ML model layer with two independent models plus an ensemble:
- **Isolation Forest** — Unsupervised anomaly detection
- **Random Forest** — Supervised multi-class attack classification
- **Ensemble Coordinator** — Combines scores with configurable weights

### `src/soc_copilot/phase4/controller/`
Application orchestrator. `AppController` manages the ML pipeline, text log classifier, rule-based fallback, result storage, and dashboard state reporting.

### `src/soc_copilot/phase4/ingestion/`
Real-time log ingestion with micro-batching. Watches files/directories, buffers records, and flushes batches to the controller at configurable intervals.

### `src/soc_copilot/phase4/ui/`
PyQt6 desktop interface with dashboard, alerts view, AI assistant panel, configuration panel, and system status bar.

### `models/text_log_classifier/`
Separate Random Forest classifier (12 features, 5 classes) trained on text log characteristics. Used for custom log formats that the network-flow model can't handle.

## Configuration Architecture

All configs use YAML and live in `config/`:

| File | Purpose |
|------|---------|
| `thresholds.yaml` | Alert scoring, priority levels, deduplication |
| `features.yaml` | Feature definitions for all 4 extractors |
| `model_config.yaml` | ML model hyperparameters |
| `ingestion/system_logs.yaml` | System log monitoring settings |
| `governance/` | Governance policies and compliance |

## Security Architecture

- **Offline core** — Detection, inference, UI, governance, and storage run locally with no cloud dependency
- **Optional online enrichment** — External reputation/recon lookups are blocked unless `SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT=true`
- **Permission-aware** — Checks OS permissions before accessing system logs
- **Kill switch** — Emergency stop mechanism via file-based flag
- **Governance layer** — Phase 3 governance controls and audit logging
- **File permissions** — Secure mode (600/640) on model and log files
