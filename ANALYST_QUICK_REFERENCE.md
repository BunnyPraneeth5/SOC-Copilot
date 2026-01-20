# SOC Copilot - Analyst Quick Reference

## 🚀 Quick Start

```bash
python launch_ui.py
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+1` | Dashboard |
| `Ctrl+2` | Alerts |
| `Ctrl+3` | Investigation |
| `Ctrl+4` | Assistant |
| `Ctrl+,` | Settings |
| `F5` | Refresh current view |

---

## 📊 Dashboard Overview

### Key Metrics (Top Row)
- **Total Alerts**: All detected threats
- **Critical**: Immediate action required
- **High**: Urgent investigation needed
- **Medium**: Review when possible

### Status Cards
- **Log Ingestion**: Active/Idle/Not Started
- **Governance**: Kill switch and permissions

### Activity Feed
- Real-time log of system events
- Color-coded by severity
- Latest events at top

---

## 🚨 Alerts View

### Header Controls
- **Filter dropdown**: Show only Critical/High/Medium/Low
- **Search box**: Find by classification, IP, or batch ID
- **🔄 button**: Manual refresh

### Alert Counter
```
Total: 156 │ Critical: 12 │ High: 34 │ Medium: 67
```

### Table Columns
1. **Time**: When alert was detected
2. **Priority**: Critical/High/Medium/Low (color-coded)
3. **Classification**: Attack type
4. **Source IP**: Origin of threat
5. **Confidence**: ML confidence score
6. **Batch ID**: Unique identifier

### Color Coding
- 🔴 **Red**: Critical priority
- 🟠 **Orange**: High priority
- 🟡 **Yellow**: Medium priority
- ⚪ **White**: Low priority

### Actions
- **Click any row** → Navigate to Investigation view
- **Scroll freely** → Position preserved on refresh
- **Filter/Search** → Instant client-side filtering

---

## 🔍 Investigation View

### Navigation
- **← Back to Alerts**: Return to alerts table

### Alert Details
1. **Priority Badge**: Color-coded severity
2. **Classification**: Full attack description
3. **Key Metrics**:
   - **Confidence**: How certain the ML model is
   - **Anomaly Score**: Deviation from normal
   - **Risk Score**: Overall threat level
4. **Network Info**: Source/Destination IPs
5. **Analysis Reasoning**: Why this was flagged
6. **Suggested Action**: Recommended response

### Metric Colors
- 🟢 **Green**: High confidence (>80%)
- 🟡 **Yellow**: Medium confidence (60-80%)
- 🟠 **Orange**: Low confidence (<60%)

---

## 📁 Uploading Logs

### From Dashboard
1. Click **"📁 Upload Logs"** button
2. Select one or more log files:
   - JSON (`.json`, `.jsonl`)
   - CSV (`.csv`)
   - Plain text (`.log`, `.txt`)
   - Windows Event Logs (`.evtx`)
3. Watch progress bar
4. Check activity feed for results

### Supported Formats
- **JSON**: Structured logs
- **CSV**: Tabular data
- **Plain text**: Line-by-line logs
- **EVTX**: Windows Event Logs (requires admin)

---

## 🛡️ System Status Bar

### Indicators (Top of Screen)

| Indicator | Meaning |
|-----------|---------|
| **Pipeline** 🟢 Active | ML models loaded and ready |
| **Pipeline** 🟡 Loading | Models initializing |
| **Ingestion** 🔵 Active (3) | Processing 3 log sources |
| **Ingestion** ⚪ Idle (3) | 3 sources configured, not running |
| **Kill Switch** 🟢 OFF | Normal operation |
| **Kill Switch** 🔴 ACTIVE | Emergency stop engaged |
| **Admin** 🟢 Full | Administrator privileges |
| **Admin** 🟡 Limited | Standard user (no system logs) |
| **Buffer** 🟢 50/10000 | Processing buffer healthy |
| **Buffer** 🟡 9000/10000 | Buffer near capacity |

### Update Frequency
Status bar updates every **1 second** for real-time monitoring.

---

## 🎯 Common Workflows

### 1. Initial Setup
```
Dashboard → Upload Logs → Monitor Status Bar → Wait for Alerts
```

### 2. Investigating Alerts
```
Alerts (Ctrl+2) → Filter by Critical → Click Alert → Review Details → Back
```

### 3. Searching for Specific Threat
```
Alerts → Search Box → Type "SQL Injection" → Review Results
```

### 4. Monitoring Active Ingestion
```
Dashboard → Watch Activity Feed → Check Status Bar → Review Metrics
```

### 5. Quick Navigation
```
Ctrl+1 (Dashboard) → Ctrl+2 (Alerts) → Click Alert → Ctrl+1 (Back to Dashboard)
```

---

## ⚠️ Troubleshooting

### No Alerts Appearing

**Check:**
1. Status Bar → Pipeline should be 🟢 Active
2. Status Bar → Ingestion should be 🔵 Active
3. Dashboard → Activity Feed for errors
4. Alerts → Empty state message for guidance

