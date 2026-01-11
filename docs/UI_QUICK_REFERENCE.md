# Sprint-16 UI Quick Reference

## Overview
Sprint-16 implements a PyQt6 desktop UI for real-time security alert visualization.

## Launch UI

### Basic Launch
```bash
cd "c:\Users\karup\projects\SOC Copilot"
python launch_ui.py
```

### With Real-Time Ingestion
```python
from soc_copilot.phase4.ingestion import IngestionController
from soc_copilot.phase4.controller import AppController
from soc_copilot.phase4.ui import MainWindow
from PyQt6.QtWidgets import QApplication
import sys

# Setup
controller = AppController(models_dir="data/models")
controller.initialize()

ingestion = IngestionController(batch_interval=5.0)
ingestion.set_batch_callback(controller.process_batch)
ingestion.add_file_source("/var/log/access.log")
ingestion.start()

# Launch UI
app = QApplication(sys.argv)
window = MainWindow(controller)
window.show()
sys.exit(app.exec())
```

## UI Components

### Dashboard (Top)
- **Total Alerts**: All alerts count
- **Critical**: P0-Critical count (red)
- **High**: P1-High count (yellow)
- **Medium**: P2-Medium count (orange)
- **Status**: Pipeline and results status
- **Auto-refresh**: Every 3 seconds

### Alerts View (Left)
- **Table**: Latest 50 alerts
- **Columns**: Time, Priority, Classification, Source IP, Confidence, Batch ID
- **Color-coded**: By priority (red/yellow/orange/white)
- **Click**: Select alert to view details
- **Auto-refresh**: Every 3 seconds

### Alert Details (Right Tab 1)
- **Metadata**: Alert ID, Priority, Classification
- **Scores**: Confidence, Anomaly, Risk
- **Network**: Source/Destination IPs
- **Explainability**: Reasoning text
- **Action**: Suggested action
- **Read-only**: No editing

### Assistant (Right Tab 2)
- **Chat-like**: Q&A format
- **Questions**:
  - "Why was this alert generated?"
  - "What does this mean?"
  - "What should I do?"
- **Templates**: Predefined responses
- **No LLM**: Uses explainability metadata only

## Features

### Auto-Refresh
- Dashboard: 3 seconds
- Alerts table: 3 seconds
- Automatic updates

### Color Coding
- **Red**: Critical priority
- **Yellow**: High priority
- **Orange**: Medium priority
- **White**: Low/Info priority

### Dark Theme
- Professional appearance
- Easy on eyes
- Analyst-friendly

## Read-Only Access

UI provides **read-only** access:
- ✅ View alerts
- ✅ View details
- ✅ View explanations
- ✅ View statistics
- ❌ NO modifications
- ❌ NO feedback submission
- ❌ NO threshold changes
- ❌ NO auto-actions

## Assistant Panel

### NOT a Chatbot
- No LLM integration
- No API calls
- No internet access
- Template-based only

### Explanation Templates

**BruteForce:**
> A brute force attack involves repeated login attempts to guess credentials. This pattern suggests an attacker is trying to gain unauthorized access.

**PortScan:**
> A port scan is reconnaissance activity where an attacker probes your network to find open ports and services. This is often a precursor to an attack.

**DDoS:**
> A Distributed Denial of Service attack attempts to overwhelm your systems with traffic, making services unavailable to legitimate users.

**SQLInjection:**
> SQL injection is an attack that exploits vulnerabilities in database queries to access or manipulate data. This is a critical security risk.

**XSS:**
> Cross-Site Scripting allows attackers to inject malicious scripts into web pages viewed by other users, potentially stealing data or hijacking sessions.

## Keyboard Shortcuts

- **Click Row**: View alert details
- **Tab**: Switch between Details and Assistant
- **Scroll**: Navigate details panel

## Requirements

### Install PyQt6
```bash
pip install PyQt6
```

### System Requirements
- Python 3.8+
- PyQt6
- Windows/Linux/macOS

## Troubleshooting

### UI Won't Launch
```bash
# Check PyQt6 installation
pip install PyQt6

# Check Python version
python --version  # Should be 3.8+
```

### No Alerts Showing
- Check if controller is initialized
- Check if ingestion is running
- Check if models are loaded

### Pipeline Not Loaded
```python
# Check controller status
stats = controller.get_stats()
print(stats["pipeline_loaded"])  # Should be True
```

## Configuration

### Refresh Interval
Edit in source files:
- `dashboard.py`: Line with `timer.start(3000)`
- `alerts_view.py`: Line with `timer.start(3000)`
- Change `3000` to desired milliseconds

### Table Limit
Edit in `alerts_view.py`:
```python
results = self.bridge.get_latest_alerts(limit=50)  # Change 50
```

### Dashboard Metrics Limit
Edit in `dashboard.py`:
```python
results = self.bridge.get_latest_alerts(limit=100)  # Change 100
```

## Safety

- ✅ Read-only UI
- ✅ No ML calls
- ✅ No retraining
- ✅ No threshold changes
- ✅ No auto-actions
- ✅ No internet access
- ✅ Offline only
- ✅ Template-based explanations

## Testing

Run UI tests:
```bash
python -m pytest tests/unit/test_ui_sprint16.py -v
```

## Known Limitations

1. **No Persistence**: Results lost on restart
2. **No Export**: No CSV/JSON export
3. **No Filtering**: No advanced filtering
4. **No Search**: No search functionality
5. **No Governance UI**: Use CLI for governance

## Future Enhancements (Not in Sprint-16)

- Export to CSV/JSON
- Advanced filtering
- Search functionality
- Governance UI controls
- Alert history charts
- Custom dashboards
