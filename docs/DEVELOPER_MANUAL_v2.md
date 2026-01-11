# SOC Copilot — Developer Manual

**Version**: 2.0  
**For**: Future Developers & Contributors  
**Date**: January 2026

---

## Table of Contents

1. [Developer Overview](#1-developer-overview)
2. [Codebase Structure](#2-codebase-structure)
3. [Phase-1 Internals](#3-phase-1-internals)
4. [Phase-2 Modules Explained](#4-phase-2-modules-explained)
5. [Phase-3 Governance Layer](#5-phase-3-governance-layer)
6. [Design Patterns Used](#6-design-patterns-used)
7. [Database Schemas](#7-database-schemas)
8. [Configuration Files](#8-configuration-files)
9. [Testing Strategy](#9-testing-strategy)
10. [Adding New Features Safely](#10-adding-new-features-safely)
11. [Rules for Modifying Phases](#11-rules-for-modifying-phases)
12. [Governance Rules](#12-governance-rules)
13. [How to Extend the System](#13-how-to-extend-the-system)
14. [Do's and Don'ts](#14-dos-and-donts)
15. [Contribution Guidelines](#15-contribution-guidelines)

---

## 1. Developer Overview

### 1.1 Project Philosophy

SOC Copilot is built on three core principles:

| Principle | Description |
|-----------|-------------|
| **Analyst-in-the-loop** | Human judgment required for all critical decisions |
| **Offline-first** | No network dependencies or cloud requirements |
| **Governance-first** | All automation disabled by default with manual controls |

### 1.2 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SOC COPILOT                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PHASE-1: Detection Engine (Frozen)                                         │
│    ├── Log Ingestion (parsers, validators)                                 │
│    ├── Preprocessing (normalization, encoding)                             │
│    ├── Feature Engineering (78 features)                                   │
│    ├── ML Inference (Isolation Forest + Random Forest)                     │
│    └── Alert Generation (ensemble, MITRE mapping)                          │
│                                                                             │
│  PHASE-2: Trust & Intelligence (Frozen)                                     │
│    ├── Feedback Store (SQLite persistence)                                 │
│    ├── Drift Monitoring (distribution tracking)                            │
│    ├── Calibration (threshold recommendations)                             │
│    └── Explainability (feature importance)                                 │
│                                                                             │
│  PHASE-3: Governance Infrastructure (Disabled by Default)                   │
│    ├── Governance Policy (authority states)                                │
│    ├── Approval Workflow (manual state machine)                            │
│    ├── Kill Switch (global disable)                                        │
│    └── Audit Logger (append-only)                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| ML Framework | scikit-learn |
| Data Processing | pandas, numpy |
| Validation | pydantic |
| Database | SQLite |
| Configuration | YAML |
| Testing | pytest |
| Logging | structlog |

### 1.4 Development Environment Setup

```bash
# Clone repository
git clone <repository-url>
cd SOC-Copilot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install with development dependencies
pip install -e ".[dev]"

# Verify installation
python -c "from soc_copilot import create_soc_copilot; print('OK')"

# Run tests
python -m pytest tests/ -v
```

---

## 2. Codebase Structure

### 2.1 Complete Directory Structure

```
SOC Copilot/
├── config/                          # Configuration files
│   ├── features.yaml                # Feature extraction settings
│   ├── thresholds.yaml              # Alert thresholds
│   ├── model_config.yaml            # Model hyperparameters
│   └── governance/
│       └── policy.yaml              # Governance policy
│
├── data/                            # Data directory (gitignored)
│   ├── datasets/                    # Training datasets
│   │   └── kaggle/cicids2017/       # CICIDS2017 CSV files
│   ├── models/                      # Trained model artifacts
│   │   ├── isolation_forest_v1.joblib
│   │   ├── random_forest_v1.joblib
│   │   ├── feature_order.json
│   │   └── label_map.json
│   └── governance/
│       └── governance.db            # Governance SQLite database
│
├── docs/                            # Documentation
│   ├── PROJECT_DOCUMENTATION.md     # Architecture & design
│   ├── USER_MANUAL.md               # For SOC analysts
│   ├── DEVELOPER_MANUAL.md          # This file
│   └── SPRINT*_SUMMARY.md           # Sprint summaries
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
├── src/soc_copilot/                 # Main source code
│   ├── __init__.py                  # Package exports
│   ├── cli.py                       # CLI (903 lines)
│   ├── main.py                      # Entry point
│   ├── pipeline.py                  # SOCCopilot class
│   │
│   ├── core/                        # Core utilities
│   │   ├── base.py                  # Base classes, ParsedRecord
│   │   ├── config.py                # Configuration loading
│   │   └── logging.py               # Structured logging
│   │
│   ├── data/                        # Data layer
│   │   ├── log_ingestion/           # Log parsers
│   │   │   ├── parsers/             # Format-specific parsers
│   │   │   ├── parser_factory.py    # Parser selection
│   │   │   └── validators.py        # Schema validation
│   │   ├── preprocessing/           # Data preprocessing
│   │   │   ├── timestamp_normalizer.py
│   │   │   ├── field_standardizer.py
│   │   │   ├── categorical_encoder.py
│   │   │   ├── missing_values.py
│   │   │   └── pipeline.py
│   │   └── feature_engineering/     # Feature extraction
│   │       ├── statistical_features.py
│   │       ├── temporal_features.py
│   │       ├── behavioral_features.py
│   │       ├── network_features.py
│   │       └── pipeline.py
│   │
│   ├── models/                      # ML inference
│   │   ├── training/
│   │   │   └── data_loader.py       # Dataset loading
│   │   ├── inference/
│   │   │   └── engine.py            # Model loading & scoring
│   │   └── ensemble/
│   │       ├── coordinator.py       # Decision matrix
│   │       ├── alert_generator.py   # Alert creation
│   │       └── pipeline.py          # Ensemble pipeline
│   │
│   ├── intelligence/                # Intelligence layer
│   │   ├── alert_engine.py          # Alert processing
│   │   └── context_enrichment.py    # Context addition
│   │
│   ├── phase2/                      # Phase-2 modules
│   │   ├── __init__.py              # Exports
│   │   ├── feedback/                # Analyst feedback
│   │   │   ├── store.py             # FeedbackStore
│   │   │   ├── models.py            # Data models
│   │   │   └── stats.py             # Statistics
│   │   ├── drift/                   # Drift monitoring
│   │   │   ├── monitor.py           # DriftMonitor
│   │   │   └── report.py            # DriftReport
│   │   ├── calibration/             # Threshold calibration
│   │   │   ├── recommender.py       # ThresholdCalibrator
│   │   │   └── models.py            # CalibrationRecommendation
│   │   └── explainability/          # Explainability
│   │       ├── explainer.py         # AlertExplainer
│   │       └── models.py            # ExplainedAlert
│   │
│   ├── phase3/                      # Phase-3 governance
│   │   ├── __init__.py              # Exports
│   │   └── governance/
│   │       ├── policy.py            # GovernancePolicy
│   │       ├── approval.py          # ApprovalWorkflow
│   │       ├── killswitch.py        # KillSwitch
│   │       ├── audit.py             # AuditLogger
│   │       └── override.py          # Framework shells
│   │
│   └── ui/                          # Presentation layer
│       └── (minimal, CLI-focused)
│
├── tests/                           # Test suite
│   ├── __init__.py
│   ├── fixtures/                    # Test data
│   ├── unit/                        # Unit tests (192+)
│   └── integration/                 # Integration tests (16+)
│
├── pyproject.toml                   # Project configuration
├── README.md                        # Project readme
└── .gitignore                       # Git exclusions
```

### 2.2 Key Module Responsibilities

| Module | Location | Responsibility |
|--------|----------|----------------|
| **Log Ingestion** | `data/log_ingestion/` | Parse raw logs, validate schema |
| **Preprocessing** | `data/preprocessing/` | Normalize, standardize, encode |
| **Feature Engineering** | `data/feature_engineering/` | Extract 78 numeric features |
| **ML Inference** | `models/inference/` | Load models, score records |
| **Ensemble** | `models/ensemble/` | Combine scores, generate alerts |
| **Feedback** | `phase2/feedback/` | Store analyst verdicts |
| **Drift** | `phase2/drift/` | Monitor distribution changes |
| **Calibration** | `phase2/calibration/` | Recommend threshold adjustments |
| **Governance** | `phase3/governance/` | Manage authority states |

---

## 3. Phase-1 Internals

### 3.1 Log Ingestion

**Location**: `src/soc_copilot/data/log_ingestion/`

#### Parser Architecture

```
ParserFactory
    │
    ├── JSONParser     (.jsonl, .json)
    ├── CSVParser      (.csv, .tsv)
    ├── SyslogParser   (.log, .syslog)
    └── EVTXParser     (.evtx)
```

**Parser Interface**:
```python
class BaseParser(ABC):
    @abstractmethod
    def can_parse(self, path: Path) -> bool:
        """Check if this parser can handle the file."""
        pass
    
    @abstractmethod
    def parse(self, path: Path) -> list[ParsedRecord]:
        """Parse file and return records."""
        pass
```

**ParsedRecord Structure**:
```python
class ParsedRecord(BaseModel):
    timestamp: datetime
    source_ip: str | None = None
    destination_ip: str | None = None
    source_port: int | None = None
    destination_port: int | None = None
    protocol: str | None = None
    action: str | None = None
    user: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
```

### 3.2 Preprocessing Pipeline

**Location**: `src/soc_copilot/data/preprocessing/`

**Pipeline Stages**:
```
Input DataFrame
      │
      ▼
MissingValuesHandler (fill/drop/flag)
      │
      ▼
TimestampNormalizer (→ UTC ISO 8601)
      │
      ▼
FieldStandardizer (→ canonical names)
      │
      ▼
CategoricalEncoder (→ integers)
      │
      ▼
Preprocessed DataFrame
```

**Key Design Decisions**:
- All timestamps converted to UTC for consistent temporal analysis
- Field names mapped to lowercase_underscore convention
- Missing values filled with defaults (not dropped) to maintain record count
- Categorical encoding is reversible

### 3.3 Feature Engineering

**Location**: `src/soc_copilot/data/feature_engineering/`

**Feature Categories**:

| Category | Class | Features | Example |
|----------|-------|----------|---------|
| Statistical | `StatisticalExtractor` | ~20 | event_count, unique_destinations |
| Temporal | `TemporalExtractor` | ~15 | hour_sin, hour_cos, day_of_week |
| Behavioral | `BehavioralExtractor` | ~18 | session_duration, deviation_from_baseline |
| Network | `NetworkExtractor` | ~25 | port_entropy, ip_rarity_score |

**Feature Order Persistence**:
```python
# data/models/feature_order.json
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

> [!IMPORTANT]
> Feature order must exactly match between training and inference. The `feature_order.json` file is the source of truth.

### 3.4 ML Inference

**Location**: `src/soc_copilot/models/inference/`

#### Isolation Forest Scoring

```python
def score_anomaly(self, features: np.ndarray) -> float:
    """Score a record for anomaly (0-1, higher = more anomalous)."""
    # Raw sklearn score (negative)
    raw_score = self.model.decision_function(features.reshape(1, -1))[0]
    
    # Normalize to [0, 1]
    normalized = (1 - (raw_score - self.min_score) / 
                  (self.max_score - self.min_score))
    
    return np.clip(normalized, 0.0, 1.0)
```

#### Random Forest Classification

```python
def classify(self, features: np.ndarray) -> tuple[str, float]:
    """Classify a record and return (class, confidence)."""
    probas = self.model.predict_proba(features.reshape(1, -1))[0]
    class_idx = np.argmax(probas)
    
    return self.label_map[class_idx], probas[class_idx]
```

### 3.5 Ensemble Coordinator

**Location**: `src/soc_copilot/models/ensemble/coordinator.py`

**Decision Matrix Implementation**:
```python
def compute_risk_score(
    self,
    anomaly_score: float,
    classification: str,
    confidence: float
) -> tuple[float, RiskLevel]:
    """Compute combined risk score using decision matrix."""
    
    # Base calculation
    threat_severity = self.get_threat_severity(classification)
    combined = (
        self.weights["anomaly"] * anomaly_score +
        self.weights["classification"] * (threat_severity * confidence)
    )
    
    # Boost for severe threats with anomalous behavior
    if (classification in ["Malware", "Exfiltration"] 
        and anomaly_score >= 0.5):
        combined *= 1.2
    
    # Reduction for confident benign
    if (classification == "Benign" 
        and confidence >= 0.85 
        and anomaly_score < 0.5):
        combined *= 0.5
    
    return np.clip(combined, 0.0, 1.0), self.score_to_level(combined)
```

---

## 4. Phase-2 Modules Explained

### 4.1 Feedback Store

**Location**: `src/soc_copilot/phase2/feedback/`

**Purpose**: Persist analyst verdicts for analysis and calibration.

**Key Classes**:
```python
class FeedbackEntry(BaseModel):
    feedback_id: str
    alert_id: str
    verdict: Literal["true_positive", "false_positive", 
                     "true_negative", "false_negative"]
    analyst: str
    notes: str | None = None
    created_at: datetime

class FeedbackStore:
    def add(self, entry: FeedbackEntry) -> None: ...
    def get(self, feedback_id: str) -> FeedbackEntry | None: ...
    def list(self, limit: int = 100) -> list[FeedbackEntry]: ...
    def get_stats(self) -> FeedbackStats: ...
    def export_json(self, path: Path) -> None: ...
    def import_json(self, path: Path) -> int: ...
```

**Database Table**:
```sql
CREATE TABLE feedback (
    feedback_id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    analyst TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);
```

> [!NOTE]
> Feedback is stored but NOT automatically used for model retraining. This is intentional—model updates require manual offline retraining.

### 4.2 Drift Monitoring

**Location**: `src/soc_copilot/phase2/drift/`

**Purpose**: Detect distribution changes in features over time.

**Key Classes**:
```python
class DriftLevel(Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"

class DriftReport(BaseModel):
    report_id: str
    generated_at: datetime
    period_days: int
    overall_level: DriftLevel
    feature_drift: dict[str, float]
    recommendations: list[str]

class DriftMonitor:
    def analyze(self, days: int = 30) -> DriftReport: ...
    def compare_periods(
        self, 
        period1: tuple[datetime, datetime],
        period2: tuple[datetime, datetime]
    ) -> DriftReport: ...
```

### 4.3 Threshold Calibration

**Location**: `src/soc_copilot/phase2/calibration/`

**Purpose**: Generate environment-specific threshold recommendations.

**Key Classes**:
```python
class CalibrationRecommendation(BaseModel):
    parameter: str
    current_value: float
    recommended_value: float
    reason: str
    expected_impact: dict[str, float]

class ThresholdCalibrator:
    def analyze_current(self) -> dict[str, Any]: ...
    def recommend(
        self, 
        based_on: Literal["feedback", "drift", "performance"]
    ) -> list[CalibrationRecommendation]: ...
```

> [!CAUTION]
> Calibration recommendations require manual approval before application. The system does NOT automatically adjust thresholds.

### 4.4 Explainability

**Location**: `src/soc_copilot/phase2/explainability/`

**Purpose**: Generate human-readable explanations for alerts.

**Key Classes**:
```python
class AlertExplanation(BaseModel):
    reasoning: list[str]
    feature_importance: dict[str, float]
    score_breakdown: dict[str, float]
    suggested_action: str

class ExplainedAlert(BaseModel):
    alert: Alert
    explanation: AlertExplanation

class AlertExplainer:
    def explain(self, alert: Alert, features: np.ndarray) -> ExplainedAlert: ...
```

**Explanation Generation**:
```python
def explain(self, alert: Alert, features: np.ndarray) -> ExplainedAlert:
    reasoning = []
    
    # Classification reasoning
    reasoning.append(
        f"Classified as {alert.classification} "
        f"with {alert.classification_confidence:.1%} confidence"
    )
    
    # Anomaly reasoning
    if alert.anomaly_score >= 0.7:
        reasoning.append(
            f"High anomaly score ({alert.anomaly_score:.2f}) "
            "indicates unusual behavior"
        )
    
    # Feature importance (permutation-based)
    importance = self._compute_feature_importance(features)
    top_features = self._get_top_features(importance, n=3)
    reasoning.append(
        f"Top contributing features: {', '.join(top_features)}"
    )
    
    return ExplainedAlert(
        alert=alert,
        explanation=AlertExplanation(
            reasoning=reasoning,
            feature_importance=importance,
            ...
        )
    )
```

---

## 5. Phase-3 Governance Layer

### 5.1 Overview

**Location**: `src/soc_copilot/phase3/governance/`

**Purpose**: Provide governance infrastructure for controlling system authority.

> [!WARNING]
> Phase-3 is **disabled by default**. All authority states default to DISABLED, and the kill switch is enabled (Phase-3 disabled).

### 5.2 Authority States

**Location**: `phase3/governance/policy.py`

```python
class AuthorityState(Enum):
    DISABLED = "disabled"        # No automation (DEFAULT)
    OBSERVE_ONLY = "observe_only"  # Logging only
    ADVISORY_ONLY = "advisory_only"  # Recommendations only

class GovernancePolicy:
    def __init__(self, config_path: str = "config/governance/policy.yaml"):
        self.config = yaml.safe_load(Path(config_path).read_text())
        self.current_state = AuthorityState.DISABLED  # ALWAYS default
    
    def get_permitted_components(self) -> list[str]:
        """Get components permitted in current state."""
        return self.config["permitted_components"].get(
            self.current_state.value, []
        )
```

### 5.3 Approval Workflow

**Location**: `phase3/governance/approval.py`

**State Machine**:
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
└──────────┘  └──────────┘  └──────────┘
```

**Key Classes**:
```python
class ApprovalState(Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"

class ApprovalRequest(BaseModel):
    request_id: str
    requester: str
    action: str
    reason: str
    state: ApprovalState
    requested_at: datetime
    reviewed_at: datetime | None = None
    reviewer: str | None = None
    review_notes: str | None = None

class ApprovalWorkflow:
    def create_request(self, ...) -> ApprovalRequest: ...
    def approve_request(self, request_id: str, ...) -> ApprovalRequest: ...
    def reject_request(self, request_id: str, ...) -> ApprovalRequest: ...
    def revoke_request(self, request_id: str, ...) -> ApprovalRequest: ...
```

> [!IMPORTANT]
> Approval does NOT automatically activate anything. Manual implementation is required after approval.

### 5.4 Kill Switch

**Location**: `phase3/governance/killswitch.py`

**Purpose**: Global override that disables all Phase-3 functionality.

```python
class KillSwitch:
    def __init__(self, db_path: str = "data/governance/governance.db"):
        self.db_path = db_path
        self._init_db()
    
    def enable(self, actor: str, reason: str) -> None:
        """Enable kill switch (disable Phase-3)."""
        ...
    
    def disable(self, actor: str, reason: str) -> None:
        """Disable kill switch (enable Phase-3)."""
        ...
    
    def is_enabled(self) -> bool:
        """Check if kill switch is enabled."""
        # Default: True (Phase-3 disabled)
        ...
    
    def get_state(self) -> dict[str, Any]:
        """Get current kill switch state."""
        ...
```

**Database Schema**:
```sql
CREATE TABLE killswitch_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled BOOLEAN NOT NULL DEFAULT 1,  -- Enabled by default!
    last_changed TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    reason TEXT
);
```

### 5.5 Audit Logger

**Location**: `phase3/governance/audit.py`

**Purpose**: Append-only record of all governance actions.

```python
class AuditEvent(BaseModel):
    event_id: str
    timestamp: datetime
    actor: str
    action: str
    reason: str

class AuditLogger:
    def log_event(self, actor: str, action: str, reason: str) -> AuditEvent: ...
    def get_events(self, limit: int = 100) -> list[AuditEvent]: ...
```

**Database Schema**:
```sql
CREATE TABLE audit_log (
    event_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL
);
-- NO DELETE or UPDATE operations permitted
```

### 5.6 Override/Rollback Frameworks

**Location**: `phase3/governance/override.py`

**Status**: Framework shells only—NO execution logic implemented.

```python
class OverrideAction(ABC):
    """Abstract base class for override actions."""
    @abstractmethod
    def execute(self) -> None:
        pass

class RollbackAction(ABC):
    """Abstract base class for rollback actions."""
    @abstractmethod
    def execute(self) -> None:
        pass

class OverrideManager:
    """Placeholder - no execution logic."""
    pass

class RollbackManager:
    """Placeholder - no execution logic."""
    pass
```

---

## 6. Design Patterns Used

### 6.1 Factory Pattern

**Used in**: Log parser selection

```python
class ParserFactory:
    _parsers: list[type[BaseParser]] = [
        JSONParser, CSVParser, SyslogParser, EVTXParser
    ]
    
    @classmethod
    def get_parser(cls, path: Path) -> BaseParser:
        for parser_class in cls._parsers:
            parser = parser_class()
            if parser.can_parse(path):
                return parser
        raise ValueError(f"No parser found for {path}")
```

### 6.2 Pipeline Pattern

**Used in**: Preprocessing, feature extraction

```python
class PreprocessingPipeline:
    def __init__(self):
        self.stages = [
            MissingValuesHandler(),
            TimestampNormalizer(),
            FieldStandardizer(),
            CategoricalEncoder(),
        ]
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        for stage in self.stages:
            df = stage.transform(df)
        return df
```

### 6.3 Strategy Pattern

**Used in**: Ensemble scoring strategies

```python
class ScoringStrategy(ABC):
    @abstractmethod
    def score(self, anomaly: float, classification: str, confidence: float) -> float:
        pass

class DefaultScoringStrategy(ScoringStrategy):
    def score(self, ...):
        return 0.4 * anomaly + 0.6 * (severity * confidence)

class ConservativeScoringStrategy(ScoringStrategy):
    def score(self, ...):
        # More conservative scoring
        ...
```

### 6.4 Repository Pattern

**Used in**: Feedback store, audit logger

```python
class FeedbackRepository:
    def add(self, entry: FeedbackEntry) -> None: ...
    def get(self, id: str) -> FeedbackEntry | None: ...
    def list(self, ...) -> list[FeedbackEntry]: ...
    def delete(self, id: str) -> bool: ...  # NOT in AuditLogger!
```

### 6.5 State Machine Pattern

**Used in**: Approval workflow

```python
class ApprovalStateMachine:
    TRANSITIONS = {
        ApprovalState.REQUESTED: [
            ApprovalState.APPROVED,
            ApprovalState.REJECTED
        ],
        ApprovalState.APPROVED: [
            ApprovalState.REVOKED
        ],
        # No transitions from REJECTED or REVOKED
    }
    
    def can_transition(self, from_state: ApprovalState, to_state: ApprovalState) -> bool:
        return to_state in self.TRANSITIONS.get(from_state, [])
```

---

## 7. Database Schemas

### 7.1 Phase-2 Database (Feedback)

**Location**: Managed by FeedbackStore

```sql
-- Feedback entries
CREATE TABLE feedback (
    feedback_id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (
        verdict IN ('true_positive', 'false_positive', 
                    'true_negative', 'false_negative')
    ),
    analyst TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_feedback_alert_id ON feedback(alert_id);
CREATE INDEX idx_feedback_analyst ON feedback(analyst);
CREATE INDEX idx_feedback_verdict ON feedback(verdict);
```

### 7.2 Phase-3 Database (Governance)

**Location**: `data/governance/governance.db`

```sql
-- Kill Switch (single row)
CREATE TABLE killswitch_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled BOOLEAN NOT NULL DEFAULT 1,
    last_changed TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    reason TEXT
);

-- Approval Requests
CREATE TABLE approval_requests (
    request_id TEXT PRIMARY KEY,
    requester TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('requested', 'approved', 'rejected', 'revoked')
    ),
    requested_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewer TEXT,
    review_notes TEXT
);

CREATE INDEX idx_approval_state ON approval_requests(state);

-- Audit Log (append-only)
CREATE TABLE audit_log (
    event_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL
);

CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);

-- Rotation Tracking
CREATE TABLE audit_rotation (
    rotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rotated_at TEXT NOT NULL,
    event_count INTEGER NOT NULL
);
```

### 7.3 Database Isolation

| Database | Phase | Location | Operations |
|----------|-------|----------|------------|
| Feedback | Phase-2 | In-memory or `data/feedback.db` | CRUD |
| Governance | Phase-3 | `data/governance/governance.db` | Insert, Read only (audit) |

> [!NOTE]
> Phase-3 database is completely isolated from Phase-1 and Phase-2. No cross-database queries.

---

## 8. Configuration Files

### 8.1 thresholds.yaml

**Location**: `config/thresholds.yaml`

```yaml
# Anomaly score thresholds
anomaly:
  low_threshold: 0.3
  high_threshold: 0.7

# Priority weights (must sum to 1.0)
weights:
  isolation_forest: 0.4
  random_forest: 0.4
  context: 0.2

# Classification confidence
classification:
  min_confidence: 0.7
  unknown_threshold: 0.3

# Alert priority thresholds
priority:
  critical: 0.85
  high: 0.70
  medium: 0.50
  low: 0.30

# Deduplication
deduplication:
  window_seconds: 300
  group_by:
    - src_ip
    - dst_ip
    - attack_class

# Conservative mode
conservative_mode:
  enabled: true
  min_signals: 2
  never_suppress_high_anomaly: true
```

### 8.2 features.yaml

**Location**: `config/features.yaml`

```yaml
settings:
  default_window: 300
  entity_types:
    - user
    - src_ip
    - dst_ip
    - host

statistical:
  enabled: true
  features:
    - name: event_count
      description: Number of events per entity
      aggregation: count
    ...

temporal:
  enabled: true
  features:
    - name: hour_of_day
      description: Hour when event occurred
      type: extract
      component: hour
    ...

behavioral:
  enabled: true
  features:
    - name: session_duration
      description: Duration of session
      type: duration
    ...

network:
  enabled: true
  features:
    - name: ip_rarity_score
      description: How rare is this IP
      type: rarity
      field: src_ip
      lookback: 604800
    ...
```

### 8.3 model_config.yaml

**Location**: `config/model_config.yaml`

```yaml
isolation_forest:
  n_estimators: 100
  max_samples: "auto"
  contamination: 0.1
  random_state: 42
  
  training:
    min_samples: 1000
    baseline_days: 7
  
  inference:
    batch_size: 1000

random_forest:
  n_estimators: 100
  max_depth: 20
  class_weight: "balanced"
  random_state: 42
  n_jobs: -1
  
  classes:
    - Benign
    - DDoS
    - BruteForce
    - Malware
    - Exfiltration
    - Reconnaissance
    - Injection

ensemble:
  load_on_startup: true
  parallel_inference: true
  timeout_seconds: 30
  fusion:
    if_weight: 0.4
    rf_weight: 0.4
    context_weight: 0.2

autoencoder:
  enabled: false  # Future Phase-2+
```

### 8.4 policy.yaml (Governance)

**Location**: `config/governance/policy.yaml`

```yaml
# Default authority state (MUST be disabled)
default_state: disabled

# Permitted components per state
permitted_components:
  disabled: []
  observe_only:
    - logging
    - monitoring
  advisory_only:
    - logging
    - monitoring
    - recommendations

# Safety constraints
safety:
  enforce_disabled_default: true
  require_manual_approval: true
  killswitch_priority: highest
```

---

## 9. Testing Strategy

### 9.1 Test Structure

```
tests/
├── __init__.py
├── fixtures/                    # Test data
│   ├── sample_logs.json
│   ├── sample_threats.jsonl
│   ├── sample_benign.csv
│   └── sample_evtx.evtx
├── unit/                        # Unit tests
│   ├── test_parsers.py
│   ├── test_validators.py
│   ├── test_preprocessing.py
│   ├── test_features.py
│   ├── test_inference.py
│   ├── test_ensemble.py
│   ├── test_feedback.py
│   ├── test_drift.py
│   ├── test_calibration.py
│   ├── test_explainability.py
│   └── test_governance_sprint13.py
└── integration/                 # Integration tests
    ├── test_pipeline.py
    ├── test_cli.py
    └── test_e2e.py
```

### 9.2 Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Unit tests only
python -m pytest tests/unit/ -v

# Integration tests only
python -m pytest tests/integration/ -v

# Specific test file
python -m pytest tests/unit/test_governance_sprint13.py -v

# With coverage
python -m pytest tests/ --cov=soc_copilot --cov-report=html

# Run in parallel
python -m pytest tests/ -n auto
```

### 9.3 Test Categories

| Category | Tests | Focus |
|----------|-------|-------|
| Parsers | 32 | Format detection, field extraction |
| Validators | 25 | Schema validation, error handling |
| Preprocessing | 31 | Each pipeline stage |
| Features | 21 | Each feature extractor |
| Models | 21 | Loading, scoring, classification |
| Ensemble | 26 | Decision matrix, alerts |
| Feedback | 15 | CRUD operations, stats |
| Drift | 10 | Distribution analysis |
| Calibration | 10 | Recommendations |
| Governance | 50+ | All Phase-3 components |
| Integration | 16 | End-to-end flows |

### 9.4 Test Fixtures

**Sample Threat Log** (`tests/fixtures/sample_threats.jsonl`):
```json
{"timestamp": "2026-01-10T10:00:00Z", "src_ip": "192.168.1.100", "dst_ip": "10.0.0.5", "dst_port": 22, "action": "connection", "bytes": 50000}
{"timestamp": "2026-01-10T10:00:01Z", "src_ip": "192.168.1.100", "dst_ip": "10.0.0.6", "dst_port": 22, "action": "connection", "bytes": 50000}
```

### 9.5 Key Test Assertions

**Phase-1 Determinism**:
```python
def test_deterministic_scoring():
    """Same input always produces same output."""
    result1 = copilot.analyze_file("tests/fixtures/sample.jsonl")
    result2 = copilot.analyze_file("tests/fixtures/sample.jsonl")
    
    assert result1.alerts == result2.alerts
    assert result1.stats == result2.stats
```

**Governance Default State**:
```python
def test_governance_default_disabled():
    """Authority state must default to DISABLED."""
    policy = GovernancePolicy()
    assert policy.current_state == AuthorityState.DISABLED
    
    killswitch = KillSwitch("test.db")
    assert killswitch.is_enabled() == True  # Kill switch ON = Phase-3 OFF
```

---

## 10. Adding New Features Safely

### 10.1 Feature Addition Workflow

```
1. Create feature branch
       │
       ▼
2. Write tests FIRST (TDD)
       │
       ▼
3. Implement feature
       │
       ▼
4. Verify Phase-1/2 unchanged
       │
       ▼
5. Update documentation
       │
       ▼
6. Run full test suite
       │
       ▼
7. Code review
       │
       ▼
8. Merge to main
```

### 10.2 Safe Addition Patterns

**New Parser**:
```python
# 1. Create parser in data/log_ingestion/parsers/
class NewFormatParser(BaseParser):
    def can_parse(self, path: Path) -> bool:
        return path.suffix == ".newformat"
    
    def parse(self, path: Path) -> list[ParsedRecord]:
        # Implementation
        pass

# 2. Register in ParserFactory
ParserFactory._parsers.append(NewFormatParser)

# 3. Add tests in tests/unit/test_parsers.py
def test_newformat_parser():
    ...
```

**New Feature Extractor**:
```python
# 1. Create extractor in data/feature_engineering/
class NewFeatureExtractor:
    def extract(self, df: pd.DataFrame) -> dict[str, float]:
        # Return dict of feature_name -> value
        pass

# 2. Add to FeatureEngineeringPipeline
# 3. Update feature_order.json
# 4. RETRAIN MODELS (offline)
```

> [!CAUTION]
> Adding new features requires model retraining. This is an offline operation that must be done manually.

### 10.3 Safety Checks

Before merging any feature:

```bash
# 1. All tests pass
python -m pytest tests/ -v

# 2. No Phase-1 modifications
git diff main -- src/soc_copilot/data/ src/soc_copilot/models/

# 3. No Phase-2 modifications
git diff main -- src/soc_copilot/phase2/

# 4. Governance still defaults to DISABLED
python -c "
from soc_copilot.phase3.governance import GovernancePolicy
assert GovernancePolicy().current_state.value == 'disabled'
print('✓ Governance defaults verified')
"
```

---

## 11. Rules for Modifying Phases

### 11.1 Phase-1 Rules (Detection Engine)

| Rule | Rationale |
|------|-----------|
| ❌ No modifications | Phase-1 is frozen and production-stable |
| ❌ No new imports | Maintain isolation |
| ❌ No training code in inference path | Prevent accidental model updates |
| ✅ Bug fixes allowed | With extensive testing and review |

### 11.2 Phase-2 Rules (Trust & Intelligence)

| Rule | Rationale |
|------|-----------|
| ❌ No automatic learning | Analyst-in-the-loop required |
| ❌ No Phase-1 modifications | Additive only |
| ❌ No automatic threshold changes | Manual approval required |
| ✅ New modules allowed | If they follow additive pattern |

### 11.3 Phase-3 Rules (Governance)

| Rule | Rationale |
|------|-----------|
| ✅ Default must be DISABLED | Safety-first design |
| ✅ Kill switch priority highest | Emergency override capability |
| ❌ No Phase-1/2 imports | Complete isolation |
| ❌ No automatic authority promotion | Manual-only transitions |
| ✅ Append-only audit | No modification or deletion |

---

## 12. Governance Rules

### 12.1 Authority Transition Rules

```python
ALLOWED_TRANSITIONS = {
    # Can only go from DISABLED to other states with approval
    AuthorityState.DISABLED: [
        AuthorityState.OBSERVE_ONLY,
        AuthorityState.ADVISORY_ONLY,
    ],
    # Can escalate or return to DISABLED
    AuthorityState.OBSERVE_ONLY: [
        AuthorityState.ADVISORY_ONLY,
        AuthorityState.DISABLED,
    ],
    # Can only return to DISABLED or lower
    AuthorityState.ADVISORY_ONLY: [
        AuthorityState.OBSERVE_ONLY,
        AuthorityState.DISABLED,
    ],
}
```

### 12.2 Kill Switch Behavior

| Kill Switch | Phase-3 Status | Effect |
|-------------|----------------|--------|
| **ENABLED** (default) | DISABLED | No Phase-3 operations permitted |
| DISABLED | ENABLED | Phase-3 operates per authority state |

### 12.3 Audit Requirements

All governance actions MUST be audited:

| Action | Logged Fields |
|--------|---------------|
| Kill switch toggle | actor, reason, new_state |
| Approval request | requester, action, reason |
| Approval decision | reviewer, decision, notes |
| Authority change | actor, from_state, to_state, reason |

---

## 13. How to Extend the System

### 13.1 Adding a New CLI Command

```python
# In cli.py, add to setup_parser()
def setup_parser():
    ...
    
    # Add new command
    new_parser = subparsers.add_parser(
        "newcommand",
        help="Description of new command"
    )
    new_parser.add_argument("--option", help="...")
    new_parser.set_defaults(func=cmd_newcommand)

# Implement command handler
def cmd_newcommand(args):
    """Handle new command."""
    # Implementation
    pass
```

### 13.2 Adding a New Phase-2 Module

```python
# 1. Create module directory
# src/soc_copilot/phase2/newmodule/
#   ├── __init__.py
#   ├── core.py
#   └── models.py

# 2. Export from phase2/__init__.py
from soc_copilot.phase2.newmodule import NewModuleClass

# 3. Add CLI integration if needed
# 4. Add tests in tests/unit/test_newmodule.py
```

### 13.3 Adding New Threat Category

```python
# 1. Update config/model_config.yaml
random_forest:
  classes:
    - ...existing...
    - NewThreatCategory

# 2. Update MITRE mapping in alert_generator.py
MITRE_MAPPING = {
    ...
    "NewThreatCategory": {
        "tactics": ["TacticX"],
        "techniques": ["TXXXX"]
    }
}

# 3. RETRAIN Random Forest (offline)
# 4. Update label_map.json
```

---

## 14. Do's and Don'ts

### 14.1 DO

✅ **Write tests first** (TDD approach)
✅ **Document all changes** in docstrings and markdown
✅ **Use type hints** throughout
✅ **Follow existing patterns** for consistency
✅ **Run full test suite** before committing
✅ **Keep modules focused** (single responsibility)
✅ **Use configuration files** for adjustable parameters
✅ **Log important operations** with structlog
✅ **Validate inputs** with pydantic

### 14.2 DON'T

❌ **Modify Phase-1** (it's frozen)
❌ **Add network calls** in inference path
❌ **Enable automatic learning** without explicit approval
❌ **Change default governance state** from DISABLED
❌ **Delete audit log entries** (append-only)
❌ **Import Phase-1/2 in Phase-3** (isolation required)
❌ **Use magic numbers** (always use configuration)
❌ **Commit secrets or credentials** (use environment variables)
❌ **Skip code review** for governance changes

---

## 15. Contribution Guidelines

### 15.1 Branch Naming

```
feature/add-new-parser
bugfix/fix-timestamp-parsing
docs/update-developer-manual
refactor/cleanup-ensemble-code
```

### 15.2 Commit Message Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**: feat, fix, docs, refactor, test, chore

**Examples**:
```
feat(parser): add CEF log format support
fix(ensemble): correct risk score calculation for edge case
docs(developer): add Phase-3 governance section
```

### 15.3 Pull Request Checklist

- [ ] Tests pass locally (`python -m pytest tests/ -v`)
- [ ] Coverage maintained or improved
- [ ] Documentation updated
- [ ] No Phase-1 modifications (unless bug fix)
- [ ] Governance defaults verified (DISABLED)
- [ ] Type hints added for new code
- [ ] Linting passes (`ruff check src/`)

### 15.4 Code Review Requirements

| Change Type | Required Reviewers |
|-------------|-------------------|
| Phase-1 bug fix | 2 reviewers + security review |
| Phase-2 addition | 1 reviewer |
| Phase-3 modification | 2 reviewers + security review |
| Documentation | 1 reviewer |
| Configuration | 1 reviewer |

---

## Appendix A: Quick Reference

### Key Modules

| Module | Import | Purpose |
|--------|--------|---------|
| `create_soc_copilot` | `from soc_copilot import create_soc_copilot` | Create analysis instance |
| `FeedbackStore` | `from soc_copilot.phase2 import FeedbackStore` | Manage feedback |
| `DriftMonitor` | `from soc_copilot.phase2 import DriftMonitor` | Track drift |
| `GovernancePolicy` | `from soc_copilot.phase3.governance import GovernancePolicy` | Check policy |
| `KillSwitch` | `from soc_copilot.phase3.governance import KillSwitch` | Control Phase-3 |

### Database Locations

| Database | Phase | Path |
|----------|-------|------|
| Models | Phase-1 | `data/models/*.joblib` |
| Feedback | Phase-2 | In-memory or `data/feedback.db` |
| Governance | Phase-3 | `data/governance/governance.db` |

### Configuration Files

| File | Purpose |
|------|---------|
| `config/thresholds.yaml` | Alert thresholds |
| `config/features.yaml` | Feature extraction |
| `config/model_config.yaml` | Model parameters |
| `config/governance/policy.yaml` | Governance policy |

---

**Document End**

*SOC Copilot Developer Manual*  
*Version 2.0 — January 2026*
