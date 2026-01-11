# SOC Copilot — Project Documentation

**Version**: 2.0  
**Status**: Phase-1 + Phase-2 Complete, Phase-3 Infrastructure  
**Date**: January 2026

---

## Table of Contents

1. [Introduction & Problem Statement](#1-introduction--problem-statement)
2. [Objectives & Scope](#2-objectives--scope)
3. [System Classification](#3-system-classification)
4. [High-Level Architecture](#4-high-level-architecture)
5. [Phase-wise Breakdown](#5-phase-wise-breakdown)
6. [Data Flow](#6-data-flow)
7. [Machine Learning Design](#7-machine-learning-design)
8. [Explainability Strategy](#8-explainability-strategy)
9. [Governance & Safety Design](#9-governance--safety-design)
10. [Security & Risk Mitigation](#10-security--risk-mitigation)
11. [Testing Strategy](#11-testing-strategy)
12. [Limitations](#12-limitations)
13. [Future Enhancements](#13-future-enhancements)
14. [Conclusion](#14-conclusion)

---

## 1. Introduction & Problem Statement

### 1.1 Context

Security Operations Centers (SOCs) face an overwhelming volume of security logs from diverse sources—firewalls, intrusion detection systems, endpoint agents, and application logs. Analysts must manually review thousands of alerts daily, leading to:

- **Alert fatigue**: High-volume, low-quality alerts desensitize analysts
- **Missed threats**: Genuine attacks buried in noise go undetected
- **Delayed response**: Manual triage increases mean time to detect (MTTD)
- **Inconsistent decisions**: Human judgment varies across analysts and shifts

### 1.2 Problem Statement

> How can we assist SOC analysts in identifying genuine security threats from large volumes of heterogeneous log data while ensuring the system remains explainable, auditable, and operates entirely offline without automatic learning?

### 1.3 Solution Overview

**SOC Copilot** is an offline, desktop-based Security Operations Center assistant that:

- Ingests security logs from multiple formats (JSON, CSV, Syslog, EVTX)
- Applies hybrid machine learning for threat detection
- Generates prioritized, explainable alerts with MITRE ATT&CK mapping
- Maintains complete analyst oversight through manual controls
- Enforces governance constraints that prevent unsupervised automation

### 1.4 Key Differentiators

| Feature | SOC Copilot | Traditional SIEM |
|---------|-------------|------------------|
| Deployment | Fully offline | Cloud/on-premise |
| Learning | No automatic learning | Often auto-trains |
| Explainability | Built-in reasoning | Limited/opaque |
| Governance | Disabled-by-default automation | Often auto-enabled |
| Analyst Control | Mandatory human-in-loop | Optional oversight |

---

## 2. Objectives & Scope

### 2.1 Primary Objectives

| Objective | Description |
|-----------|-------------|
| **Threat Detection** | Identify malicious activity using hybrid ML (unsupervised + supervised) |
| **Alert Prioritization** | Generate P0-P4 priority alerts to focus analyst attention |
| **Explainability** | Provide human-readable reasoning for every decision |
| **Offline Operation** | Operate without network connectivity or cloud dependencies |
| **Governance-First** | Ensure all automation is disabled by default with manual controls |

### 2.2 Scope Boundaries

#### In Scope

- Multi-format log ingestion (JSON, CSV, Syslog, Windows EVTX)
- Batch analysis of historical logs
- Hybrid ML detection pipeline
- CLI-based user interface
- Analyst feedback collection
- Model drift monitoring
- Manual threshold calibration
- Governance infrastructure (disabled by default)

#### Out of Scope

- Real-time streaming analysis
- Web-based user interface
- Cloud deployment
- Automatic model retraining
- Integration with external SIEM/SOAR platforms
- Multi-tenant operation

### 2.3 Design Constraints

| Constraint | Rationale |
|------------|-----------|
| Fully offline | Air-gap compatibility for sensitive environments |
| No cloud dependencies | Data privacy and sovereignty requirements |
| No automatic learning | Prevent model drift without analyst oversight |
| Analyst-in-the-loop | Human judgment required for all critical decisions |
| Governance-first design | All automation disabled until explicitly approved |

---

## 3. System Classification

### 3.1 Why This Is a Software Application (Not a Web App)

SOC Copilot is classified as a **desktop CLI application**, not a web application, because:

| Characteristic | SOC Copilot | Web Application |
|----------------|-------------|-----------------|
| **Deployment** | Local installation via pip | Server + client architecture |
| **Network** | No network required | Requires HTTP/WebSocket |
| **Interface** | Command-line + Python API | Browser-based UI |
| **Data Storage** | Local SQLite + files | Remote database |
| **Execution** | Runs in user's Python environment | Runs on web server |
| **Authentication** | OS-level user identity | Session-based auth |

### 3.2 Technical Classification

- **Type**: Desktop application with CLI interface
- **Runtime**: Python 3.10+ interpreter
- **Distribution**: Python package (pip installable)
- **Platform**: Cross-platform (Windows, Linux, macOS)
- **Architecture**: Monolithic, single-process

### 3.3 Target Environments

| Environment | Suitability |
|-------------|-------------|
| Air-gapped networks | ✅ Excellent |
| Developer workstations | ✅ Excellent |
| Security lab environments | ✅ Excellent |
| SOC analyst workstations | ✅ Excellent |
| Cloud VMs | ⚠️ Possible but not designed for |
| Containers | ⚠️ Possible but loses persistence |

---

## 4. High-Level Architecture

### 4.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SOC COPILOT                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                     PHASE-1: DETECTION ENGINE (Frozen)              │    │
│  │  ┌──────────┐   ┌──────────────┐   ┌─────────────────┐             │    │
│  │  │   Log    │──▶│ Preprocessing │──▶│    Feature      │             │    │
│  │  │ Ingestion│   │   Pipeline    │   │  Engineering    │             │    │
│  │  └──────────┘   └──────────────┘   └────────┬────────┘             │    │
│  │                                              │                      │    │
│  │                                              ▼                      │    │
│  │                              ┌───────────────────────────┐          │    │
│  │                              │      ML Inference         │          │    │
│  │                              │  ┌─────────┐ ┌─────────┐  │          │    │
│  │                              │  │Isolation│ │ Random  │  │          │    │
│  │                              │  │ Forest  │ │ Forest  │  │          │    │
│  │                              │  └────┬────┘ └────┬────┘  │          │    │
│  │                              └───────┼───────────┼───────┘          │    │
│  │                                      ▼           ▼                  │    │
│  │                              ┌───────────────────────────┐          │    │
│  │                              │    Ensemble Coordinator   │          │    │
│  │                              │      + Alert Generator    │          │    │
│  │                              └───────────────────────────┘          │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                              │                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                    PHASE-2: TRUST & INTELLIGENCE (Frozen)           │    │
│  │                                                                     │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │    │
│  │  │   Feedback   │  │     Drift    │  │  Calibration │              │    │
│  │  │    Store     │  │   Monitoring │  │  Recommender │              │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │    │
│  │                                                                     │    │
│  │  ┌───────────────────────────────────────────────────────────┐     │    │
│  │  │                    Explainability Layer                     │     │    │
│  │  │        (Wrapper-based feature importance analysis)          │     │    │
│  │  └───────────────────────────────────────────────────────────┘     │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │               PHASE-3: GOVERNANCE INFRASTRUCTURE                    │    │
│  │                        (Disabled by Default)                        │    │
│  │                                                                     │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │    │
│  │  │  Governance  │  │   Approval   │  │  Kill Switch │              │    │
│  │  │    Policy    │  │   Workflow   │  │   (Global)   │              │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │    │
│  │                                                                     │    │
│  │  ┌──────────────┐  ┌──────────────┐                                │    │
│  │  │ Audit Logger │  │  Override/   │                                │    │
│  │  │ (Append-Only)│  │  Rollback    │                                │    │
│  │  └──────────────┘  └──────────────┘                                │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Component Interaction Summary

| Component | Input | Output | Responsibility |
|-----------|-------|--------|----------------|
| **Log Ingestion** | Raw log files | ParsedRecord objects | Detect format, parse, validate |
| **Preprocessing** | ParsedRecord DataFrame | Normalized DataFrame | Timestamp normalization, field standardization |
| **Feature Engineering** | Normalized DataFrame | Feature matrix (numeric) | Extract 78 statistical, temporal, behavioral, network features |
| **Isolation Forest** | Feature matrix | Anomaly scores [0,1] | Unsupervised anomaly detection |
| **Random Forest** | Feature matrix + labels | Class predictions + probabilities | Supervised multi-class classification |
| **Ensemble Coordinator** | Both model outputs | Risk score + level | Combine signals, apply decision matrix |
| **Alert Generator** | Ensemble result | Structured Alert | Generate prioritized, explainable alerts |
| **Feedback Store** | Analyst verdicts | Persisted feedback | Store analyst corrections for analysis |
| **Drift Monitor** | Feature distributions | Drift reports | Detect distribution shifts |
| **Explainability** | Model outputs | Feature importance | Generate human-readable explanations |
| **Governance** | Admin actions | Audit trail | Control system authority states |

---

## 5. Phase-wise Breakdown

### 5.1 Phase-1: Detection Engine

**Status**: ✅ Complete and Frozen

Phase-1 implements the core detection pipeline:

| Component | Description |
|-----------|-------------|
| **Log Parsers** | JSON, CSV, Syslog, EVTX format support |
| **Validators** | Schema and field validation |
| **Preprocessors** | Timestamp normalization, field standardization, categorical encoding |
| **Feature Extractors** | 78 numeric features across 4 categories |
| **ML Models** | Isolation Forest + Random Forest |
| **Ensemble Logic** | Weighted combination with decision matrix |
| **Alert Generation** | Priority assignment (P0-P4) with MITRE mapping |

**Key Design Decisions**:
- Training code separate from inference code
- Models loaded read-only at runtime
- Deterministic scoring (fixed random seeds)
- No online learning or model updates

### 5.2 Phase-2: Trust & Intelligence

**Status**: ✅ Complete and Frozen

Phase-2 adds intelligence and adaptability:

| Module | Purpose |
|--------|---------|
| **Feedback Store** | SQLite-based persistence of analyst verdicts |
| **Drift Monitoring** | Track feature distribution changes over time |
| **Threshold Calibration** | Environment-specific tuning recommendations |
| **Explainability** | Wrapper-based feature importance analysis |

**Key Design Decisions**:
- Phase-2 does NOT modify Phase-1 behavior
- Feedback is stored but not used for automatic learning
- Calibration provides recommendations only (manual approval required)
- Explainability is post-hoc analysis, not model introspection

### 5.3 Phase-3: Governance Infrastructure

**Status**: ✅ Infrastructure Complete, Disabled by Default

Phase-3 provides governance and control:

| Component | Purpose |
|-----------|---------|
| **Governance Policy** | Authority states (DISABLED, OBSERVE_ONLY, ADVISORY_ONLY) |
| **Approval Workflow** | Manual request/approve/reject state machine |
| **Kill Switch** | Global disable flag with highest priority |
| **Audit Logger** | Append-only record of all governance actions |
| **Override/Rollback** | Framework shells (no execution logic) |

**Key Design Decisions**:
- All authority states default to DISABLED
- Kill switch is enabled by default (Phase-3 disabled)
- No automatic transitions or side effects
- Separate database from Phase-1/Phase-2
- No imports from Phase-1 or Phase-2

---

## 6. Data Flow

### 6.1 End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        LOG FILE INPUT                                    │
│            (.jsonl, .csv, .log, .evtx)                                  │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE-1: DETECTION PIPELINE                                            │
├─────────────────────────────────────────────────────────────────────────┤
│  1. Parse Records    → Detect format, extract fields                    │
│  2. Validate         → Schema and field validation                      │
│  3. Normalize        → Timestamp to UTC ISO 8601                        │
│  4. Standardize      → Map to canonical field names                     │
│  5. Encode           → Convert categoricals to integers                 │
│  6. Extract Features → 78 numeric features                              │
│  7. Anomaly Score    → Isolation Forest: [0, 1]                        │
│  8. Classification   → Random Forest: class + confidence               │
│  9. Ensemble Score   → Weighted combination                            │
│  10. Generate Alert  → Priority, reasoning, MITRE mapping              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ALERT OUTPUT                                                            │
│  • Priority: P0-Critical to P4-Info                                     │
│  • Risk Level: Critical/High/Medium/Low                                 │
│  • Classification: DDoS, BruteForce, Malware, Exfiltration, etc.       │
│  • Reasoning: Human-readable explanation                                │
│  • Suggested Action: Recommended response                               │
│  • MITRE ATT&CK: Tactics and techniques                                │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE-2: ANALYST INTERACTION                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  • Analyst reviews alert                                                │
│  • Analyst provides feedback (confirm/dispute)                          │
│  • Feedback stored in SQLite database                                   │
│  • Drift reports generated periodically                                 │
│  • Calibration recommendations provided                                 │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE-3: GOVERNANCE (Disabled by Default)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  • All actions require manual CLI commands                              │
│  • All state changes recorded in audit log                              │
│  • Kill switch can halt all Phase-3 operations                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Feedback Loop (Manual Only)

```
         ┌──────────────────────────────────────────┐
         │           Alert Generated                │
         └─────────────────┬────────────────────────┘
                           │
                           ▼
         ┌──────────────────────────────────────────┐
         │      Analyst Reviews Alert               │
         └─────────────────┬────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
    ┌─────────────────┐       ┌─────────────────┐
    │    Confirm      │       │    Dispute      │
    │ (True Positive) │       │ (False Positive)│
    └────────┬────────┘       └────────┬────────┘
              │                         │
              └────────────┬────────────┘
                           │
                           ▼
         ┌──────────────────────────────────────────┐
         │      Feedback Stored (SQLite)            │
         │      (NO automatic model update)         │
         └─────────────────┬────────────────────────┘
                           │
                           ▼
         ┌──────────────────────────────────────────┐
         │   Drift Monitor Analyzes Feedback        │
         │   Calibrator Provides Recommendations    │
         └─────────────────┬────────────────────────┘
                           │
                           ▼
         ┌──────────────────────────────────────────┐
         │   Manual Approval Required for Changes   │
         └──────────────────────────────────────────┘
```

---

## 7. Machine Learning Design

### 7.1 Hybrid Approach Rationale

SOC Copilot uses a **hybrid ML approach** combining:

| Model | Type | Purpose | Training Data |
|-------|------|---------|---------------|
| **Isolation Forest** | Unsupervised | Anomaly detection | Benign records only |
| **Random Forest** | Supervised | Attack classification | Labeled dataset |

**Why Hybrid?**

1. **Unknown threats**: Isolation Forest can detect novel attacks not in training data
2. **Known threats**: Random Forest accurately classifies known attack patterns
3. **Confidence**: Two independent signals provide higher confidence
4. **Robustness**: If one model fails, the other provides backup

### 7.2 Isolation Forest Role

**Purpose**: Detect anomalous behavior that deviates from normal patterns.

| Aspect | Detail |
|--------|--------|
| **Training Data** | Benign (normal) records only |
| **Algorithm** | Scikit-learn IsolationForest |
| **Parameters** | n_estimators=100, contamination=0.1, random_state=42 |
| **Output** | Anomaly score normalized to [0, 1] |
| **Interpretation** | Higher score = more anomalous |

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

### 7.3 Random Forest Role

**Purpose**: Classify records into known threat categories.

| Aspect | Detail |
|--------|--------|
| **Training Data** | Full labeled dataset |
| **Algorithm** | Scikit-learn RandomForestClassifier |
| **Parameters** | n_estimators=100, class_weight=balanced, random_state=42 |
| **Output** | Class label + probability distribution |
| **Classes** | Benign, DDoS, BruteForce, Malware, Exfiltration, Reconnaissance, Injection |

**Class Imbalance Handling**:
```python
# Automatic class weighting
model = RandomForestClassifier(class_weight="balanced")
```

### 7.4 Ensemble Logic

The ensemble coordinator combines both model outputs using a decision matrix:

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

**Combined Risk Score Calculation**:
```python
combined = (
    0.4 * anomaly_score +
    0.6 * (threat_severity * classification_confidence)
)
```

### 7.5 Training vs Inference Separation

| Aspect | Training | Inference |
|--------|----------|-----------|
| **Code Location** | `models/*/trainer.py` | `src/soc_copilot/models/inference/` |
| **Execution** | Manual, offline | Automatic, runtime |
| **Data Access** | Full datasets | Model artifacts only |
| **Model State** | Creates/modifies | Read-only |
| **Reproducibility** | Fixed random seeds | Deterministic |

---

## 8. Explainability Strategy

### 8.1 Approach

SOC Copilot uses **wrapper-based explainability**, providing explanations without modifying the underlying models:

| Approach | Description |
|----------|-------------|
| **Feature Importance** | Which features contributed most to the decision |
| **Score Breakdown** | How anomaly and classification scores combined |
| **Threshold Analysis** | Which thresholds were crossed |
| **Reasoning Generation** | Human-readable explanation text |

### 8.2 Explanation Components

Each alert includes:

```python
{
    "reasoning": [
        "Classified as Malware with 92.5% confidence",
        "High anomaly score (0.85) indicates unusual behavior",
        "Top contributing features: port_entropy (0.15), unique_destinations (0.12)",
        "Risk boosted: severe threat with anomalous behavior"
    ],
    "suggested_action": "Isolate endpoint and investigate process execution",
    "feature_importance": {
        "port_entropy": 0.15,
        "unique_destinations": 0.12,
        "time_since_last": 0.09,
        ...
    }
}
```

### 8.3 Design Decisions

| Decision | Rationale |
|----------|-----------|
| Wrapper-based, not intrinsic | Avoids modifying frozen Phase-1 models |
| Post-hoc analysis | Explanations generated after inference |
| Human-readable | SOC analysts need actionable insights |
| Feature-level granularity | Shows which log attributes triggered alert |

---

## 9. Governance & Safety Design

### 9.1 Governance Philosophy

SOC Copilot follows a **governance-first design** where:

1. **All automation is disabled by default**
2. **Manual approval is required for any state changes**
3. **Kill switch has highest priority**
4. **All actions are recorded in append-only audit log**

### 9.2 Authority States

| State | Description | Permitted Components |
|-------|-------------|---------------------|
| **DISABLED** (default) | No automation permitted | None |
| **OBSERVE_ONLY** | Monitoring only | Logging, monitoring |
| **ADVISORY_ONLY** | Recommendations without action | Logging, monitoring, recommendations |

> [!IMPORTANT]
> The system ships with authority state set to **DISABLED**. Changing this requires explicit CLI commands and is recorded in the audit log.

### 9.3 Kill Switch

The global kill switch:

- **Default state**: Enabled (Phase-3 disabled)
- **Priority**: Highest (overrides all other permissions)
- **Persistence**: Survives application restarts
- **Control**: CLI-only (no automatic triggering)

```bash
# Enable kill switch (disable Phase-3)
python -m soc_copilot.cli governance disable --actor admin --reason "Emergency"

# Disable kill switch (enable Phase-3)
python -m soc_copilot.cli governance enable --actor admin --reason "Authorized"
```

### 9.4 Approval Workflow

```
         ┌──────────────────────┐
         │      REQUESTED       │
         │   (Analyst submits)  │
         └───────────┬──────────┘
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│ APPROVED │  │ REJECTED │  │ REVOKED  │
│(Manager) │  │(Manager) │  │(Manager) │
└──────────┘  └──────────┘  └──────────┘
```

> [!CAUTION]
> Approval does NOT automatically activate anything. Manual implementation is required after approval.

### 9.5 Audit Logging

All governance actions are recorded:

| Field | Description |
|-------|-------------|
| event_id | Unique identifier (UUID) |
| timestamp | ISO 8601 timestamp |
| actor | Who performed the action |
| action | What action was performed |
| reason | Why the action was taken |

The audit log is **append-only**—no deletion or modification is permitted.

---

## 10. Security & Risk Mitigation

### 10.1 Security Guarantees

| Guarantee | Implementation |
|-----------|----------------|
| **Offline Operation** | No network calls during analysis |
| **Data Privacy** | All processing local, no data exfiltration |
| **Model Stability** | Read-only model loading, no runtime updates |
| **Determinism** | Fixed random seeds, reproducible results |
| **Auditability** | Structured logging, append-only audit trail |

### 10.2 Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Model drift | Drift monitoring with manual alerts |
| False positives | Conservative thresholds, analyst feedback |
| False negatives | Dual-model ensemble, anomaly detection backup |
| Unauthorized changes | Governance layer with kill switch |
| Alert fatigue | Priority levels, deduplication, analyst control |

### 10.3 Data Handling

| Data Type | Handling |
|-----------|----------|
| Log files | Processed in memory, not persisted beyond analysis |
| Model artifacts | Loaded read-only from local files |
| Feedback data | Stored in local SQLite database |
| Governance data | Separate SQLite database with audit trail |
| Configuration | YAML files, version-controlled |

---

## 11. Testing Strategy

### 11.1 Test Pyramid

| Level | Count | Purpose |
|-------|-------|---------|
| **Unit Tests** | 192+ | Individual component correctness |
| **Integration Tests** | 16+ | End-to-end pipeline validation |
| **Total** | 208+ | Comprehensive coverage |

### 11.2 Test Categories

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
| Governance | 50+ | Sprint-13 governance layer |

### 11.3 Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Unit tests only
python -m pytest tests/unit/ -v

# Integration tests only
python -m pytest tests/integration/ -v

# With coverage
python -m pytest tests/ --cov=soc_copilot

# Governance tests only
python -m pytest tests/unit/test_governance_sprint13.py -v
```

### 11.4 Exit Gates

| Gate | Requirement | Result |
|------|-------------|--------|
| IF trains successfully | Completes without error | ✅ |
| RF trains successfully | Completes without error | ✅ |
| RF test accuracy | > 80% | 99.99% |
| IF score separation | Attack > Benign mean | ✅ |
| Feature order consistent | 78 features persisted | ✅ |
| Models load correctly | No errors | ✅ |
| E2E pipeline works | Sample file analyzed | ✅ |
| All tests pass | 0 failures | 208+ passed |
| Governance default DISABLED | Verified | ✅ |

---

## 12. Limitations

### 12.1 Known Limitations

| Limitation | Description | Impact |
|------------|-------------|--------|
| Batch processing only | No real-time streaming | Cannot analyze live traffic |
| Fixed models | No online learning | Must retrain offline for new threats |
| Single-host | No distributed processing | Limited by single machine resources |
| CLI-only | No graphical interface | Learning curve for non-technical users |
| English only | No localization | International users may face challenges |

### 12.2 Performance Constraints

| Metric | Typical Value |
|--------|---------------|
| Model loading | 1-2 seconds |
| Single record analysis | < 10ms |
| 1000 records batch | 2-5 seconds |
| 100,000 records | 2-5 minutes |

### 12.3 Assumptions

1. **Log format consistency**: Logs within a file follow consistent format
2. **Timestamp presence**: Records have parseable timestamps
3. **Network context**: IP addresses and ports available for network features
4. **Sufficient training data**: Models trained on representative data
5. **Feature availability**: Most features can be computed

---

## 13. Future Enhancements

### 13.1 Potential Phase-4+ Features

| Enhancement | Description | Status |
|-------------|-------------|--------|
| Autoencoder integration | Additional anomaly detection signal | Framework exists |
| Transformer models | Improved sequence understanding | Not planned |
| Web interface | Browser-based dashboard | Out of scope |
| Real-time streaming | Live log analysis | Out of scope |
| SIEM integration | Export to external systems | Out of scope |

### 13.2 Governance Evolution

Future governance enhancements may include:

- Override/rollback execution logic (currently framework shells only)
- Authority state transitions (currently static)
- Integration with Phase-1/Phase-2 (currently isolated)

> [!WARNING]
> All future governance changes require separate approval and must maintain the governance-first design philosophy.

---

## 14. Conclusion

### 14.1 Summary

SOC Copilot is a **fully offline, governance-first security analysis application** that:

- Ingests security logs from multiple formats
- Applies hybrid ML for threat detection
- Generates prioritized, explainable alerts
- Maintains complete analyst oversight
- Enforces disabled-by-default automation

### 14.2 Key Achievements

| Capability | Status |
|------------|--------|
| Multi-format log parsing | ✅ JSON, CSV, Syslog, EVTX |
| Hybrid ML detection | ✅ Isolation Forest + Random Forest |
| Prioritized alerting | ✅ P0-P4 with MITRE mapping |
| Explainability | ✅ Feature importance, reasoning |
| Analyst feedback | ✅ SQLite persistence |
| Drift monitoring | ✅ Distribution tracking |
| Governance infrastructure | ✅ Disabled by default |
| Test coverage | ✅ 208+ tests |

### 14.3 Design Philosophy

SOC Copilot embodies three core principles:

1. **Analyst-in-the-loop**: Human judgment is required for all critical decisions
2. **Offline-first**: No network dependencies or cloud requirements
3. **Governance-first**: All automation disabled by default with manual controls

---

**Document End**

*SOC Copilot Project Documentation*  
*Version 2.0 — January 2026*
