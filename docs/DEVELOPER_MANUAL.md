# SOC Copilot — Phase-1 Developer User Manual

**Version**: 1.0  
**Status**: Phase-1 Complete  
**Date**: January 2026

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Overview](#2-system-overview)
3. [Project Structure](#3-project-structure)
4. [Installation & Setup](#4-installation--setup)
5. [Configuration Guide](#5-configuration-guide)
6. [Data Handling](#6-data-handling)
7. [Preprocessing Pipeline](#7-preprocessing-pipeline)
8. [Feature Engineering](#8-feature-engineering)
9. [Machine Learning Models](#9-machine-learning-models)
10. [Ensemble Logic](#10-ensemble-logic)
11. [Alerting System](#11-alerting-system)
12. [Interfaces](#12-interfaces)
13. [Testing & Validation](#13-testing--validation)
14. [Operational Notes](#14-operational-notes)
15. [Security & Design Guarantees](#15-security--design-guarantees)
16. [Phase-1 Conclusion](#16-phase-1-conclusion)

---

## 1. Introduction

### 1.1 Purpose of SOC Copilot

SOC Copilot is an offline, desktop-based Security Operations Center assistant that analyzes security logs using hybrid machine learning to detect anomalies and classify threats. It provides prioritized, explainable alerts with MITRE ATT&CK mapping to assist security analysts in threat triage.

### 1.2 Phase-1 Goals

Phase-1 implements a complete, functional end-to-end pipeline:

| Goal | Delivered |
|------|-----------|
| Parse multiple log formats | JSON, CSV, Syslog, EVTX |
| Preprocess and normalize data | Timestamp, field standardization, encoding |
| Extract ML-ready features | Statistical, temporal, behavioral, network |
| Detect anomalies | Isolation Forest (unsupervised) |
| Classify threats | Random Forest (supervised) |
| Generate prioritized alerts | P0-Critical to P4-Info |
| Provide explainable outputs | Reasoning, suggested actions, MITRE mapping |

### 1.3 Non-Goals (Explicitly Out of Scope)

- Real-time streaming analysis
- Web-based user interface
- Online learning or model retraining during runtime
- Cloud deployment or API endpoints
- Integration with external SIEM/SOAR platforms

### 1.4 Offline-First Design Rationale

SOC Copilot is designed for environments where:

1. **Air-gapped networks**: Security-sensitive environments may not have internet access
2. **Data privacy**: Sensitive log data should not leave the local system
3. **Reproducibility**: Deterministic, auditable analysis without external dependencies
4. **Portability**: Can run on any system with Python installed

All processing occurs locally. No network calls are made during analysis.

---

## 2. System Overview

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SOC COPILOT                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌─────────────────┐             │
│  │   Log    │──▶│ Preprocessing │──▶│    Feature      │             │
│  │ Ingestion│   │   Pipeline    │   │  Engineering    │             │
│  └──────────┘   └──────────────┘   └────────┬────────┘             │
│                                              │                      │
│                                              ▼                      │
│                              ┌───────────────────────────┐          │
│                              │      ML Inference         │          │
│                              │  ┌─────────┐ ┌─────────┐  │          │
│                              │  │Isolation│ │ Random  │  │          │
│                              │  │ Forest  │ │ Forest  │  │          │
│                              │  └────┬────┘ └────┬────┘  │          │
│                              └───────┼───────────┼───────┘          │
│                                      │           │                  │
│                                      ▼           ▼                  │
│                              ┌───────────────────────────┐          │
│                              │    Ensemble Coordinator   │          │
│                              │   (Decision Matrix)       │          │
│                              └────────────┬──────────────┘          │
│                                           │                         │
│                                           ▼                         │
│                              ┌───────────────────────────┐          │
│                              │    Alert Generator        │          │
│                              │  (MITRE ATT&CK Mapping)   │          │
│                              └───────────────────────────┘          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Interaction Summary

| Component | Input | Output | Responsibility |
|-----------|-------|--------|----------------|
| **Log Ingestion** | Raw log files | ParsedRecord objects | Detect format, parse, validate |
| **Preprocessing** | ParsedRecord DataFrame | Normalized DataFrame | Timestamp normalization, field standardization, encoding |
| **Feature Engineering** | Normalized DataFrame | Feature matrix (numeric) | Extract statistical, temporal, behavioral, network features |
| **Isolation Forest** | Feature matrix (benign only) | Anomaly scores [0,1] | Unsupervised anomaly detection |
| **Random Forest** | Feature matrix + labels | Class predictions + probabilities | Supervised multi-class classification |
| **Ensemble Coordinator** | Anomaly score + classification | Risk score + level | Combine signals, apply decision matrix |
| **Alert Generator** | Ensemble result | Structured Alert | Generate prioritized, explainable alerts |

### 2.3 End-to-End Data Flow

```
Log File (.jsonl, .csv, .log, .evtx)
         │
         ▼
    ┌─────────────────┐
    │  Parse Records  │  → Detect format, extract fields
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Normalize Timestamps │  → Convert to UTC ISO 8601
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Standardize Fields │  → Map to canonical names
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Encode Categoricals │  → Convert strings to integers
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Extract Features │  → 78 numeric features
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Anomaly Scoring │  → IF: normalized score [0,1]
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Classification  │  → RF: class + confidence
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Ensemble Scoring │  → Combined risk score
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Alert Generation │  → Priority, reasoning, MITRE
    └────────┬────────┘
             │
             ▼
       Alert Object
```

---

## 3. Project Structure

### 3.1 Complete Folder Structure

```
SOC Copilot/
├── config/                          # Configuration files
│   ├── features.yaml                # Feature extraction toggles
│   ├── thresholds.yaml              # Risk thresholds and weights
│   └── model_config.yaml            # Model hyperparameters
│
├── data/                            # Data directory (gitignored)
│   ├── datasets/                    # Training datasets
│   │   └── kaggle/                  # Kaggle security datasets
│   │       └── cicids2017/          # CICIDS2017 CSV files
│   └── models/                      # Trained model artifacts
│       ├── isolation_forest_v1.joblib
│       ├── random_forest_v1.joblib
│       ├── feature_order.json
│       └── label_map.json
│
├── models/                          # Training code (OFFLINE ONLY)
│   ├── isolation_forest/
│   │   └── trainer.py               # IF trainer class
│   └── random_forest/
│       └── trainer.py               # RF trainer class
│
├── scripts/                         # Utility scripts
│   └── train_models.py              # Manual training script
│
├── src/                             # Source code
│   └── soc_copilot/
│       ├── __init__.py              # Package exports
│       ├── pipeline.py              # End-to-end SOCCopilot class
│       ├── cli.py                   # Command-line interface
│       ├── core/                    # Core utilities
│       │   ├── base.py              # Base classes, ParsedRecord
│       │   ├── config.py            # Configuration loading
│       │   └── logging.py           # Structured logging
│       ├── data/
│       │   ├── log_ingestion/       # Parsers
│       │   │   ├── parsers/         # Format-specific parsers
│       │   │   ├── parser_factory.py
│       │   │   └── validators.py
│       │   ├── preprocessing/       # Data preprocessing
│       │   │   ├── timestamp_normalizer.py
│       │   │   ├── field_standardizer.py
│       │   │   ├── categorical_encoder.py
│       │   │   ├── missing_values.py
│       │   │   └── pipeline.py
│       │   └── feature_engineering/ # Feature extraction
│       │       ├── statistical_features.py
│       │       ├── temporal_features.py
│       │       ├── behavioral_features.py
│       │       ├── network_features.py
│       │       └── pipeline.py
│       └── models/
│           ├── training/            # Training data handling
│           │   └── data_loader.py   # Kaggle dataset loader
│           ├── inference/           # Runtime inference
│           │   └── engine.py        # Model loading and scoring
│           └── ensemble/            # Ensemble logic
│               ├── coordinator.py   # Decision matrix
│               ├── alert_generator.py
│               └── pipeline.py
│
├── tests/                           # Test suite
│   ├── unit/                        # Unit tests (192 tests)
│   ├── integration/                 # Integration tests (16 tests)
│   └── fixtures/                    # Test data
│
├── pyproject.toml                   # Project configuration
└── README.md                        # Project readme
```

### 3.2 Responsibility of Each Major Directory

| Directory | Responsibility |
|-----------|----------------|
| `config/` | YAML configuration files for feature toggles, thresholds, model params |
| `data/datasets/` | Training data (Kaggle CSVs) — excluded from Git |
| `data/models/` | Persisted model artifacts — versioned separately |
| `models/` | **Training code** — executed offline, manually |
| `scripts/` | Utility scripts for training, data prep |
| `src/soc_copilot/` | **Inference code** — runtime-safe, no training |
| `tests/` | Unit and integration tests |

### 3.3 Separation of Training vs Inference

**Critical Design Decision**: Training and inference code are strictly separated.

| Aspect | Training (`models/`) | Inference (`src/soc_copilot/models/`) |
|--------|---------------------|--------------------------------------|
| When executed | Offline, manually | Runtime, automatically |
| Data access | Full training datasets | Persisted model artifacts only |
| Model modification | Creates/updates models | Read-only |
| Dependencies | May use additional ML libs | Minimal, stable dependencies |

This separation ensures:
- No accidental model retraining during runtime
- Reproducible inference behavior
- Audit trail for model provenance

---

## 4. Installation & Setup

### 4.1 Environment Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ |
| Operating System | Windows, Linux, macOS |
| RAM | 8GB minimum, 16GB recommended |
| Disk | 2GB for models + dataset space |

### 4.2 Dependency Installation

```bash
# Clone repository
git clone <repository-url>
cd SOC-Copilot

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/macOS)
source venv/bin/activate

# Install dependencies
pip install -e .
```

### 4.3 Core Dependencies

```
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
pydantic>=2.0.0
structlog>=23.0.0
joblib>=1.3.0
pyyaml>=6.0
```

### 4.4 Project Initialization

```bash
# Verify installation
python -c "from soc_copilot import create_soc_copilot; print('OK')"

# Check model status
python -m soc_copilot.cli status --models-dir data/models

# Run tests
python -m pytest tests/ -v
```

### 4.5 Configuration Files Overview

| File | Purpose |
|------|---------|
| `config/thresholds.yaml` | Risk scoring weights and thresholds |
| `config/features.yaml` | Feature extraction toggles |
| `config/model_config.yaml` | Model hyperparameters |
| `pyproject.toml` | Project metadata, dependencies |

---

## 5. Configuration Guide

### 5.1 thresholds.yaml

Controls ensemble scoring and risk categorization:

```yaml
# Ensemble weights (must sum to 1.0)
ensemble:
  anomaly_weight: 0.4      # Weight for IF anomaly score
  classification_weight: 0.6  # Weight for RF classification

# Anomaly score thresholds
anomaly:
  low: 0.3
  medium: 0.5
  high: 0.7
  critical: 0.85

# Classification confidence thresholds
confidence:
  low: 0.5
  medium: 0.7
  high: 0.85
  min_required: 0.4       # Minimum to trust classification

# Combined risk score thresholds
risk:
  low: 0.25
  medium: 0.45
  high: 0.65
  critical: 0.80
```

**Impact**: Higher thresholds = fewer alerts (more conservative). Lower thresholds = more alerts (more sensitive).

### 5.2 features.yaml

Controls which feature extractors are enabled:

```yaml
extractors:
  statistical:
    enabled: true
    window_size: 100
    
  temporal:
    enabled: true
    cyclical_encoding: true
    
  behavioral:
    enabled: true
    session_timeout_minutes: 30
    
  network:
    enabled: true
    compute_graph_metrics: false  # Expensive, disabled by default
```

**Impact**: Disabling extractors reduces feature count and processing time but may reduce detection accuracy.

### 5.3 model_config.yaml

Model hyperparameters (used during training):

```yaml
isolation_forest:
  n_estimators: 100
  contamination: 0.01
  max_samples: auto
  random_state: 42

random_forest:
  n_estimators: 100
  max_depth: null
  class_weight: balanced
  random_state: 42
```

**Note**: These settings only affect training. Once models are trained, the artifacts contain the trained parameters.

### 5.4 How Configuration Affects Behavior

| Configuration | Affects | Changed At |
|---------------|---------|------------|
| `thresholds.yaml` | Risk scoring, alert generation | Runtime |
| `features.yaml` | Feature extraction | Runtime |
| `model_config.yaml` | Model training | Training time only |

---

## 6. Data Handling

### 6.1 Supported Log Formats

| Format | Extensions | Parser | Notes |
|--------|------------|--------|-------|
| JSON Lines | `.jsonl`, `.json` | JSONParser | One JSON object per line |
| CSV | `.csv`, `.tsv` | CSVParser | Header row required |
| Syslog | `.log`, `.syslog` | SyslogParser | RFC 3164 and RFC 5424 |
| Windows Events | `.evtx` | EVTXParser | Windows Event Log format |

### 6.2 Dataset Handling (Kaggle)

Training uses Kaggle security datasets:

| Dataset | Purpose | Size |
|---------|---------|------|
| CICIDS2017 | Primary training data | ~3.4GB |
| NSL-KDD | Alternative dataset | ~150MB |
| UNSW-NB15 | Alternative dataset | ~2GB |

**Directory Structure**:
```
data/datasets/kaggle/
├── cicids2017/
│   ├── Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv
│   ├── Monday-WorkingHours.pcap_ISCX.csv
│   └── ... (8 CSV files)
└── nsl-kdd/
    └── KDDTrain+.csv
```

### 6.3 Why Datasets Are Excluded from Git

1. **Size**: Datasets are too large (GBs) for version control
2. **Licensing**: Kaggle datasets have their own licenses
3. **Reproducibility**: Datasets can be independently downloaded
4. **Security**: Sensitive data should not be committed

The `.gitignore` includes:
```
data/datasets/
data/models/*.joblib
```

### 6.4 Expected Directory Layout

```
data/
├── datasets/
│   └── kaggle/
│       └── <dataset_name>/
│           └── *.csv
└── models/
    ├── isolation_forest_v1.joblib  # ~800KB
    ├── random_forest_v1.joblib     # ~6MB
    ├── feature_order.json          # ~2KB
    └── label_map.json              # ~2KB
```

---

## 7. Preprocessing Pipeline

### 7.1 Pipeline Steps (Execution Order)

```
Input DataFrame
      │
      ▼
┌─────────────────────┐
│ 1. Missing Values   │  Handle nulls, NaNs
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. Timestamp        │  Normalize to UTC ISO 8601
│    Normalization    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 3. Field            │  Map to canonical names
│    Standardization  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 4. Categorical      │  Encode strings to integers
│    Encoding         │
└──────────┬──────────┘
           │
           ▼
Preprocessed DataFrame
```

### 7.2 Detailed Step Explanations

#### Step 1: Missing Values Handler

| Strategy | Behavior |
|----------|----------|
| `drop` | Remove rows with missing values |
| `fill` | Replace with default value |
| `forward_fill` | Use previous row's value |
| `flag` | Add indicator column for missingness |

**Design Decision**: Default uses `fill` with zeros for numeric, empty string for text.

#### Step 2: Timestamp Normalizer

Converts various timestamp formats to UTC ISO 8601:

| Input Format | Example | Output |
|--------------|---------|--------|
| ISO 8601 | `2026-01-10T10:30:00Z` | `2026-01-10T10:30:00+00:00` |
| Unix epoch | `1736505000` | `2026-01-10T10:30:00+00:00` |
| Syslog | `Jan 10 10:30:00` | `2026-01-10T10:30:00+00:00` |
| Custom | `10/01/2026 10:30:00` | `2026-01-10T10:30:00+00:00` |

**Design Decision**: All timestamps are converted to UTC to ensure consistent temporal analysis regardless of log source timezone.

#### Step 3: Field Standardizer

Maps vendor-specific field names to canonical names:

| Source Field | Canonical Name |
|--------------|----------------|
| `source_ip`, `src`, `srcip` | `src_ip` |
| `destination_ip`, `dst`, `dstip` | `dst_ip` |
| `source_port`, `srcport` | `src_port` |
| `action`, `event_action` | `action` |

**Design Decision**: Canonical names follow lowercase_underscore convention for consistency.

#### Step 4: Categorical Encoder

Converts string values to integer codes:

```
action: "login" → 0
action: "logout" → 1
action: "failed_login" → 2
```

Features:
- Frequency-based filtering (rare values mapped to "OTHER")
- Unknown value handling (new values mapped to "UNKNOWN")
- Reversible encoding (can decode back to original)

### 7.3 Design Decisions and Impact

| Decision | Rationale | Impact |
|----------|-----------|--------|
| UTC normalization | Timezone-agnostic analysis | Consistent temporal features |
| Integer encoding | ML models require numeric input | All features become floats |
| Fill missing values | Maintain record count | May introduce bias if many missing |
| Canonical field names | Vendor-agnostic processing | Enables cross-log-source analysis |

---

## 8. Feature Engineering

### 8.1 Feature Categories

Phase-1 extracts 78 numeric features across 4 categories:

| Category | Count | Purpose |
|----------|-------|---------|
| Statistical | ~20 | Aggregate distributions |
| Temporal | ~15 | Time patterns |
| Behavioral | ~18 | Entity behavior patterns |
| Network | ~25 | Connection patterns |

### 8.2 Statistical Features

| Feature | Description |
|---------|-------------|
| `*_count` | Count of events per entity |
| `*_mean` | Average of numeric fields |
| `*_std` | Standard deviation |
| `*_min`, `*_max` | Range boundaries |
| `*_percentile_25`, `*_percentile_75` | Distribution quartiles |
| `*_entropy` | Entropy of categorical distributions |

### 8.3 Temporal Features

| Feature | Description |
|---------|-------------|
| `hour_sin`, `hour_cos` | Cyclical hour encoding |
| `day_of_week_sin`, `day_of_week_cos` | Cyclical day encoding |
| `time_since_last_event` | Delta from previous event |
| `events_per_hour` | Rate calculation |
| `is_business_hours` | Boolean (9 AM - 5 PM) |

**Cyclical Encoding**: Uses sin/cos transformation to preserve circular relationships (e.g., hour 23 is close to hour 0).

### 8.4 Behavioral Features

| Feature | Description |
|---------|-------------|
| `session_count` | Number of sessions per entity |
| `avg_session_duration` | Average session length |
| `unique_destinations` | Distinct destinations contacted |
| `deviation_from_baseline` | Z-score from historical behavior |
| `action_diversity` | Variety of actions performed |

### 8.5 Network Features

| Feature | Description |
|---------|-------------|
| `unique_dst_ips` | Distinct destination IPs |
| `unique_dst_ports` | Distinct destination ports |
| `port_diversity` | Entropy of port distribution |
| `private_ip_ratio` | Ratio of private to public IPs |
| `high_port_ratio` | Ratio of ports > 1024 |
| `connection_fanout` | Outbound connection count |

### 8.6 Why All Features Are Numeric

**Requirement**: scikit-learn models require numeric input.

**Solution**: All features are converted to floats through:
1. Categorical encoding (strings → integers)
2. Cyclical encoding (time → sin/cos)
3. Boolean conversion (True/False → 1.0/0.0)
4. Normalization (various ranges → standard scale)

### 8.7 Explainability Considerations

Each feature is:
- **Named descriptively**: `src_ip_unique_dst_count` not `feature_42`
- **Documented**: Feature definitions stored in metadata
- **Interpretable**: Security analyst can understand what the feature represents

### 8.8 Feature Order Persistence

**Critical**: Feature order must match between training and inference.

```json
// data/models/feature_order.json
{
  "feature_count": 78,
  "features": [
    "destination_port",
    "init_win_bytes_backward",
    "max_packet_length",
    ...
  ],
  "created_at": "2026-01-10T10:00:00Z"
}
```

During inference, features are reordered to match this exact sequence.

---

## 9. Machine Learning Models

### 9.1 Isolation Forest

**Purpose**: Unsupervised anomaly detection

| Aspect | Detail |
|--------|--------|
| Training data | Benign records only |
| Input | 78-dimensional feature vector |
| Output | Anomaly score [0, 1] |
| High score means | More anomalous |

**Training Logic**:
```python
# Filter to benign only
benign_mask = y_train == "Benign"
X_benign = X_train[benign_mask]

# Train on normal behavior
model.fit(X_benign)
```

**Scoring Logic**:
```python
# Raw score from sklearn (negative)
raw_score = model.decision_function(X)

# Normalize to [0, 1] where higher = more anomalous
normalized = (1 - (raw_score - min_score) / (max_score - min_score))
```

### 9.2 Random Forest

**Purpose**: Supervised multi-class classification

| Aspect | Detail |
|--------|--------|
| Training data | Full labeled dataset |
| Input | 78-dimensional feature vector |
| Output | Class label + probability distribution |
| Classes | Benign, DDoS, BruteForce, Malware, Exfiltration, Unknown |

**Class Imbalance Handling**:
```python
# Automatic class weighting
model = RandomForestClassifier(class_weight="balanced")
```

This adjusts for imbalanced datasets (e.g., 90% Benign, 10% attacks).

### 9.3 Training vs Inference Separation

| Aspect | Training | Inference |
|--------|----------|-----------|
| Code location | `models/*/trainer.py` | `src/soc_copilot/models/inference/` |
| Execution | Manual, offline | Automatic, runtime |
| Data access | Full datasets | Model artifacts only |
| Model state | Creates/modifies | Read-only |

### 9.4 Model Artifacts Produced

| File | Content | Size |
|------|---------|------|
| `isolation_forest_v1.joblib` | Trained IF model + scaler | ~800KB |
| `random_forest_v1.joblib` | Trained RF model + encoder | ~6MB |
| `feature_order.json` | Feature names in order | ~2KB |
| `label_map.json` | Label mappings | ~2KB |

---

## 10. Ensemble Logic

### 10.1 Decision Matrix

The ensemble coordinator combines IF and RF outputs using a decision matrix:

| Anomaly Score | Classification | Confidence | → Risk Level | → Priority |
|---------------|----------------|------------|--------------|------------|
| High (>0.7) | Malware/Exfil | High (>0.85) | **Critical** | P0 |
| High (>0.7) | Any Attack | High | High | P1 |
| High (>0.7) | Any Attack | Low | Medium | P2 |
| High (>0.7) | Benign | High | Medium | P3 |
| Med (0.5-0.7) | Malware/Exfil | High | High | P1 |
| Med (0.5-0.7) | Attack | High | Medium | P2 |
| Med (0.5-0.7) | Benign | Any | Low | P4 |
| Low (<0.5) | Attack | High | Medium | P3 |
| Low (<0.5) | Benign | High | **Low** | P4 |

### 10.2 Weighting Strategy

Combined risk score calculation:

```python
combined = (
    0.4 * anomaly_score +
    0.6 * (threat_severity * classification_confidence)
)
```

**Why 40/60 split?**
- Classification (RF) is trained on labeled data → more reliable
- Anomaly detection (IF) provides "second opinion" → catches unknowns

### 10.3 Risk Categorization

| Risk Level | Score Range | Description |
|------------|-------------|-------------|
| Low | < 0.25 | Normal operation |
| Medium | 0.25 - 0.45 | Warrants attention |
| High | 0.45 - 0.65 | Investigate promptly |
| Critical | ≥ 0.80 | Immediate response required |

### 10.4 Risk Adjustments

**Boost for severe threats**:
```python
if (classification in ["Malware", "Exfiltration"] 
    and anomaly_score >= 0.5):
    combined *= 1.2  # 20% boost
```

**Reduction for confident benign**:
```python
if (classification == "Benign" 
    and confidence >= 0.85 
    and anomaly_score < 0.5):
    combined *= 0.5  # 50% reduction
```

### 10.5 False-Positive Minimization Philosophy

Phase-1 prioritizes **precision over recall**:

1. **Conservative thresholds**: High bar for Critical/P0 alerts
2. **Confidence requirements**: Low-confidence classifications weighted down
3. **Benign suppression**: Confident benign with low anomaly is aggressively suppressed
4. **P0 restriction**: Only Critical risk generates P0 priority

**Rationale**: Alert fatigue is a major problem in SOCs. Fewer, higher-quality alerts are more actionable.

---

## 11. Alerting System

### 11.1 Alert Structure

```python
class Alert(BaseModel):
    # Identity
    alert_id: str           # UUID
    timestamp: str          # ISO 8601
    
    # Classification
    priority: AlertPriority # P0-P4
    risk_level: RiskLevel   # Low-Critical
    threat_category: ThreatCategory
    
    # Scores
    anomaly_score: float    # [0, 1]
    classification_confidence: float
    combined_risk_score: float
    
    # Context
    classification: str
    reasoning: list[str]    # Explainability
    suggested_action: str
    
    # MITRE ATT&CK
    mitre_tactics: list[str]
    mitre_techniques: list[str]
    
    # Source
    source_ip: str | None
    destination_ip: str | None
    source_port: int | None
    destination_port: int | None
    
    # Workflow
    status: AlertStatus     # New, Investigating, Resolved
```

### 11.2 Priority Levels

| Priority | Trigger | SLA Guidance |
|----------|---------|--------------|
| **P0-Critical** | Critical risk score | Immediate response |
| **P1-High** | High risk + severe threat | Within 1 hour |
| **P2-Medium** | High risk | Within 4 hours |
| **P3-Low** | Medium risk + confident | Within 24 hours |
| **P4-Info** | Low risk | Monitor, no action |

### 11.3 MITRE ATT&CK Mapping

| Threat Category | Tactics | Techniques |
|-----------------|---------|------------|
| DDoS | Impact | T1499 - Endpoint DoS |
| BruteForce | Credential Access, Initial Access | T1110 - Brute Force, T1078 - Valid Accounts |
| Malware | Execution, Persistence | T1059 - Command Scripting, T1547 - Boot Autostart |
| Exfiltration | Exfiltration, Collection | T1041 - Exfil Over C2, T1560 - Archive Data |

### 11.4 Explanation Generation

Each alert includes human-readable reasoning:

```python
reasoning = [
    "Classified as Malware with 92.5% confidence",
    "High anomaly score (0.85)",
    "Risk boosted: severe threat with anomalous behavior"
]

suggested_action = "Isolate endpoint and investigate"
```

---

## 12. Interfaces

### 12.1 CLI Usage

#### Commands

```bash
# Analyze a single file
python -m soc_copilot.cli analyze logs/access.jsonl

# Analyze a directory recursively
python -m soc_copilot.cli analyze logs/ --recursive

# Output as JSON
python -m soc_copilot.cli analyze logs/ --output-format json

# Filter by minimum priority
python -m soc_copilot.cli analyze logs/ --min-priority P2-Medium

# Save output to file
python -m soc_copilot.cli analyze logs/ --output-file report.txt

# Check pipeline status
python -m soc_copilot.cli status
```

#### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success, no high-priority alerts |
| 1 | High-priority alerts (P1) found |
| 2 | Critical alerts (P0) found |

### 12.2 Python API Usage

```python
from soc_copilot import create_soc_copilot

# Initialize and load models
copilot = create_soc_copilot("data/models")

# Analyze a single file
results, alerts, stats = copilot.analyze_file("logs/access.jsonl")

# Analyze a directory
results, alerts, stats = copilot.analyze_directory("logs/", recursive=True)

# Examine results
for result in results:
    print(f"Risk: {result.risk_level}")
    print(f"Class: {result.ensemble_result.classification}")
    print(f"Score: {result.ensemble_result.combined_risk_score:.2f}")

# Examine alerts
for alert in alerts:
    print(f"[{alert.priority.value}] {alert.threat_category.value}")
    print(f"  Reasoning: {alert.reasoning}")
    print(f"  Action: {alert.suggested_action}")

# Get statistics
print(f"Records analyzed: {stats.processed_records}")
print(f"Alerts generated: {stats.alerts_generated}")
print(f"Risk distribution: {stats.risk_distribution}")
```

### 12.3 Expected Outputs

#### CLI Text Output

```
╔══════════════════════════════════════════════════════════════╗
║ ALERT: P1-High - Malware
╟──────────────────────────────────────────────────────────────╢
║ ID: a1b2c3d4...
║ Time: 2026-01-10T11:00:00Z
║ Risk Level: High
║ Risk Score: 0.72
╟──────────────────────────────────────────────────────────────╢
║ Classification: Malware (92.5%)
║ Anomaly Score: 0.85
╟──────────────────────────────────────────────────────────────╢
║ Source: 192.168.1.100:45678
║ Destination: 10.0.0.5:22
╟──────────────────────────────────────────────────────────────╢
║ Reasoning:
║   • Classified as Malware with 92.5% confidence
║   • High anomaly score (0.85)
╟──────────────────────────────────────────────────────────────╢
║ Action: Isolate endpoint and investigate
╟──────────────────────────────────────────────────────────────╢
║ MITRE ATT&CK: T1059 - Command and Scripting
╚══════════════════════════════════════════════════════════════╝
```

#### JSON Output

```json
{
  "timestamp": "2026-01-10T12:00:00Z",
  "path": "logs/access.jsonl",
  "stats": {
    "total_records": 100,
    "processed_records": 100,
    "alerts_generated": 3,
    "risk_distribution": {
      "Low": 85,
      "Medium": 10,
      "High": 4,
      "Critical": 1
    }
  },
  "alerts": [
    {
      "alert_id": "a1b2c3d4-...",
      "priority": "P0-Critical",
      "risk_level": "Critical",
      "threat_category": "Malware",
      "classification": "Malware",
      "confidence": 0.95,
      "anomaly_score": 0.92,
      "risk_score": 0.88,
      "reasoning": ["..."],
      "suggested_action": "Immediate investigation required"
    }
  ]
}
```

---

## 13. Testing & Validation

### 13.1 Test Strategy

| Level | Purpose | Count |
|-------|---------|-------|
| **Unit Tests** | Individual component correctness | 192 |
| **Integration Tests** | End-to-end pipeline validation | 16 |
| **Total** | | **208** |

### 13.2 Test Categories

| Category | Tests | Coverage |
|----------|-------|----------|
| Log Parsers | 32 | JSON, CSV, Syslog, EVTX parsing |
| Validators | 25 | Schema validation |
| Preprocessing | 31 | Each preprocessor |
| Feature Engineering | 21 | Each feature extractor |
| ML Models | 21 | Trainers, inference |
| Ensemble | 26 | Coordinator, alerts |
| Integration | 16 | Full pipeline |
| Core | 36 | Config, base classes |

### 13.3 Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Unit tests only
python -m pytest tests/unit/ -v

# Integration tests only
python -m pytest tests/integration/ -v

# With coverage
python -m pytest tests/ --cov=soc_copilot
```

### 13.4 Exit Gates Used in Phase-1

| Gate | Requirement | Result |
|------|-------------|--------|
| IF trains successfully | Completes without error | ✅ |
| RF trains successfully | Completes without error | ✅ |
| RF test accuracy | > 80% | **99.99%** |
| IF score separation | Attack > Benign mean | 0.459 > 0.438 |
| Feature order consistent | 78 features persisted | ✅ |
| Models load correctly | No errors | ✅ |
| E2E pipeline works | Sample file analyzed | ✅ |
| All tests pass | 0 failures | 208 passed |

---

## 14. Operational Notes

### 14.1 Performance Expectations

| Operation | Time (approx) |
|-----------|---------------|
| Model loading | 1-2 seconds |
| Single record analysis | < 10ms |
| 1000 records batch | 2-5 seconds |
| 100,000 records | 2-5 minutes |

**Bottlenecks**:
1. Feature extraction (pandas operations)
2. Model inference (scales linearly with records)

### 14.2 Limitations of Phase-1

| Limitation | Description |
|------------|-------------|
| Batch only | No real-time streaming |
| Fixed models | No online learning |
| Single-host | No distributed processing |
| No GUI | CLI and Python API only |
| English only | No localization |

### 14.3 Known Assumptions

1. **Log format consistency**: Logs within a file follow consistent format
2. **Timestamp presence**: Records have parseable timestamps
3. **Network context**: IP addresses and ports available for network features
4. **Sufficient training data**: Models trained on representative data
5. **Feature availability**: Most features can be computed (missing handled gracefully)

---

## 15. Security & Design Guarantees

### 15.1 Determinism

**Guarantee**: Same input produces same output.

Implementation:
- Random seeds fixed in training (`random_state=42`)
- No stochastic operations during inference
- Hash-based ordering where needed

### 15.2 Auditability

**Guarantee**: All decisions are traceable.

Implementation:
- Alert `reasoning` field explains scoring
- Feature contributions logged
- Model versions tracked in artifacts
- Structured logging with timestamps

### 15.3 Offline Safety

**Guarantee**: No network access during analysis.

Implementation:
- No HTTP calls in inference code
- No external API dependencies
- All models loaded from local files
- Configuration files local only

### 15.4 Model Stability

**Guarantee**: Models do not change during runtime.

Implementation:
- Training code separate from inference
- Model files loaded read-only
- No fit/update operations in inference path
- Version numbers in artifact names

---

## 16. Phase-1 Conclusion

### 16.1 What Phase-1 Delivers

| Capability | Status |
|------------|--------|
| Multi-format log parsing | ✅ JSON, CSV, Syslog, EVTX |
| Data preprocessing | ✅ Normalize, standardize, encode |
| Feature engineering | ✅ 78 numeric features |
| Anomaly detection | ✅ Isolation Forest |
| Threat classification | ✅ Random Forest, 5+ classes |
| Ensemble scoring | ✅ Weighted, decision matrix |
| Prioritized alerts | ✅ P0-P4 with MITRE mapping |
| CLI interface | ✅ analyze, status commands |
| Python API | ✅ SOCCopilot class |
| Test coverage | ✅ 208 tests |

### 16.2 What Phase-1 Intentionally Does NOT Do

| Out of Scope | Reason |
|--------------|--------|
| Real-time streaming | Batch processing is sufficient for offline use |
| Web UI | CLI/API is sufficient for demo |
| Cloud deployment | Air-gap compatibility required |
| Online learning | Model stability more important |
| External SIEM integration | Standalone by design |

### 16.3 Readiness for Demo / Evaluation

**Phase-1 is complete and ready for:**

1. **Academic evaluation**: All code is documented, tested, and follows best practices
2. **Technical demonstration**: CLI provides immediate usability
3. **Security review**: Code is auditable, deterministic, offline-safe
4. **Future development**: Clean architecture supports extension

**To run a demo**:

```bash
# 1. Install
pip install -e .

# 2. Verify
python -m soc_copilot.cli status

# 3. Analyze sample data
python -m soc_copilot.cli analyze tests/fixtures/sample_threats.jsonl

# 4. Run tests
python -m pytest tests/ -v
```

---

**Document End**

*SOC Copilot Phase-1 Developer User Manual*  
*Version 1.0 — January 2026*
