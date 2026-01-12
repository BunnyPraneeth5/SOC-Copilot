# User Manual: Real-Time System Log Ingestion

**Sprint-17: System Log Ingestion**  
**Target OS**: Windows

---

## 📋 Overview

SOC Copilot can ingest real-time Windows system logs using a **safe, decoupled architecture**:

```
Windows Event Logs → External Exporter → Log Files → SOC Copilot
```

**IMPORTANT**: SOC Copilot does NOT read Windows Event Logs directly. External PowerShell exporters write logs to files, and SOC Copilot reads those files.

---

## 🚀 Quick Start

### Step 1: Start External Exporters

Open **two PowerShell terminals** (as Administrator if needed):

**Terminal 1 - Security Logs**:
```powershell
cd "C:\Users\karup\projects\SOC Copilot"
powershell -ExecutionPolicy Bypass -File scripts\exporters\export_windows_security.ps1
```

**Terminal 2 - System Logs**:
```powershell
cd "C:\Users\karup\projects\SOC Copilot"
powershell -ExecutionPolicy Bypass -File scripts\exporters\export_windows_system.ps1
```

### Step 2: Enable SOC Copilot Ingestion

```bash
python -m soc_copilot.cli system-logs enable --actor "your_name"
```

### Step 3: Verify Status

```bash
python -m soc_copilot.cli system-logs status
```

### Step 4: Launch UI

```bash
python launch_ui.py
```

System-generated alerts will appear in the Alerts view with `source=system` tag.

---

## 🔧 Configuration

### Configuration File

**Location**: `config/ingestion/system_logs.yaml`

```yaml
# Enable/disable system log ingestion
enabled: false

# Export interval (for external exporter reference)
export_interval: 5

# Log types to ingest
log_types:
  - windows_security
  - windows_system

# File paths (where external exporters write)
file_paths:
  windows_security: "logs/system/windows_security.log"
  windows_system: "logs/system/windows_system.log"

# Micro-batch configuration
max_batch_size: 100
batch_interval: 5.0

# Governance
enforce_killswitch: true
```

### Customizing Export Paths

If you change file paths in `system_logs.yaml`, you must also update the exporter scripts:

**In `export_windows_security.ps1`**:
```powershell
param(
    [string]$OutputFile = "your/custom/path.log",
    ...
)
```

---

## 📜 CLI Commands

### Show Status

```bash
soc-copilot system-logs status
```

**Output**:
```
System Log Ingestion Status
============================================================

Enabled: false
Export Interval: 5s (for external exporter)
Batch Interval: 5.0s
Killswitch Enforcement: true

Log Types:
  - windows_security
  - windows_system

File Paths (written by external exporters):
  ✓ windows_security: logs/system/windows_security.log
  ✗ windows_system: logs/system/windows_system.log

NOTE: SOC Copilot does NOT read OS logs directly.
      External exporters must write to the above file paths.
```

### Enable Ingestion

```bash
soc-copilot system-logs enable --actor "analyst_name"
```

**Output**:
```
System log ingestion ENABLED
  Actor: analyst_name

NOTE: This only enables SOC Copilot ingestion.
      External exporters must be started separately.
```

### Disable Ingestion

```bash
soc-copilot system-logs disable --actor "analyst_name"
```

---

## 🛡️ Security & Governance

### Killswitch Enforcement

Every ingestion batch checks the governance kill switch:

```bash
# Enable kill switch (disables all Phase-3 operations)
soc-copilot governance disable --actor "admin" --reason "Emergency stop"
```

When kill switch is enabled:
- ✅ Ingestion batches are dropped immediately
- ✅ No processing occurs
- ✅ No bypass mechanism

### Audit Logging

All system log operations are audit-logged:

```bash
soc-copilot governance status
```

View audit events in `data/governance/governance.db`.

---

## 🔍 Troubleshooting

### Exporter Not Writing Logs

**Symptom**: `soc-copilot system-logs status` shows `✗` for file paths

**Solution**:
1. Verify exporter is running (check PowerShell terminal)
2. Check exporter has permissions to write to output directory
3. Verify output path matches `system_logs.yaml` configuration

### No Alerts Generated

**Symptom**: Exporters running, ingestion enabled, but no alerts

