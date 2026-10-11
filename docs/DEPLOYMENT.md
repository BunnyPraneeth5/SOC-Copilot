# Deployment Guide

This guide covers deploying SOC Copilot in different environments.

## Deployment Options

| Method | Use Case | Complexity |
|--------|----------|------------|
| **Local (Development)** | Testing, development, demos | Simple |
| **Local (Admin)** | Full system log analysis | Medium |
| **Standalone Executable** | Production deployment, no Python needed | Medium |
| **Network Deployment** | Multiple analysts, shared models | Advanced |

---

## 1. Local Development Deployment

### Quick Start

```bash
# Clone and setup
git clone https://github.com/BunnyPraneeth5/SOC-Copilot.git
cd SOC-Copilot
python -m venv venv
source venv/bin/activate        # Linux/macOS
.\venv\Scripts\activate         # Windows

# Install
pip install -r requirements.txt
pip install -e .

# Train models
python scripts/train_models.py
python scripts/train_text_log_model.py

# Launch
python launch_ui.py
```

### Verify Installation

```bash
python check_requirements.py
```

This checks: Python version, package versions, directory structure, model files, and permissions.

---

## 2. Administrator Deployment (System Logs)

To analyze live Windows Event Logs, SOC Copilot must run with administrator privileges.

### Windows

```powershell
# Option 1: Auto-elevation (recommended)
python launch_ui.py
# The app will automatically request UAC elevation

# Option 2: Elevated terminal
# Right-click PowerShell → "Run as Administrator"
cd C:\path\to\SOC-Copilot
.\venv\Scripts\Activate.ps1
python launch_ui.py

# Option 3: Using Make
make run-admin
```

**What happens when running as admin:**
1. Two PowerShell exporter processes start in the background
2. Windows Security and System event logs are exported every 5 seconds to `logs/system/`
3. The ingestion controller tails those files and feeds events into the ML pipeline
4. Events appear on the dashboard in real-time
5. Exporter processes are cleaned up when the app closes

### Linux

```bash
sudo python launch_ui.py
```

This grants read access to `/var/log/syslog`, `/var/log/auth.log`, etc.

---

## 3. Standalone Executable (PyInstaller)

Build a self-contained `.exe` that doesn't require Python.

### Build

```bash
# Install PyInstaller
pip install pyinstaller>=6.0.0

# Build the executable
python scripts/build_exe.py

# Output location
ls dist/SOC-Copilot/
```

### Deploy

1. Copy the `dist/SOC-Copilot/` folder to the target machine
2. Copy the `data/models/` directory alongside the executable
3. Copy the `config/` directory for custom thresholds
4. Run `SOC-Copilot.exe`

### Requirements for Target Machine

- Windows 10/11, macOS 12+, or Linux (Ubuntu 20.04+)
- 4GB+ RAM
- No Python installation needed
- No internet connection needed

---

## 4. Directory Structure on Deployment

```
SOC-Copilot/
├── SOC-Copilot.exe          # Or: python launch_ui.py
├── config/
│   ├── thresholds.yaml      # Alert thresholds
│   ├── features.yaml        # Feature definitions
│   ├── model_config.yaml    # Model parameters
│   └── ingestion/
│       └── system_logs.yaml # System log settings
├── data/
│   └── models/              # Trained model files
│       ├── isolation_forest_v1.joblib
│       ├── random_forest_v1.joblib
│       ├── text_log_rf_v1.joblib
│       ├── feature_order.json
│       └── label_map.json
├── logs/                    # Application logs (auto-created)
│   └── system/              # System log exports (auto-created)
└── scripts/
    └── exporters/           # PowerShell exporters (for admin mode)
```

---

## 5. Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT` | `false` | Allow external lookups (Recon, Reputation, Shodan, report LLM) |
| `SOC_COPILOT_STRICT_MODEL_INTEGRITY` | `true` | Refuse to load models missing from the hash manifest |
| `ABUSEIPDB_API_KEY`, `VIRUSTOTAL_API_KEY`, `SHODAN_API_KEY` | — | Threat-intelligence enrichment keys |
| `REPORT_LLM_PROVIDER` | `nvidia_nim` | Report LLM provider (`nvidia_nim` or `openrouter`) |
| `NVIDIA_API_KEY` | — | Key from build.nvidia.com (`nvapi-…`) |
| `NVIDIA_NIM_MODEL` | `nvidia/nemotron-3-super-120b-a12b` | Primary report model |
| `NVIDIA_NIM_FALLBACK_MODEL` | `deepseek-ai/deepseek-v4.1-flash` | Tried when the primary fails or times out; empty disables it |
| `REPORT_LLM_FALLBACK_PROVIDER` | unset | Optional last-resort provider (sends alert data there too) |
| `SOC_COPILOT_THEME` | `dark` | Initial UI theme (`dark` or `light`) |

System log ingestion is configured in `config/ingestion/system_logs.yaml` (`enabled`, `export_interval`), not in `.env`.

### YAML Configuration

See `config/thresholds.yaml` for:
- Anomaly score thresholds
- Ensemble weight distribution
- Alert priority thresholds
- Deduplication settings
- Conservative mode settings

---

## 6. Integration with Other Systems

### Log File Integration

SOC Copilot can monitor any directory for new log files:

1. Configure your SIEM/log shipper to write logs to a directory
2. Point SOC Copilot's file watcher at that directory
3. Events are ingested, processed, and displayed in real-time

### Supported Input Formats

| Format | Extension | Example Source |
|--------|-----------|---------------|
| CSV/TSV | `.csv` | Network flow exports, firewall logs |
| JSON/JSONL | `.json`, `.jsonl` | Structured log pipelines |
| Syslog | `.log`, `.syslog` | rsyslog, syslog-ng |
| Windows EVTX | `.evtx` | Windows Event Viewer exports |
| Custom text | `.log` | Application logs, custom formats |

### API Integration (Programmatic)

Use the Python API directly:

```python
from soc_copilot.pipeline import create_soc_copilot

# Load the pipeline
pipeline = create_soc_copilot("data/models")

# Analyze a log file
results, alerts, stats = pipeline.analyze_file("path/to/logfile.csv")

# Process results
for alert in alerts:
    print(f"{alert['priority']}: {alert['classification']} ({alert['confidence']:.0%})")
```

---

## 7. Monitoring & Maintenance

### Application Logs

- Stored in `logs/` directory
- Structured JSON format via `structlog`
- Includes: model loading, batch processing, alert generation, errors

### Model Retraining

Models should be retrained when:
- Detection accuracy degrades
- New attack types emerge
- Network topology changes significantly

```bash
# Retrain all models
make train

# Retrain specific models
make train-network   # Network-flow model only
make train-textlog   # Text log classifier only
```

### Health Checks

```bash
# Verify all system requirements
python check_requirements.py

# Check model files exist
ls data/models/

# Run test suite
make test
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Pipeline not loaded" | Run `python scripts/train_models.py` |
| "System log access limited" | Run as administrator |
| UI becomes unresponsive | Heavy processing runs on QThread — wait for batch |
| Models not found | Check `data/models/` has `.joblib` files |
| Permission denied | Ensure write access to `data/` and `logs/` |
| PowerShell exporter fails | Run `Set-ExecutionPolicy RemoteSigned` in admin PowerShell |
