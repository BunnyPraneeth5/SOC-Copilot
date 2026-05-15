# Production Readiness Checklist

Use this before publishing or deploying SOC Copilot in a real environment.

## Model Trust

- Train or approve model artifacts from trusted datasets.
- Generate `data/models/model_hashes.json` from the final model files.
- Run with `SOC_COPILOT_STRICT_MODEL_INTEGRITY=true`.
- Verify tampered or missing model files fail to load.

## Offline And Online Mode

- Keep `SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT=false` for offline or air-gapped deployments.
- Enable online enrichment only after approving data sharing with AbuseIPDB, VirusTotal, Shodan, WHOIS, or geo-IP providers.
- Store API keys outside the repo using environment variables or a managed secret store.

## Log Privacy

- Define retention for raw logs, usernames, IPs, hostnames, and file paths.
- Restrict access to `data/`, `logs/`, model files, and governance/audit data.
- Decide whether local storage requires encryption-at-rest.

## Detection Quality

- Test with representative Windows Event Logs, syslog, firewall, authentication, endpoint, and application logs.
- Measure false positives, false negatives, precision, recall, and analyst usefulness.
- Tune thresholds and deduplication windows for the target environment.

## Release

- Build installers/executables from a clean environment.
- Verify least-privilege operation and admin-mode behavior.
- Run focused security tests and dependency/CVE scans.
- Review license compatibility for datasets, model files, dependencies, and generated artifacts.
