# System Logs Directory

This directory contains system logs exported by external PowerShell scripts.

## Files

- `windows_security.log` - Windows Security Event Logs
- `windows_system.log` - Windows System Event Logs

## How Logs Are Created

**IMPORTANT**: SOC Copilot does NOT create these files directly.

External PowerShell exporters write to these files:
- `scripts/exporters/export_windows_security.ps1`
- `scripts/exporters/export_windows_system.ps1`

## Usage

1. Start exporters (in separate terminals):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\exporters\export_windows_security.ps1
   powershell -ExecutionPolicy Bypass -File scripts\exporters\export_windows_system.ps1
   ```

2. Enable SOC Copilot ingestion:
   ```bash
   soc-copilot system-logs enable --actor "your_name"
   ```

3. Logs will be read by SOC Copilot's ingestion engine

## Architecture

```
Windows Event Logs
        ↓
External Exporter (PowerShell)
        ↓
This Directory (Plain Text Files)
        ↓
SOC Copilot Ingestion Engine
        ↓
Detection → Alerts → UI
```

## See Also

- `docs/SPRINT17_SYSTEM_LOGS_MANUAL.md` - User manual
- `docs/SPRINT17_SECURITY_JUSTIFICATION.md` - Architecture rationale
- `config/ingestion/system_logs.yaml` - Configuration
