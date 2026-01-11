# SOC Copilot — User Manual

**Version**: 2.0  
**For**: SOC Analysts & Security Operators  
**Date**: January 2026

---

## Table of Contents

1. [What is SOC Copilot](#1-what-is-soc-copilot)
2. [System Requirements](#2-system-requirements)
3. [Installation Guide](#3-installation-guide)
4. [Folder Structure Overview](#4-folder-structure-overview)
5. [How to Run the Application](#5-how-to-run-the-application)
6. [CLI Commands Explained](#6-cli-commands-explained)
7. [Understanding Alerts](#7-understanding-alerts)
8. [Understanding Explainability Output](#8-understanding-explainability-output)
9. [Using Feedback](#9-using-feedback)
10. [Using Drift Reports](#10-using-drift-reports)
11. [Using Calibration](#11-using-calibration)
12. [Governance & Kill Switch](#12-governance--kill-switch)
13. [Common Errors & Troubleshooting](#13-common-errors--troubleshooting)
14. [Best Practices](#14-best-practices)
15. [Example Workflows](#15-example-workflows)

---

## 1. What is SOC Copilot

### 1.1 Overview

SOC Copilot is an **offline, desktop-based security analysis tool** that helps SOC analysts identify potential security threats in log data. It uses machine learning to:

- Detect anomalous behavior (unusual patterns)
- Classify known attack types (DDoS, malware, brute force, etc.)
- Generate prioritized alerts (P0-Critical to P4-Info)
- Provide human-readable explanations for each alert

### 1.2 Key Features

| Feature | Description |
|---------|-------------|
| **Multi-format Support** | Analyzes JSON, CSV, Syslog, and Windows EVTX logs |
| **Hybrid Detection** | Combines anomaly detection + threat classification |
| **Prioritized Alerts** | P0 (Critical) to P4 (Informational) |
| **Explainability** | Every alert includes reasoning |
| **Offline Operation** | No internet connection required |
| **Analyst Control** | You are always in control |

### 1.3 What SOC Copilot Does NOT Do

- Does NOT automatically block or quarantine threats
- Does NOT learn or update models automatically
- Does NOT require internet connectivity
- Does NOT replace analyst judgment

---

## 2. System Requirements

### 2.1 Minimum Requirements

| Component | Requirement |
|-----------|-------------|
| **Operating System** | Windows 10+, Linux, macOS |
| **Python** | 3.10 or higher |
| **RAM** | 8 GB minimum |
| **Disk Space** | 2 GB for application + models |
| **Display** | Terminal/command prompt access |

### 2.2 Recommended Requirements

| Component | Recommendation |
|-----------|----------------|
| **RAM** | 16 GB |
| **Disk Space** | 10 GB (for large log files) |
| **CPU** | Multi-core processor |

### 2.3 Dependencies

SOC Copilot automatically installs required dependencies:

- pandas (data processing)
- scikit-learn (machine learning)
- pydantic (data validation)
- structlog (logging)
- PyQt6 (optional UI components)

---

## 3. Installation Guide

### 3.1 Step-by-Step Installation

```bash
# Step 1: Clone the repository
git clone <repository-url>
cd SOC-Copilot

# Step 2: Create a virtual environment
python -m venv venv

# Step 3: Activate the virtual environment
# On Windows:
venv\Scripts\activate

# On Linux/macOS:
source venv/bin/activate

# Step 4: Install SOC Copilot
pip install -e .

# Step 5: Verify installation
python -c "from soc_copilot import create_soc_copilot; print('Installation successful!')"
```

### 3.2 Verify Models Are Available

```bash
# Check status
python -m soc_copilot.cli status
```

Expected output:
```
╔══════════════════════════════════════════════════════════════╗
║                      SOC Copilot Status                       ║
╟──────────────────────────────────────────────────────────────╢
║ Version: 0.1.0                                                ║
║ Models Directory: data/models                                 ║
║                                                               ║
║ Models:                                                       ║
║   • Isolation Forest: ✅ Loaded                               ║
║   • Random Forest: ✅ Loaded                                  ║
║   • Feature Order: ✅ 78 features                             ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 4. Folder Structure Overview

```
SOC Copilot/
├── config/                    # Configuration files
│   ├── thresholds.yaml        # Alert thresholds
│   ├── features.yaml          # Feature extraction settings
│   ├── model_config.yaml      # Model parameters
│   └── governance/            # Governance policy
│       └── policy.yaml
│
├── data/                      # Data directory
│   ├── models/                # Trained ML models
│   │   ├── isolation_forest_v1.joblib
│   │   ├── random_forest_v1.joblib
│   │   ├── feature_order.json
│   │   └── label_map.json
│   └── governance/            # Governance database
│       └── governance.db
│
├── src/soc_copilot/           # Application code
│   ├── cli.py                 # Command-line interface
│   ├── pipeline.py            # Analysis pipeline
│   ├── phase2/                # Trust & Intelligence
│   └── phase3/                # Governance
│
└── tests/                     # Test files
```

### 4.1 Important Files for Users

| File/Folder | Purpose |
|-------------|---------|
| `config/thresholds.yaml` | Adjust alert thresholds |
| `data/models/` | Pre-trained ML models (do not modify) |
| `data/governance/` | Governance state and audit logs |

---

## 5. How to Run the Application

### 5.1 Basic Analysis

```bash
# Analyze a single log file
python -m soc_copilot.cli analyze path/to/logs.json

# Analyze a directory of logs
python -m soc_copilot.cli analyze path/to/logs/ --recursive
```

### 5.2 Common Options

| Option | Description | Example |
|--------|-------------|---------|
| `--output-format` | Output format (text, json) | `--output-format json` |
| `--min-priority` | Minimum priority to show | `--min-priority P2-Medium` |
| `--output-file` | Save output to file | `--output-file report.txt` |
| `--recursive` | Include subdirectories | `--recursive` |

### 5.3 Example Commands

```bash
# Analyze with JSON output
python -m soc_copilot.cli analyze logs/ --output-format json

# Show only high-priority alerts
python -m soc_copilot.cli analyze logs/ --min-priority P1-High

# Save results to file
python -m soc_copilot.cli analyze logs/ --output-file results.json --output-format json
```

---

## 6. CLI Commands Explained

### 6.1 analyze

**Purpose**: Analyze log files for security threats.

```bash
python -m soc_copilot.cli analyze <path> [options]
```

**Arguments**:
| Argument | Description |
|----------|-------------|
| `<path>` | Path to log file or directory |
| `--recursive` | Include subdirectories |
| `--output-format` | Output format: text, json |
| `--min-priority` | Minimum priority: P0-Critical, P1-High, P2-Medium, P3-Low, P4-Info |
| `--output-file` | Save output to file |

**Example**:
```bash
python -m soc_copilot.cli analyze logs/access.jsonl --output-format json
```

### 6.2 feedback

**Purpose**: Provide analyst feedback on alerts.

```bash
python -m soc_copilot.cli feedback <action> [options]
```

**Actions**:
| Action | Description |
|--------|-------------|
| `add` | Add feedback for an alert |
| `list` | List all feedback entries |
| `stats` | Show feedback statistics |
| `export` | Export feedback to JSON |
| `import` | Import feedback from JSON |

**Examples**:
```bash
# Add feedback for an alert
python -m soc_copilot.cli feedback add \
  --alert-id "a1b2c3d4" \
  --verdict "true_positive" \
  --analyst "analyst1" \
  --notes "Confirmed malware infection"

# List recent feedback
python -m soc_copilot.cli feedback list --limit 10

# Export feedback
python -m soc_copilot.cli feedback export --output feedback.json
```

### 6.3 drift

**Purpose**: Monitor model drift and feature distribution changes.

```bash
python -m soc_copilot.cli drift <action> [options]
```

**Actions**:
| Action | Description |
|--------|-------------|
| `report` | Generate drift report |
| `compare` | Compare two time periods |

**Example**:
```bash
# Generate drift report
python -m soc_copilot.cli drift report --days 30
```

### 6.4 calibrate

**Purpose**: Generate threshold calibration recommendations.

```bash
python -m soc_copilot.cli calibrate <action> [options]
```

**Actions**:
| Action | Description |
|--------|-------------|
| `analyze` | Analyze current thresholds |
| `recommend` | Generate recommendations |
| `apply` | Apply recommended thresholds (requires approval) |

**Example**:
```bash
# Get calibration recommendations
python -m soc_copilot.cli calibrate recommend --based-on feedback

# Analyze current thresholds
python -m soc_copilot.cli calibrate analyze
```

> [!IMPORTANT]
> Applying calibration changes requires manual approval. The system will not automatically change thresholds.

### 6.5 governance

**Purpose**: Manage governance infrastructure (Phase-3).

```bash
python -m soc_copilot.cli governance <action> [options]
```

**Actions**:
| Action | Description |
|--------|-------------|
| `status` | Show governance status |
| `request` | Create approval request |
| `approve` | Approve a request |
| `reject` | Reject a request |
| `revoke` | Revoke approved request |
| `enable` | Enable Phase-3 (disable kill switch) |
| `disable` | Disable Phase-3 (enable kill switch) |

**Examples**:
```bash
# Check governance status
python -m soc_copilot.cli governance status

# Create approval request
python -m soc_copilot.cli governance request \
  --action "enable_monitoring" \
  --reason "Need monitoring capability" \
  --requester "analyst1"
```

### 6.6 Command Summary Table

| Command | Purpose | Example |
|---------|---------|---------|
| `analyze` | Analyze log files | `analyze logs/` |
| `feedback` | Manage analyst feedback | `feedback add --alert-id X` |
| `drift` | Monitor model drift | `drift report --days 30` |
| `calibrate` | Threshold calibration | `calibrate recommend` |
| `status` | System status | `status` |
| `governance` | Governance control | `governance status` |

---

## 7. Understanding Alerts

### 7.1 Alert Priority Levels

| Priority | Meaning | Recommended Action | SLA Guidance |
|----------|---------|-------------------|--------------|
| **P0-Critical** | Confirmed severe threat | Immediate investigation | < 15 minutes |
| **P1-High** | High-confidence attack | Investigate promptly | < 1 hour |
| **P2-Medium** | Possible threat | Review when available | < 4 hours |
| **P3-Low** | Low-confidence issue | Monitor | < 24 hours |
| **P4-Info** | Informational | No action required | — |

### 7.2 Alert Structure

```
╔══════════════════════════════════════════════════════════════╗
║ ALERT: P1-High - Malware                                      ║
╟──────────────────────────────────────────────────────────────╢
║ ID: a1b2c3d4-5678-90ab-cdef-1234567890ab                      ║
║ Time: 2026-01-10T11:00:00Z                                    ║
║ Risk Level: High                                               ║
║ Risk Score: 0.72                                               ║
╟──────────────────────────────────────────────────────────────╢
║ Classification: Malware (92.5% confidence)                    ║
║ Anomaly Score: 0.85                                            ║
╟──────────────────────────────────────────────────────────────╢
║ Source: 192.168.1.100:45678                                   ║
║ Destination: 10.0.0.5:22                                       ║
╟──────────────────────────────────────────────────────────────╢
║ Reasoning:                                                     ║
║   • Classified as Malware with 92.5% confidence               ║
║   • High anomaly score (0.85) indicates unusual behavior      ║
║   • Connection to unusual destination port                     ║
╟──────────────────────────────────────────────────────────────╢
║ Suggested Action: Isolate endpoint and investigate            ║
╟──────────────────────────────────────────────────────────────╢
║ MITRE ATT&CK: T1059 - Command and Scripting Interpreter       ║
╚══════════════════════════════════════════════════════════════╝
```

### 7.3 Key Alert Fields

| Field | Description |
|-------|-------------|
| **ID** | Unique identifier for this alert |
| **Time** | When the suspicious activity occurred |
| **Risk Level** | Critical, High, Medium, or Low |
| **Risk Score** | Numeric score (0.0 - 1.0) |
| **Classification** | Attack type (DDoS, Malware, etc.) |
| **Anomaly Score** | How unusual the behavior is (0.0 - 1.0) |
| **Reasoning** | Human-readable explanation |
| **Suggested Action** | Recommended response |
| **MITRE ATT&CK** | Mapped tactics and techniques |

### 7.4 Threat Categories

| Category | Description | Typical Indicators |
|----------|-------------|-------------------|
| **DDoS** | Distributed Denial of Service | High traffic volume, many sources |
| **BruteForce** | Password guessing attacks | Multiple failed logins |
| **Malware** | Malicious software | Unusual process execution |
| **Exfiltration** | Data theft | Large outbound transfers |
| **Reconnaissance** | Network scanning | Port scans, service enumeration |
| **Injection** | Code injection attacks | SQL/command injection patterns |
| **Benign** | Normal activity | — |

---

## 8. Understanding Explainability Output

### 8.1 Reasoning Field

Each alert includes a `reasoning` field that explains why the alert was generated:

```
Reasoning:
  • Classified as Malware with 92.5% confidence
  • High anomaly score (0.85) indicates unusual behavior
  • Top contributing features: port_entropy (0.15), unique_destinations (0.12)
  • Risk boosted: severe threat with anomalous behavior
```

### 8.2 Feature Importance

When requested, SOC Copilot shows which log attributes contributed most to the decision:

| Feature | Contribution | Meaning |
|---------|--------------|---------|
| `port_entropy` | 0.15 | Unusual variety of destination ports |
| `unique_destinations` | 0.12 | Contact with many different hosts |
| `time_since_last` | 0.09 | Unusual timing of activity |
| `bytes_total` | 0.08 | Unusual data transfer volume |

### 8.3 Score Breakdown

```
Combined Risk Score: 0.72
├── Anomaly Score (IF): 0.85 × 0.4 weight = 0.34
├── Classification Score (RF): 0.925 × 0.6 weight = 0.555
└── Adjustments: +20% boost (severe threat + anomalous)
```

---

## 9. Using Feedback

### 9.1 Why Provide Feedback?

Your feedback helps:
- Track alert accuracy over time
- Generate calibration recommendations
- Build audit trail for governance review
- Improve your organization's security metrics

> [!NOTE]
> Feedback is stored locally but does NOT automatically update the detection models. Model updates require manual offline retraining.

### 9.2 Adding Feedback

```bash
python -m soc_copilot.cli feedback add \
  --alert-id "a1b2c3d4-5678-90ab-cdef-1234567890ab" \
  --verdict "true_positive" \
  --analyst "your_name" \
  --notes "Confirmed malware infection on endpoint WS-101"
```

**Verdict Options**:
| Verdict | Meaning |
|---------|---------|
| `true_positive` | Alert correctly identified a threat |
| `false_positive` | Alert was incorrect (not a threat) |
| `true_negative` | Correctly identified as benign |
| `false_negative` | Missed threat (should have alerted) |

### 9.3 Viewing Feedback Statistics

```bash
python -m soc_copilot.cli feedback stats
```

Output:
```
╔══════════════════════════════════════════════════════════════╗
║                    Feedback Statistics                        ║
╟──────────────────────────────────────────────────────────────╢
║ Total Feedback: 247                                           ║
║ True Positives: 198 (80.2%)                                  ║
║ False Positives: 42 (17.0%)                                  ║
║ False Negatives: 7 (2.8%)                                    ║
║                                                               ║
║ By Category:                                                  ║
║   Malware: 89 alerts, 92.1% accuracy                         ║
║   DDoS: 56 alerts, 78.6% accuracy                            ║
║   BruteForce: 45 alerts, 84.4% accuracy                      ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 10. Using Drift Reports

### 10.1 What is Drift?

**Drift** occurs when the patterns in your log data change significantly over time. This can affect detection accuracy.

Types of drift:
- **Feature drift**: Log data characteristics change
- **Concept drift**: Attack patterns evolve
- **Label drift**: What constitutes an attack changes

### 10.2 Generating Drift Reports

```bash
python -m soc_copilot.cli drift report --days 30
```

Output:
```
╔══════════════════════════════════════════════════════════════╗
║                     Drift Report                              ║
╟──────────────────────────────────────────────────────────────╢
║ Period: Last 30 days                                          ║
║ Overall Drift Level: LOW                                      ║
║                                                               ║
║ Feature Drift:                                                ║
║   • unique_destinations: +12% (MODERATE)                     ║
║   • port_entropy: -3% (LOW)                                  ║
║   • time_since_last: +2% (LOW)                               ║
║                                                               ║
║ Recommendation: No immediate action required                  ║
╚══════════════════════════════════════════════════════════════╝
```

### 10.3 Drift Levels

| Level | Meaning | Action |
|-------|---------|--------|
| **LOW** | Normal variation | No action needed |
| **MODERATE** | Notable change | Monitor closely |
| **HIGH** | Significant drift | Consider recalibration |
| **CRITICAL** | Severe drift | Model may need retraining |

---

## 11. Using Calibration

### 11.1 What is Calibration?

Calibration adjusts alert thresholds to match your environment's specific characteristics, reducing false positives while maintaining detection accuracy.

### 11.2 Getting Recommendations

```bash
python -m soc_copilot.cli calibrate recommend --based-on feedback
```

Output:
```
╔══════════════════════════════════════════════════════════════╗
║                Calibration Recommendations                    ║
╟──────────────────────────────────────────────────────────────╢
║ Based on: 247 feedback entries                                ║
║                                                               ║
║ Recommended Changes:                                          ║
║   • anomaly.high_threshold: 0.70 → 0.75                      ║
║     Reason: 17% false positive rate at current threshold     ║
║                                                               ║
║   • classification.min_confidence: 0.70 → 0.75               ║
║     Reason: Low-confidence classifications often wrong       ║
║                                                               ║
║ Expected Impact:                                              ║
║   • False positives: -25%                                    ║
║   • True positives: -3%                                      ║
╚══════════════════════════════════════════════════════════════╝
```

### 11.3 Applying Calibration (Manual Approval Required)

> [!CAUTION]
> Applying calibration changes modifies system behavior. This requires manual approval and is recorded in the audit log.

```bash
# First, review the recommendation
python -m soc_copilot.cli calibrate recommend --based-on feedback

# If approved by your security team, apply changes
python -m soc_copilot.cli calibrate apply --config new_thresholds.yaml
```

---

## 12. Governance & Kill Switch

### 12.1 Governance Overview

Phase-3 governance controls advanced system capabilities. By default, all governance features are **disabled**.

### 12.2 Checking Governance Status

```bash
python -m soc_copilot.cli governance status
```

Output:
```
╔══════════════════════════════════════════════════════════════╗
║                    Governance Status                          ║
╟──────────────────────────────────────────────────────────────╢
║ Kill Switch: ENABLED (Phase-3 disabled)                       ║
║ Authority State: DISABLED                                     ║
║ Permitted Components: None                                    ║
║                                                               ║
║ Pending Requests: 0                                           ║
║ Audit Events: 12                                              ║
╚══════════════════════════════════════════════════════════════╝
```

### 12.3 Authority States

| State | Description |
|-------|-------------|
| **DISABLED** | No automation permitted (default) |
| **OBSERVE_ONLY** | Logging and monitoring only |
| **ADVISORY_ONLY** | Can provide recommendations, no actions |

### 12.4 Kill Switch

The kill switch is an emergency control that immediately disables all Phase-3 functionality:

```bash
# Disable Phase-3 (enable kill switch)
python -m soc_copilot.cli governance disable \
  --actor "your_name" \
  --reason "Emergency shutdown for investigation"

# Enable Phase-3 (disable kill switch) - requires authorization
python -m soc_copilot.cli governance enable \
  --actor "your_name" \
  --reason "Authorized re-activation after review"
```

> [!WARNING]
> All governance actions are recorded in an append-only audit log. This log cannot be modified or deleted.

---

## 13. Common Errors & Troubleshooting

### 13.1 Models Not Found

**Error**: `Models not found in data/models/`

**Solution**:
```bash
# Check if model files exist
ls data/models/

# Expected files:
# - isolation_forest_v1.joblib
# - random_forest_v1.joblib
# - feature_order.json
# - label_map.json
```

If files are missing, you need to train models (offline, requires training data).

### 13.2 Feature Mismatch

**Error**: `Feature count mismatch: expected 78, got 65`

**Solution**: Ensure your log files contain the required fields. Check `config/features.yaml` for expected fields.

### 13.3 Log Format Not Detected

**Error**: `Could not detect log format for file.log`

**Solution**: 
- Ensure file has correct extension (.json, .csv, .log, .evtx)
- Check file contents match expected format
- JSON files should have one record per line

### 13.4 Permission Denied (Governance)

**Error**: `Permission denied: kill switch is enabled`

**Solution**: Phase-3 governance features are disabled by default. Contact your administrator to enable.

### 13.5 Out of Memory

**Error**: `MemoryError during analysis`

**Solution**:
- Process smaller batches of log files
- Increase system RAM
- Close other applications

### 13.6 Command Not Found

**Error**: `python: command not found` or `soc-copilot: command not found`

**Solution**:
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate      # Windows

# Use `python -m` syntax
python -m soc_copilot.cli analyze logs/
```

---

## 14. Best Practices

### 14.1 Log Analysis

| Practice | Recommendation |
|----------|----------------|
| **Regular Analysis** | Run analysis daily on new logs |
| **Priority Focus** | Address P0 and P1 alerts first |
| **Batch Processing** | Process logs in manageable batches |
| **Archive Results** | Save analysis results for audit trail |

### 14.2 Feedback

| Practice | Recommendation |
|----------|----------------|
| **Consistent Feedback** | Provide feedback on all alerts you investigate |
| **Timely Feedback** | Submit feedback promptly while details are fresh |
| **Detailed Notes** | Include investigation findings in notes |
| **Regular Stats Review** | Check feedback statistics weekly |

### 14.3 Calibration

| Practice | Recommendation |
|----------|----------------|
| **Baseline First** | Establish baseline before adjusting thresholds |
| **Incremental Changes** | Make small threshold adjustments |
| **Monitor Impact** | Track alert volume and accuracy after changes |
| **Document Changes** | Record why thresholds were modified |

### 14.4 Governance

| Practice | Recommendation |
|----------|----------------|
| **Keep Disabled** | Leave governance disabled unless needed |
| **Audit Review** | Periodically review governance audit log |
| **Emergency Procedures** | Know how to activate kill switch |
| **Authorization** | Never enable advanced features without approval |

---

## 15. Example Workflows

### 15.1 Daily Triage Workflow

```bash
# Step 1: Check system status
python -m soc_copilot.cli status

# Step 2: Analyze today's logs
python -m soc_copilot.cli analyze /var/log/security/2026-01-11/ \
  --output-format json \
  --output-file reports/2026-01-11_analysis.json

# Step 3: Review high-priority alerts
python -m soc_copilot.cli analyze /var/log/security/2026-01-11/ \
  --min-priority P1-High

# Step 4: Provide feedback on investigated alerts
python -m soc_copilot.cli feedback add \
  --alert-id "a1b2c3d4" \
  --verdict "true_positive" \
  --analyst "analyst1" \
  --notes "Confirmed brute force attack, blocked source IP"
```

### 15.2 Weekly Review Workflow

```bash
# Step 1: Generate feedback statistics
python -m soc_copilot.cli feedback stats

# Step 2: Check for drift
python -m soc_copilot.cli drift report --days 7

# Step 3: Review calibration recommendations
python -m soc_copilot.cli calibrate recommend --based-on feedback

# Step 4: Export feedback for reporting
python -m soc_copilot.cli feedback export --output weekly_feedback.json
```

### 15.3 Incident Investigation Workflow

```bash
# Step 1: Analyze specific timeframe
python -m soc_copilot.cli analyze logs/incident_2026-01-10/ \
  --output-format json \
  --output-file incident_analysis.json

# Step 2: Review all alerts (including low priority)
python -m soc_copilot.cli analyze logs/incident_2026-01-10/ \
  --min-priority P4-Info

# Step 3: Document findings
python -m soc_copilot.cli feedback add \
  --alert-id "incident-alert-id" \
  --verdict "true_positive" \
  --analyst "incident_handler" \
  --notes "Part of incident IR-2026-001. Attack vector confirmed."
```

### 15.4 Emergency Response Workflow

```bash
# Step 1: If something goes wrong with Phase-3, activate kill switch
python -m soc_copilot.cli governance disable \
  --actor "admin" \
  --reason "Emergency: unexpected behavior detected"

# Step 2: Verify Phase-3 is disabled
python -m soc_copilot.cli governance status

# Step 3: Continue with Phase-1 analysis (unaffected)
python -m soc_copilot.cli analyze logs/ --recursive
```

---

## Appendix A: Quick Reference Card

### Common Commands

| Task | Command |
|------|---------|
| Analyze logs | `python -m soc_copilot.cli analyze <path>` |
| Check status | `python -m soc_copilot.cli status` |
| Add feedback | `python -m soc_copilot.cli feedback add ...` |
| View feedback | `python -m soc_copilot.cli feedback list` |
| Drift report | `python -m soc_copilot.cli drift report` |
| Calibrate | `python -m soc_copilot.cli calibrate recommend` |
| Governance | `python -m soc_copilot.cli governance status` |

### Priority SLAs

| Priority | Response Time |
|----------|---------------|
| P0-Critical | < 15 minutes |
| P1-High | < 1 hour |
| P2-Medium | < 4 hours |
| P3-Low | < 24 hours |
| P4-Info | No action |

### Feedback Verdicts

| Verdict | When to Use |
|---------|-------------|
| `true_positive` | Alert was correct |
| `false_positive` | Alert was wrong |
| `true_negative` | Benign correctly identified |
| `false_negative` | Threat missed |

---

**Document End**

*SOC Copilot User Manual*  
*Version 2.0 — January 2026*
