# Sprint-13 Governance Quick Reference

## Overview
Sprint-13 implements a Governance & Control Layer for the SOC Copilot system.
This is INFRASTRUCTURE ONLY - no learning, authority, or automation is enabled.

## Default State
- **Authority State**: DISABLED
- **Kill Switch**: ENABLED (Phase-3 disabled)
- **Permitted Components**: None
- **Approval Workflow**: Manual only

## CLI Commands

### Check Governance Status
```bash
python -m soc_copilot.cli governance status
```
Shows:
- Kill switch state
- Phase-3 status
- Authority state
- Permitted components
- Approval request count
- Audit event count

### Create Approval Request
```bash
python -m soc_copilot.cli governance request \
  --action "ACTION_NAME" \
  --reason "JUSTIFICATION" \
  --requester "YOUR_NAME"
```
Creates a new approval request in REQUESTED state.

### Approve Request
```bash
python -m soc_copilot.cli governance approve \
  --request-id "REQUEST_ID" \
  --reviewer "REVIEWER_NAME" \
  --notes "OPTIONAL_NOTES"
```
**IMPORTANT**: Approval does NOT activate anything. Manual implementation required.

### Reject Request
```bash
python -m soc_copilot.cli governance reject \
  --request-id "REQUEST_ID" \
  --reviewer "REVIEWER_NAME" \
  --notes "REJECTION_REASON"
```

### Revoke Approved Request
```bash
python -m soc_copilot.cli governance revoke \
  --request-id "REQUEST_ID" \
  --reviewer "REVIEWER_NAME" \
  --notes "REVOCATION_REASON"
```

### Enable Kill Switch (Disable Phase-3)
```bash
python -m soc_copilot.cli governance disable \
  --actor "YOUR_NAME" \
  --reason "EMERGENCY_REASON"
```
Immediately disables all Phase-3 functionality.

### Disable Kill Switch (Enable Phase-3)
```bash
python -m soc_copilot.cli governance enable \
  --actor "YOUR_NAME" \
  --reason "AUTHORIZATION_REASON"
```
Enables Phase-3 functionality (requires explicit authorization).

## Python API

### Check Policy State
```python
from soc_copilot.phase3.governance import GovernancePolicy

policy = GovernancePolicy("config/governance/policy.yaml")
print(f"State: {policy.current_state.value}")
print(f"Permitted: {policy.get_permitted_components()}")
```

### Check Kill Switch
```python
from soc_copilot.phase3.governance import KillSwitch

killswitch = KillSwitch("data/governance/governance.db")
if killswitch.is_enabled():
    print("Phase-3 is DISABLED")
else:
    print("Phase-3 is ENABLED")
```

### Manual Approval Workflow
```python
from soc_copilot.phase3.governance import ApprovalWorkflow, AuditLogger

workflow = ApprovalWorkflow("data/governance/governance.db")
audit = AuditLogger("data/governance/governance.db")

# Create request
request = workflow.create_request(
    request_id="req-001",
    requester="analyst1",
    action="enable_monitoring",
    reason="Need monitoring capability"
)
audit.log_event("analyst1", "request_created", "Monitoring request")

# Approve (NO automatic activation)
approved = workflow.approve_request(
    request_id="req-001",
    reviewer="manager1",
    notes="Approved"
)
audit.log_event("manager1", "request_approved", "Approved")
```

### Audit Logging
```python
from soc_copilot.phase3.governance import AuditLogger

audit = AuditLogger("data/governance/governance.db")

# Log event
event = audit.log_event(
    actor="user1",
    action="config_change",
    reason="Updated threshold"
)

# Retrieve events
events = audit.get_events(limit=10)
for event in events:
    print(f"{event.timestamp}: {event.actor} - {event.action}")
```

## Authority States

### DISABLED (Default)
- No components permitted
- All Phase-3 functionality inactive
- Safest state

### OBSERVE_ONLY
- Logging permitted
- Monitoring permitted
- No recommendations or actions

### ADVISORY_ONLY
- Logging permitted
- Monitoring permitted
- Recommendations permitted
- No automatic actions

## Safety Guarantees

1. **Default DISABLED**: All authority states default to DISABLED
2. **Manual Only**: All operations require explicit human action
3. **Kill Switch Priority**: Kill switch overrides all permissions
4. **Append-Only Audit**: Audit log cannot be modified or deleted
5. **No Automation**: Approvals do NOT trigger automatic execution
6. **Phase Isolation**: No imports from Phase-1 or Phase-2
7. **Persistent State**: Kill switch state persists across restarts

## Database Location
```
data/governance/governance.db
```
Separate from Phase-1/Phase-2 databases.

## Configuration
```
config/governance/policy.yaml
```
YAML-driven policy configuration.

## Testing
```bash
# Run governance tests
python -m pytest tests/unit/test_governance_sprint13.py -v

# Run verification script
python scripts/verify_sprint13.py
```

## Important Notes

1. **Approval ≠ Activation**: Approving a request does NOT automatically activate anything. Manual implementation is required.

2. **Kill Switch Priority**: When kill switch is enabled, Phase-3 is disabled regardless of approvals or authority state.

3. **Audit Trail**: All governance operations are logged in the append-only audit log.

4. **No Learning**: Sprint-13 does NOT implement any learning, training, or model updates.

5. **Infrastructure Only**: This sprint provides governance infrastructure. Future sprints may add execution logic (requires separate approval).

## Troubleshooting

### Check if Phase-3 is enabled
```bash
python -m soc_copilot.cli governance status
```
Look for "Phase-3 Status" in output.

### View audit trail
```python
from soc_copilot.phase3.governance import AuditLogger

audit = AuditLogger("data/governance/governance.db")
events = audit.get_events(limit=50)
for e in events:
    print(f"{e.timestamp}: {e.actor} - {e.action} - {e.reason}")
```

### Reset to default state
```bash
# Enable kill switch (disable Phase-3)
python -m soc_copilot.cli governance disable \
  --actor "admin" \
  --reason "Reset to default"
```

## Next Steps (NOT PART OF SPRINT-13)

Sprint-13 provides infrastructure only. Future work may include:
- Implementing override/rollback execution logic
- Adding authority state transitions
- Integrating with Phase-1/Phase-2
- Enabling learning mechanisms

**All future work requires separate approval and review.**