**Solutions:**
- If "Pipeline not active": Run `python scripts/train_models.py`
- If "No sources": Upload logs via Dashboard
- If "Ingestion stopped": Restart application

### Limited Permissions

**Symptom:** 🟡 Admin indicator shows "Limited"

**Impact:** Cannot access Windows system logs

**Solution:** 
- Run as Administrator for full access
- Or continue with user-provided logs only

### Kill Switch Active

**Symptom:** 🔴 Kill Switch indicator shows "ACTIVE"

**Impact:** All ML processing halted

**Solution:**
1. Check `config/kill_switch.yaml`
2. Set `enabled: false`
3. Restart application

### Slow Performance

**Check:**
1. Alert count (if >500, consider filtering)
2. Buffer indicator (if near max, wait for processing)
3. System resources (4GB+ RAM recommended)

**Solutions:**
- Use Priority filter to reduce visible alerts
- Use Search to narrow results
- Close other applications

---

## 💡 Pro Tips

### Efficiency
- **Use keyboard shortcuts** instead of clicking
- **Filter before searching** for faster results
- **Watch status bar** instead of checking logs
- **Use F5** to refresh current view quickly

### Alert Management
- **Start with Critical** filter to prioritize
- **Search by IP** to track specific sources
- **Check confidence** before taking action
- **Read reasoning** to understand detection

### Monitoring
- **Keep Dashboard visible** for overview
- **Watch activity feed** for real-time events
- **Monitor buffer** to prevent drops
- **Check ingestion** to ensure processing

### Investigation
- **Review all metrics** before deciding
- **Compare anomaly vs risk** scores
- **Check network info** for context
- **Follow suggested actions** as starting point

---

## 📈 Understanding Metrics

### Confidence Score
- **>80%**: High confidence - likely true positive
- **60-80%**: Medium confidence - investigate further
- **<60%**: Low confidence - may be false positive

### Anomaly Score
- **>0.7**: Highly unusual behavior
- **0.5-0.7**: Moderately unusual
- **<0.5**: Slightly unusual

### Risk Score
- **>0.8**: Critical risk - immediate action
- **0.6-0.8**: High risk - urgent investigation
- **0.4-0.6**: Medium risk - review soon
- **<0.4**: Low risk - monitor

### Priority Levels
- **Critical**: Active attack or severe vulnerability
- **High**: Suspicious activity requiring investigation
- **Medium**: Anomalous behavior worth reviewing
- **Low**: Minor deviation from baseline

---

## 🔄 Real-Time Updates

### Automatic Refresh
- **Status Bar**: Every 1 second
- **Dashboard**: Every 1.5 seconds
- **Alerts**: Every 2 seconds (incremental)

### Manual Refresh
- Press **F5** in any view
- Click **🔄** button in Alerts view
- Click **🔄 Refresh** in Dashboard

### Scroll Preservation
Alerts table **preserves scroll position** during automatic refresh - no jump to top!

---

## 🎨 Visual Indicators

### Status Dots
- 🟢 **Green**: Healthy/Active/Enabled
- 🔵 **Blue**: Processing/Active
- 🟡 **Yellow**: Warning/Limited/Loading
- 🔴 **Red**: Critical/Error/Stopped
- ⚪ **Gray**: Inactive/Idle/Disabled

### Card Colors
- **Blue gradient**: Total/Overview metrics
- **Red gradient**: Critical alerts
- **Orange gradient**: High priority
- **Yellow gradient**: Medium priority

### Text Colors
- **Cyan (#00d4ff)**: Primary accent, active items
- **White**: Normal text
- **Gray**: Secondary text, labels
- **Green**: Success, healthy status
- **Red**: Errors, critical items
- **Orange**: Warnings, high priority

---

## 📞 Getting Help

### In-App
1. Check empty state messages for guidance
2. Hover over status indicators for tooltips
3. Review activity feed for recent events

### Documentation
- `README.md` - Setup and installation
- `UI_OPTIMIZATION_SUMMARY.md` - Technical details
- This file - Quick reference

### Troubleshooting
1. Check status bar for system state
2. Review activity feed for errors
3. Verify logs in `logs/` directory
4. Run `python check_requirements.py`

---

## 🎓 Training Scenarios

### Scenario 1: First-Time User
1. Launch app (Dashboard appears)
2. Click "📁 Upload Logs"
3. Select sample log file
4. Watch activity feed
5. Press Ctrl+2 when alerts appear
6. Click first alert
7. Review investigation details
8. Press ← Back button

### Scenario 2: Daily Monitoring
1. Launch app
2. Check Dashboard metrics
3. Press Ctrl+2 for Alerts
4. Filter by Critical
5. Investigate each critical alert
6. Document findings
7. Monitor status bar throughout

### Scenario 3: Incident Response
1. Receive alert notification
2. Press Ctrl+2 (Alerts)
3. Search for specific IP/classification
4. Click matching alert
5. Review confidence and risk scores
6. Follow suggested action
7. Document in external system

---

**Remember:** The UI updates in real-time - no need to constantly refresh! 🎉
