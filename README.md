# 🛡️ SOC Copilot

**An AI-Powered Security Operations Center Assistant for Automated Threat Detection and Intelligent Incident Response**

SOC Copilot is an offline-first, desktop-based security analysis platform that combines hybrid Machine Learning (Isolation Forest + Random Forest) with rule-based detection to provide real-time threat monitoring, intelligent alert generation, and explainable incident analysis. The core detection pipeline runs locally with zero cloud dependency. Optional threat-intelligence enrichment agents can call external services only when explicitly enabled.

---

## 📋 Table of Contents

- [Key Features](#-key-features)
- [Architecture Overview](#-architecture-overview)
- [How It Works](#-how-it-works)
- [Tech Stack](#-tech-stack)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Usage](#-usage)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [Detection Capabilities](#-detection-capabilities)
- [ML Models](#-ml-models)
- [Feature Engineering](#-feature-engineering)
- [Testing](#-testing)
- [Troubleshooting](#-troubleshooting)
- [Production Deployment](#-production-deployment)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| **Hybrid ML Detection** | Isolation Forest (unsupervised anomaly detection) + Random Forest (supervised attack classification) ensemble |
| **Text Log ML Classifier** | Separate Random Forest model (99.65% accuracy) trained on text log features — detects brute force, malware, exfiltration, and suspicious activity |
| **Multi-Format Log Ingestion** | Supports CSV, JSON/JSONL, Syslog (RFC 3164/5424), Windows EVTX, and custom text log formats |
| **Real-Time Dashboard** | PyQt6 desktop interface with live threat monitoring, interactive alert tables, and system health metrics |
| **AI-Powered Explanations** | Every alert includes human-readable reasoning, risk scoring, and actionable suggested responses |
| **Alert Deduplication** | Intelligent grouping of related alerts within configurable time windows to reduce analyst fatigue |
| **Fully Offline** | All inference, processing, and UI run entirely on-premise — no internet connection required |
| **Optional Online Enrichment** | AbuseIPDB, VirusTotal, Shodan, WHOIS, and geo-IP lookups are disabled by default and require explicit opt-in |
| **Kill Switch** | Emergency stop mechanism to instantly halt all processing |
| **Modular & Extensible** | Plugin-ready architecture designed for adding new ML models (Autoencoder, Transformer, etc.) |
| **Cross-Platform** | Runs on Windows, macOS, and Linux |

---

## 🏗️ Architecture Overview

SOC Copilot follows a **layered architecture** with clear separation of concerns:

```
┌──────────────────────────────────────────────────────────────────────┐
│                     PRESENTATION LAYER (PyQt6)                      │
│  ┌────────────┐  ┌─────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │  Dashboard  │  │ Alerts View │  │ AI Asst. │  │ Config Panel  │  │
│  └─────┬──────┘  └──────┬──────┘  └────┬─────┘  └───────┬───────┘  │
│        └────────────────┼──────────────┼─────────────────┘          │
│                    Controller Bridge (QThread)                       │
├──────────────────────────────────────────────────────────────────────┤
│                      CONTROLLER LAYER                                │
│  ┌───────────────────────────────────────────────────────────┐      │
│  │               AppController (Orchestrator)                 │      │
│  │  ┌──────────────────┐    ┌──────────────────────────────┐ │      │
│  │  │ Rule-Based Detect │    │      ML Pipeline             │ │      │
│  │  │ • Brute Force     │    │  ┌─────────┐  ┌───────────┐ │ │      │
│  │  │ • Malware         │    │  │   IF    │  │    RF     │ │ │      │
│  │  │ • Exfiltration    │    │  │(Anomaly)│  │(Classify) │ │ │      │
│  │  └──────────────────┘    │  └─────────┘  └───────────┘ │ │      │
│  │                           │       Ensemble Coordinator   │ │      │
│  │                           └──────────────────────────────┘ │      │
│  └───────────────────────────────────────────────────────────┘      │
├──────────────────────────────────────────────────────────────────────┤
│                        DATA LAYER                                    │
│  ┌──────────────┐  ┌────────────────┐  ┌───────────────────────┐    │
│  │ Log Ingestion │  │ Preprocessing  │  │ Feature Engineering   │    │
│  │ • CSV         │  │ • Cleaning     │  │ • Statistical (33)    │    │
│  │ • JSON/JSONL  │  │ • Normalizing  │  │ • Temporal (9)        │    │
│  │ • Syslog      │  │ • Validating   │  │ • Behavioral (10)     │    │
│  │ • EVTX        │  │ • Encoding     │  │ • Network (12)        │    │
│  │ • Custom Text │  │                │  │   Total: 64-78        │    │
│  └──────────────┘  └────────────────┘  └───────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ How It Works

SOC Copilot processes security logs through a **six-stage pipeline**:

### Stage 1: Log Ingestion
Raw log files are ingested through format-specific parsers. The system auto-detects the format based on file extension and content analysis:
- **CSV/TSV** → Tabular network flow data (CICIDS, NetFlow)
- **JSON/JSONL** → Structured log entries
- **Syslog** → RFC 3164 (BSD) and RFC 5424 (modern) formats
- **EVTX** → Windows Event Logs
- **Custom Text** → Key-value log formats (e.g., `UserLogin user=admin ip=10.0.0.1`)

### Stage 2: Preprocessing
Raw parsed records are cleaned, normalized, and validated:
- Missing value imputation
- Field type normalization (IPs, timestamps, ports)
- Label encoding for categorical fields
- Outlier handling

### Stage 3: Feature Engineering
Four specialized extractors generate a **64–78 dimensional feature vector** per record:

| Extractor | Features | Examples |
|-----------|----------|----------|
| **Statistical** | 33 | Event counts, unique destinations, port entropy, byte totals, z-scores |
| **Temporal** | 9 | Hour of day, day of week, business hours flag, time-since-last-event |
| **Behavioral** | 10 | Session duration, request rate, deviation from baseline |
| **Network** | 12 | IP rarity score, protocol anomaly, port scan indicator, fanout ratio |

### Stage 4: Rule-Based Detection
Before ML inference, a deterministic rules engine scans for obvious threat patterns:

| Rule | Condition | Priority |
|------|-----------|----------|
| Brute Force (Critical) | `LoginAttempt` ≥ 10 attempts from external IP | P1-Critical |
| Brute Force (High) | `LoginAttempt` ≥ 5 attempts | P1/P2 |
| Malware Execution | `FileExecution` with `.exe` or `payload` | P1-Critical |
| Data Exfiltration (Critical) | `DataTransfer` > 2GB to external IP | P1-Critical |
| Data Exfiltration (High) | `DataTransfer` > 500MB to external IP | P2-High |

### Stage 5: ML Inference & Ensemble Scoring
Each feature vector passes through both ML models in parallel:

1. **Isolation Forest** → Anomaly score (0.0 – 1.0)
   - Unsupervised: learns what "normal" looks like
   - High scores = rare/anomalous behavior
2. **Random Forest** → Attack classification + confidence
   - Supervised: trained on labeled CICIDS2017 data
   - Classifies into: Benign, DoS, DDoS, PortScan, BruteForce, Botnet, Infiltration, Web Attack

The **Ensemble Coordinator** combines both signals using configurable weights:
```
Risk Score = (IF_weight × anomaly_score) + (RF_weight × classification_confidence) + (context_weight × context_score)
```
Default weights: IF = 0.4, RF = 0.4, Context = 0.2

### Stage 6: Alert Generation & Deduplication
High-risk results generate alerts with:
- **Priority level**: P1-Critical (≥0.85), P2-High (≥0.70), P3-Medium (≥0.50), P4-Low (≥0.30)
- **Human-readable reasoning**: Explains *why* the alert was triggered
- **Suggested action**: Recommends concrete remediation steps
- **Deduplication**: Groups related alerts within a 5-minute window by source IP, destination IP, and attack class

Text log ML alerts and network-flow ML alerts are **merged into a unified alert stream** displayed on the dashboard. If the text log model is unavailable, the system falls back to rule-based detection.

---

## 🔧 Tech Stack

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Language** | Python 3.10+ | Core platform |
| **ML Framework** | scikit-learn ≥ 1.3 | Isolation Forest, Random Forest, StandardScaler, LabelEncoder |
| **Data Processing** | pandas ≥ 2.0, NumPy ≥ 1.24 | Feature engineering, data manipulation |
| **Desktop UI** | PyQt6 ≥ 6.5 | Dashboard, alerts view, configuration panels |
| **Model Persistence** | joblib ≥ 1.3 | Serialized model storage |
| **Configuration** | pydantic ≥ 2.0, PyYAML ≥ 6.0 | Type-safe config validation |
| **Log Parsing** | python-evtx ≥ 0.8 | Windows Event Log parsing |
| **Logging** | structlog ≥ 23.1 | Structured application logging |
| **Date Handling** | python-dateutil ≥ 2.8 | Timestamp parsing and normalization |
| **Packaging** | PyInstaller ≥ 6.0 | Standalone executable builds |

---

## 📦 Prerequisites

- **Python**: 3.10 or higher (3.11, 3.12 also supported)
- **RAM**: 4GB minimum, 8GB+ recommended
- **Storage**: ~500MB for models and dependencies
- **OS**: Windows 10/11, macOS 12+, or Linux (Ubuntu 20.04+)

---

## 🚀 Installation

### Quick Start (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/BunnyPraneeth5/SOC-Copilot.git
cd SOC-Copilot

# 2. Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Linux/macOS
# OR
.\venv\Scripts\activate         # Windows

# 3. Run automated setup
python setup_project.py

# 4. Verify installation
python check_requirements.py

# 5. Train ML models (required on first run)
python scripts/train_models.py

# 6. Launch the application
python launch_ui.py
```

### Manual Installation

If the automated setup fails:

```bash
# Install the package in development mode
pip install -e .

# Install dev dependencies (optional, for testing)
pip install -e ".[dev]"

# Create required directories
mkdir -p data/models data/logs logs/system

# Train models
python scripts/train_models.py

# Launch
python launch_ui.py
```

### CLI Entry Point

After installation, you can also launch via the command line:

```bash
soc-copilot
```

---

## 📖 Usage

### Desktop Application (Primary)

Launch the full-featured desktop interface:

```bash
python launch_ui.py
```

The application opens with a **splash screen** → **main window** containing:

#### Dashboard Tab
- **Live threat feed**: Real-time alerts with priority-based color coding
- **Risk distribution**: Visual breakdown of Low / Medium / High / Critical events
- **System metrics**: Records processed, alerts generated, processing time
- **Status bar**: Pipeline health, model loading status, active sources

#### Alerts Tab
- **Sortable alert table**: Filter by priority, classification, time range
- **Alert details panel**: Click any alert for full analysis with reasoning
- **AI explanations**: Natural language description of why each event is suspicious
- **Suggested actions**: Concrete remediation steps for each alert

#### Configuration Tab
- **Threshold tuning**: Adjust anomaly, classification, and priority thresholds
- **Model settings**: View and modify model parameters
- **Ingestion settings**: Configure log sources and monitoring paths

### File Upload

In the dashboard, use the **Upload Logs** button to select log files for analysis. Supported formats:
- `.csv` — CSV/TSV network flow logs
- `.json` / `.jsonl` — Structured JSON logs
- `.log` / `.syslog` — Syslog and custom text logs
- `.evtx` — Windows Event Logs

### Real-Time Monitoring

The application can continuously monitor:
- **Individual log files** in tail mode (watches for new entries)
- **Directories** with pattern matching (e.g., all `.log` files in `/var/log/`)
- **System logs** on Windows (requires appropriate permissions)

### Command Line Analysis

Analyze log files directly from the terminal:

```bash
# Analyze a single file
soc-copilot analyze /path/to/logfile.log

# Analyze a directory
soc-copilot analyze /path/to/logs/ --recursive
```

---

## 📁 Project Structure

```
SOC-Copilot/
├── src/soc_copilot/                  # Main source code
│   ├── __init__.py                   # Package metadata (v0.1.0)
│   ├── main.py                       # CLI entry point
│   ├── cli.py                        # Command-line interface
│   ├── pipeline.py                   # End-to-end SOC pipeline orchestrator
│   │
│   ├── core/                         # Core infrastructure
│   │   ├── base.py                   # Base classes (BaseParser, ParsedRecord, ParseError)
│   │   ├── config.py                 # Configuration management
│   │   └── logging.py               # Structured logging (structlog)
│   │
│   ├── data/                         # Data processing layer
│   │   ├── log_ingestion/            # Multi-format log parsing
│   │   │   ├── parser_factory.py     # Auto-detection & parser routing
│   │   │   ├── parsers/
│   │   │   │   ├── csv_parser.py     # CSV/TSV network flow logs
│   │   │   │   ├── json_parser.py    # JSON/JSONL structured logs
│   │   │   │   ├── syslog_parser.py  # RFC 3164/5424 syslog
│   │   │   │   └── evtx_parser.py    # Windows Event Logs
│   │   │   └── validators/           # Input validation
│   │   │
│   │   ├── preprocessing/            # Data cleaning & normalization
│   │   │   └── pipeline.py           # PreprocessingPipeline
│   │   │
│   │   └── feature_engineering/      # Feature extraction (64-78 features)
│   │       ├── pipeline.py           # FeatureEngineeringPipeline
│   │       ├── base.py               # BaseFeatureExtractor
│   │       ├── statistical_features.py   # 33 statistical features
│   │       ├── temporal_features.py      # 9 temporal features
│   │       ├── behavioral_features.py    # 10 behavioral features
│   │       └── network_features.py       # 12 network features
│   │
│   ├── models/                       # Machine Learning layer
│   │   ├── isolation_forest/         # Unsupervised anomaly detection
│   │   │   └── trainer.py            # IsolationForestTrainer + config
│   │   ├── random_forest/            # Supervised attack classification
│   │   │   └── trainer.py            # RandomForestTrainer + config
│   │   ├── ensemble/                 # Ensemble scoring & coordination
│   │   │   ├── coordinator.py        # Combines IF + RF scores
│   │   │   ├── pipeline.py           # AnalysisPipeline (load, analyze)
│   │   │   ├── alert_generator.py    # Priority calculation & alert creation
│   │   │   └── deduplication.py      # Time-window alert deduplication
│   │   ├── inference/                # Model loading & prediction
│   │   └── training/                 # Training utilities
│   │
│   ├── intelligence/                 # Threat intelligence layer
│   │   └── __init__.py               # Alert engine, context enrichment (extensible)
│   │
│   ├── security/                     # Security & permissions
│   │   └── permissions.py            # OS-level permission checks
│   │
│   ├── phase4/                       # Real-time processing engine
│   │   ├── kill_switch.py            # Emergency stop mechanism
│   │   ├── ingestion/                # Real-time log ingestion
│   │   │   ├── buffer.py             # Micro-batch buffer
│   │   │   ├── controller.py         # Ingestion controller
│   │   │   ├── watcher.py            # File/directory watcher
│   │   │   ├── system_log_reader.py  # System log reader
│   │   │   └── system_logs.py        # System log utilities
│   │   ├── controller/               # Application orchestration
│   │   │   ├── app_controller.py     # Main controller (ML + rule-based)
│   │   │   ├── result_store.py       # In-memory result storage (max 1000)
│   │   │   └── schemas.py            # AnalysisResult, AlertSummary, PipelineStats
│   │   ├── config/                   # Phase 4 configuration
│   │   └── ui/                       # Desktop UI (PyQt6)
│   │       ├── main_window.py        # Main application window
│   │       ├── dashboard.py          # Real-time monitoring dashboard
│   │       ├── dashboard_v2.py       # Enhanced dashboard v2
│   │       ├── dashboard_components.py # Reusable dashboard widgets
│   │       ├── alerts_view.py        # Alert table & filtering
│   │       ├── alert_details.py      # Detailed alert analysis panel
│   │       ├── assistant_panel.py    # AI explanation assistant
│   │       ├── config_panel.py       # Settings & configuration UI
│   │       ├── controller_bridge.py  # QThread bridge (UI ↔ Controller)
│   │       ├── splash_screen.py      # Application splash screen
│   │       ├── system_status_bar.py  # System health status bar
│   │       ├── state_constants.py    # UI state definitions
│   │       └── about_dialog.py       # About dialog
│   │
│   └── ui/                           # Legacy/alternate UI components
│
├── models/                           # Trained model artifacts
│   ├── random_forest/                # random_forest_v1.joblib
│   └── isolation_forest/             # isolation_forest_v1.joblib
│
├── data/                             # Runtime data directory
│   ├── datasets/                     # Training datasets (CICIDS2017)
│   ├── models/                       # Model storage (joblib files)
│   ├── models_backup/                # Model backups
│   ├── logs/                         # Ingested logs
│   ├── ioc_database/                 # Indicators of Compromise
│   ├── drift/                        # Model drift monitoring
│   ├── feedback/                     # Analyst feedback storage
│   └── governance/                   # Audit & compliance data
│
├── config/                           # Configuration files (YAML)
│   ├── thresholds.yaml               # Alert thresholds & priority scoring
│   ├── features.yaml                 # Feature definitions for all 4 extractors
│   ├── model_config.yaml             # ML model hyperparameters
│   ├── governance/                   # Governance policies
│   └── ingestion/                    # Log ingestion settings
│       └── system_logs.yaml          # System log monitoring config
│
├── scripts/                          # Utility scripts
│   ├── train_models.py               # Model training pipeline
│   ├── build_exe.py                  # PyInstaller build script
│   ├── generate_assets.py            # Asset generation
│   └── exporters/                    # Data export utilities
│
├── tests/                            # Test suite
│   ├── unit/                         # Unit tests
│   ├── integration/                  # Integration tests
│   ├── fixtures/                     # Test data fixtures
│   └── conftest.py                   # Shared pytest fixtures
│
├── docs/                             # Documentation
│   ├── DEVELOPER_MANUAL.md           # Developer guide
│   ├── USER_MANUAL.md                # End-user manual
│   ├── UML_Diagrams.md               # System design diagrams
│   ├── PROJECT_DOCUMENTATION.md      # Full project documentation
│   ├── Team_Contributions.md         # Team member contributions
│   └── diagrams/                     # Architecture & flow diagrams
│
├── assets/                           # Application assets
│   └── icon.ico                      # Application icon
│
├── logs/                             # Application logs directory
├── installer/                        # Installer artifacts
├── launch_ui.py                      # UI launcher script
├── setup_project.py                          # Automated setup script
├── check_requirements.py             # System requirements checker
├── pyproject.toml                    # Project metadata & dependencies
├── sample_logs.jsonl                 # Sample log data for testing
├── LICENSE                           # MIT License
└── README.md                         # This file
```

---

## ⚙️ Configuration

All configuration files use **YAML format** and live in the `config/` directory.

### `config/thresholds.yaml` — Alert Thresholds

```yaml
# Anomaly detection thresholds
anomaly:
  low_threshold: 0.3        # Below = normal
  high_threshold: 0.7       # Above = high anomaly

# Ensemble weight distribution (must sum to 1.0)
weights:
  isolation_forest: 0.4     # Anomaly detection contribution
  random_forest: 0.4        # Classification confidence contribution
  context: 0.2              # Business context contribution

# Alert priority levels (by final risk score)
priority:
  critical: 0.85
  high: 0.70
  medium: 0.50
  low: 0.30

# Deduplication: group related alerts within 5-minute windows
deduplication:
  window_seconds: 300
  group_by: [src_ip, dst_ip, attack_class]
```

### `config/features.yaml` — Feature Definitions

Defines the 64–78 features extracted by the four feature engineering pipelines (statistical, temporal, behavioral, network). See the file for full feature specifications.

### `config/model_config.yaml` — Model Hyperparameters

```yaml
# Isolation Forest
isolation_forest:
  n_estimators: 100
  contamination: 0.01       # Expected 1% anomaly rate
  max_features: 1.0

# Random Forest
random_forest:
  n_estimators: 100
  max_depth: null            # Unlimited depth
  class_weight: balanced     # Handle class imbalance
  random_state: 42
```

### Production Security Flags

SOC Copilot defaults to developer-friendly local operation. For production releases, enable stricter runtime checks:

```bash
# Fail model loading if model_hashes.json is missing, incomplete, or invalid
SOC_COPILOT_STRICT_MODEL_INTEGRITY=true

# Keep false/unset for offline operation. Set true only after approving external lookups.
SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT=false
```

Production model bundles should include `data/models/model_hashes.json` generated from trusted model artifacts.

---

## 🎯 Detection Capabilities

### ML-Based Detection (Network Flow Data)

Trained on the **CICIDS2017** dataset, the ML pipeline classifies:

| Attack Type | Description |
|-------------|-------------|
| **Benign** | Normal network traffic |
| **DoS** | Denial of Service attacks (Hulk, GoldenEye, Slowloris, Slowhttptest) |
| **DDoS** | Distributed Denial of Service |
| **PortScan** | Network reconnaissance via port scanning |
| **BruteForce** | FTP/SSH credential brute forcing |
| **Botnet** | Bot-controlled traffic patterns |
| **Infiltration** | Network infiltration attempts |
| **Web Attack** | SQL Injection, XSS, and brute force web attacks |

### Rule-Based Detection (Custom Text Logs)

For non-network-flow log formats, the rule-based engine detects:

| Threat | Indicators | Priority |
|--------|-----------|----------|
| **Brute Force** | ≥ 5 failed login attempts, especially from external IPs | P1/P2 |
| **Malware Execution** | Execution of `.exe` files or files containing "payload" | P1-Critical |
| **Data Exfiltration** | Large data transfers (>500MB) to external (non-RFC1918) IPs | P1/P2 |

---

## 🤖 ML Models

### Isolation Forest (Anomaly Detection)

- **Type**: Unsupervised learning
- **Purpose**: Detects anomalous behavior without labeled data
- **How it works**: Learns the "normal" distribution of network features; data points that require fewer splits to isolate are flagged as anomalies
- **Output**: Anomaly score from 0.0 (normal) to 1.0 (highly anomalous)
- **Config**: 100 estimators, 1% contamination rate
- **Model file**: `data/models/isolation_forest_v1.joblib`

### Random Forest (Attack Classification)

- **Type**: Supervised learning
- **Purpose**: Classifies attacks into specific categories
- **Training data**: CICIDS2017 dataset (~2.8M labeled network flows)
- **Output**: Attack class label + confidence score (0.0–1.0)
- **Config**: 100 estimators, unlimited depth, balanced class weights
- **Performance**: 99.88% validation accuracy
- **Model file**: `data/models/random_forest_v1.joblib`

### Ensemble Coordinator

Combines both model outputs into a single risk assessment:

```
Final Risk = 0.4 × IF_anomaly_score + 0.4 × RF_confidence + 0.2 × context_score
```

Generates alerts with priority levels, human-readable reasoning, and deduplication.

---

## 🔬 Feature Engineering

The four feature extractors produce a rich representation of each log event:

### Statistical Features (33 features)
- Per-entity event counts, unique destination counts
- Port entropy, byte totals, packet statistics
- Z-scores for deviation detection
- Entropy-based measures for distribution analysis

### Temporal Features (9 features)
- Hour of day, day of week
- Business hours flag (9 AM – 5 PM)
- Time-since-last-event per entity
- Temporal deviation from baseline

### Behavioral Features (10 features)
- Session duration, request rate
- Deviation from 24-hour baseline (z-score)
- Entity activity patterns

### Network Features (12 features)
- IP rarity score (how unusual is this IP?)
- Protocol anomaly detection
- Port scan indicators (>50 unique ports in 60s)
- Fanout ratio (connection distribution)

---

## 🧪 Testing

The project includes comprehensive unit and integration tests:

```bash
# Run all tests
python -m pytest tests/ -v

# Run unit tests only
python -m pytest tests/unit/ -v

# Run integration tests only
python -m pytest tests/integration/ -v

# Run with coverage report
python -m pytest tests/ --cov=soc_copilot --cov-report=html

# Run specific test files
python -m pytest tests/unit/test_controller_sprint15.py -v
python -m pytest tests/unit/test_dashboard_states.py -v
```

### Key Test Areas
- **Controller tests**: `test_controller_sprint15.py` (batch processing, stats, results)
- **Dashboard state tests**: `test_dashboard_states.py` (UI state transitions)
- **Shutdown tests**: `test_controller_shutdown.py` (graceful shutdown, kill switch)
- **Deduplication tests**: `test_deduplication.py` (alert grouping)

---

## 🔧 Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| **"Pipeline not loaded" error** | Run `python scripts/train_models.py` to generate model files |
| **PyQt6 import error** | Install with `pip install PyQt6>=6.5.0` |
| **"No module named soc_copilot"** | Install the package: `pip install -e .` or set `PYTHONPATH=src` |
| **0 records parsed from `.log` file** | The ML pipeline works with the full UI (file upload via dashboard). Use `python launch_ui.py` and upload logs through the GUI |
| **Permission errors** | Ensure write access to `data/` and `logs/` directories |
| **High memory usage** | Close other applications; the system needs ~4GB for model loading and inference |
| **Models not found** | Verify `data/models/` contains `isolation_forest_v1.joblib` and `random_forest_v1.joblib` |

### System Requirements Check

```bash
python check_requirements.py
```

This verifies Python version, required packages, directory structure, model availability, and system permissions.

### Fresh Installation

```bash
# Remove existing data
rm -rf data/models data/logs

# Re-run setup
python setup_project.py

# Retrain models
python scripts/train_models.py

# Verify
python check_requirements.py
```

---

## 🏭 Production Deployment

### System Requirements
- Dedicated machine with **8GB+ RAM**
- SSD storage for optimal I/O performance
- Network access to log sources

### Build Standalone Executable

```bash
# Install build dependency
pip install pyinstaller>=6.0.0

# Build executable
python scripts/build_exe.py
```

The executable will be generated in the `dist/` directory.

### Security Considerations
- Run with **minimal required permissions** (least privilege)
- Deploy in an **air-gapped / isolated network** — no internet access required
- Apply regular security updates to the host OS
- Rotate log files according to your organization's retention policy
- Enable strict model integrity for release builds
- Keep online enrichment disabled unless data-sharing with external providers is approved

### Limitations
- The text-log classifier can be trained from synthetic data for demos; production deployments should validate or retrain with representative SOC logs.
- Alert thresholds need environment-specific tuning to balance false positives and missed detections.
- Raw logs may contain sensitive usernames, IPs, hostnames, and file paths; define retention and access-control policy before production use.

### Monitoring
- Application logs are stored in `logs/`
- Model drift data is tracked in `data/drift/`
- Analyst feedback is stored in `data/feedback/` for future retraining

---

## 🤝 Contributing

### Development Setup

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Code formatting
black src/ tests/

# Linting
ruff src/ tests/

# Type checking
mypy src/
```

### Code Style
- **Line length**: 100 characters
- **Formatter**: Black
- **Linter**: Ruff
- **Type checker**: mypy (strict mode)
- **Python versions**: 3.10, 3.11, 3.12

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

```
Copyright (c) 2026 SOC Copilot Team
```

---

## 📚 Additional Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System architecture, data flow, and module reference |
| [Deployment Guide](docs/DEPLOYMENT.md) | Local, admin, PyInstaller, and network deployment |
| [Developer Manual](docs/DEVELOPER_MANUAL.md) | Developer guide and code reference |
| [User Manual](docs/USER_MANUAL.md) | End-user operation guide |
| [Contributing](CONTRIBUTING.md) | Contribution guidelines |
| [Changelog](CHANGELOG.md) | Version history |

---

## ⚡ Quick Commands

```bash
make setup          # Full automated setup
make train          # Train all ML models
make run            # Launch desktop UI
make run-admin      # Launch with admin (system logs)
make test           # Run all tests
make test-coverage  # Tests with HTML coverage report
make lint           # Code quality checks
make format         # Format code with black
make build          # Build standalone executable
make clean          # Remove build artifacts
```

---

<p align="center">
  <strong>SOC Copilot</strong> — AI-Powered Security Operations, Fully Offline.<br>
  Built with ❤️ by the SOC Copilot Team
</p>
