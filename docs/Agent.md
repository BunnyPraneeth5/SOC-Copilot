# SOC Copilot — Antigravity Agent Config

## Mission context

You are building the MCP agentic investigation layer for SOC Copilot —
a production-grade, offline Windows SIEM/IDS desktop application.
The existing codebase has: PyQt6 UI, Isolation Forest + Random Forest ML models
(99.88% accuracy on CICIDS2017, 84 features), FastAPI backend, SQLite alert store.

## Your primary task

Implement the full MCP pipeline so that when an analyst clicks an IP or domain
in the alert table, it triggers an automated threat investigation using 4 agents.

## Agent pipeline (build in this order)

1. ReconAgent      — WHOIS, reverse DNS, ASN lookup, geo-IP (use ipwhois + httpx)
2. ReputationAgent — AbuseIPDB confidence score + VirusTotal detection ratio (async)
3. ShodanAgent     — open ports, service banners, known CVEs (use shodan library)
4. ReportAgent     — aggregates all 3 outputs, calls Anthropic claude-sonnet-4-20250514,
                     returns structured ThreatReport with severity (CRITICAL/HIGH/MEDIUM/LOW)

## Orchestrator behaviour

- Class: MCPOrchestrator in soc_copilot/mcp/orchestrator.py
- Run agents 1–3 in parallel: asyncio.gather(recon, reputation, shodan)
- Timeout per agent: 10 seconds
- If an agent fails, include partial results (don't abort the whole pipeline)
- Cache results: diskcache, TTL 6 hours, key format "ip:<value>"
- Emit Qt signals back to the UI thread (never call PyQt6 from async thread directly)

## PyQt6 integration

- The alert table uses QTableWidget
- Connect: table.itemDoubleClicked.connect(self.on_alert_click)
- on_alert_click must extract IP from column 2 (or domain from column 3)
- Use QThreadPool + QRunnable to run the asyncio event loop off the main thread
- Emit a custom reportReady(ThreatReport) signal when done

## Report Agent prompt (use this exact system prompt for Claude API)
