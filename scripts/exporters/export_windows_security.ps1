# Windows Security Event Log Exporter
# Sprint-17: System Log Ingestion
#
# PURPOSE: Export Windows Security Event Logs to file for SOC Copilot ingestion
# ARCHITECTURE: OS Logs → This Script → File → SOC Copilot
#
# USAGE:
#   powershell -ExecutionPolicy Bypass -File export_windows_security.ps1
#
# CONFIGURATION:
#   $OutputFile: Where to write logs (must match config/ingestion/system_logs.yaml)
#   $IntervalSeconds: How often to export (default: 5 seconds)
#   $MaxEvents: Maximum events per export (default: 100)

param(
    [string]$OutputFile = "logs\system\windows_security.log",
    [int]$IntervalSeconds = 5,
    [int]$MaxEvents = 100
)

# Ensure output directory exists
$OutputDir = Split-Path -Parent $OutputFile
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

Write-Host "Windows Security Event Log Exporter"
Write-Host "===================================="
Write-Host "Output File: $OutputFile"
Write-Host "Interval: $IntervalSeconds seconds"
Write-Host "Max Events: $MaxEvents"
Write-Host ""
Write-Host "Press Ctrl+C to stop"
Write-Host ""

# Track last event time
$LastEventTime = (Get-Date).AddSeconds(-$IntervalSeconds)

while ($true) {
    try {
        # Get new security events since last check
        $Events = Get-WinEvent -FilterHashtable @{
            LogName = 'Security'
            StartTime = $LastEventTime
        } -MaxEvents $MaxEvents -ErrorAction SilentlyContinue
        
        if ($Events) {
            # Reverse to chronological order
            $Events = $Events | Sort-Object TimeCreated
            
            # Export to file (append mode)
            foreach ($Event in $Events) {
                $LogLine = "{0}|EventID={1}|Level={2}|Message={3}" -f `
                    $Event.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss"), `
                    $Event.Id, `
                    $Event.LevelDisplayName, `
                    ($Event.Message -replace "`r`n", " " -replace "`n", " ")
                
                Add-Content -Path $OutputFile -Value $LogLine
            }
            
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Exported $($Events.Count) events"
            
            # Update last event time
            $LastEventTime = ($Events | Select-Object -Last 1).TimeCreated
        }
        
    } catch {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Error: $_" -ForegroundColor Red
    }
    
    # Wait for next interval
    Start-Sleep -Seconds $IntervalSeconds
}