**Possible Causes**:
1. **Kill switch enabled**: Check `soc-copilot governance status`
2. **No events**: Windows may not be generating events
3. **Parsing issues**: Check logs for parsing errors

**Solution**:
```bash
# Check governance status
soc-copilot governance status

# Verify ingestion status
soc-copilot system-logs status

# Check if files are being written
dir logs\system\
```

### Permission Denied

**Symptom**: Exporter fails with "Access Denied"

**Solution**:
- Run PowerShell as Administrator
- Verify user has permission to read Windows Event Logs
- Check output directory write permissions

---

## 📊 Monitoring

### Exporter Output

Exporters display real-time status:

```
Windows Security Event Log Exporter
====================================
Output File: logs\system\windows_security.log
Interval: 5 seconds
Max Events: 100

Press Ctrl+C to stop

[14:23:15] Exported 12 events
[14:23:20] Exported 8 events
[14:23:25] Exported 15 events
```

### Log File Format

**Security Logs**:
```
2024-01-15 14:23:15|EventID=4624|Level=Information|Message=An account was successfully logged on
```

**System Logs**:
```
2024-01-15 14:23:16|EventID=7036|Level=Information|Source=Service Control Manager|Message=Service entered running state
```

---

## 🎯 Best Practices

### 1. Start Exporters Before Enabling Ingestion

```bash
# 1. Start exporters first
powershell -File scripts\exporters\export_windows_security.ps1

# 2. Then enable ingestion
soc-copilot system-logs enable --actor "analyst"
```

### 2. Monitor Exporter Health

Keep exporter terminals visible to monitor for errors.

### 3. Regular Log Rotation

Exported log files grow over time. Implement log rotation:

```powershell
# Example: Archive old logs
Move-Item logs\system\windows_security.log logs\system\archive\windows_security_$(Get-Date -Format 'yyyyMMdd').log
```

### 4. Test with Sample Events

Generate test events to verify pipeline:

```powershell
# Generate test security event
eventcreate /T INFORMATION /ID 999 /L SECURITY /SO "SOC_Test" /D "Test event for SOC Copilot"
```

---

## 🚫 What SOC Copilot Does NOT Do

❌ Read Windows Event Logs directly  
❌ Require elevated privileges  
❌ Install background services  
❌ Modify OS configuration  
❌ Auto-start exporters  
❌ Manage exporter lifecycle

---

## ✅ What SOC Copilot DOES Do

✅ Read log files written by external exporters  
✅ Apply ML detection to system logs  
✅ Generate alerts for suspicious activity  
✅ Enforce governance kill switch  
✅ Audit all operations  
✅ Display alerts in UI

---

## 📞 Support

For issues or questions:

1. Check `docs/SPRINT17_SUMMARY.md` for implementation details
2. Review `docs/SPRINT17_SECURITY_JUSTIFICATION.md` for architecture rationale
3. Run unit tests: `python -m pytest tests/unit/test_system_logs_sprint17.py -v`

---

## 🎓 Architecture Explanation

### Why External Exporters?

SOC Copilot follows **industry-standard decoupled architecture**:

- **Splunk**: Uses forwarders to collect logs
- **Elastic**: Uses Beats agents to ship logs
- **Sentinel**: Uses connectors to ingest logs
- **CrowdStrike**: Uses sensors to collect telemetry

**Benefits**:
- ✅ Security: No elevated privileges needed
- ✅ Stability: No OS hooks that can crash
- ✅ Portability: Easy to support multiple OS
- ✅ Testability: File-based ingestion is testable
- ✅ Governance: Independent control of collection vs analysis

---

## 📝 Example Workflow

```bash
# 1. Start exporters (in separate terminals)
powershell -File scripts\exporters\export_windows_security.ps1
powershell -File scripts\exporters\export_windows_system.ps1

# 2. Enable ingestion
soc-copilot system-logs enable --actor "john_doe"

# 3. Verify status
soc-copilot system-logs status

# 4. Launch UI
python launch_ui.py

# 5. Monitor alerts in UI
# System alerts will have source=system tag

# 6. When done, disable ingestion
soc-copilot system-logs disable --actor "john_doe"

# 7. Stop exporters (Ctrl+C in exporter terminals)
```

---

**End of User Manual**
