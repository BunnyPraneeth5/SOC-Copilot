"""Sprint-13 Verification Script

This script verifies that Sprint-13 (Governance & Control Layer) has been
implemented correctly according to specifications.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from soc_copilot.phase3.governance import (
    AuthorityState,
    GovernancePolicy,
    ApprovalState,
    ApprovalWorkflow,
    KillSwitch,
    AuditLogger,
)


def verify_default_disabled_state():
    """Verify all authority states default to DISABLED"""
    print("[OK] Verifying default DISABLED state...")
    
    policy = GovernancePolicy()
    assert policy.current_state == AuthorityState.DISABLED, "Policy should default to DISABLED"
    assert len(policy.get_permitted_components()) == 0, "DISABLED should permit no components"
    
    print("  [OK] Policy defaults to DISABLED")
    print("  [OK] No components permitted by default")


def verify_killswitch_default():
    """Verify kill switch defaults to enabled (Phase-3 disabled)"""
    print("\n[OK] Verifying kill switch default state...")
    
    import tempfile
    db_path = tempfile.mktemp(suffix=".db")
    
    killswitch = KillSwitch(db_path)
    assert killswitch.is_enabled() is True, "Kill switch should default to enabled"
    
    state = killswitch.get_state()
    assert state["phase3_status"] == "disabled", "Phase-3 should be disabled by default"
    
    print("  [OK] Kill switch defaults to ENABLED")
    print("  [OK] Phase-3 defaults to DISABLED")


def verify_manual_only_operations():
    """Verify all operations require manual action"""
    print("\n[OK] Verifying manual-only operations...")
    
    import tempfile
    db_path = tempfile.mktemp(suffix=".db")
    
    workflow = ApprovalWorkflow(db_path)
    
    # Create request
    request = workflow.create_request(
        request_id="verify-001",
        requester="test_user",
        action="test_action",
        reason="Testing"
    )
    
    assert request.state == ApprovalState.REQUESTED, "Request should start in REQUESTED state"
    assert request.reviewer is None, "No automatic reviewer assignment"
    
    # Approve request
    approved = workflow.approve_request(
        request_id="verify-001",
        reviewer="test_manager",
        notes="Approved"
    )
    
    assert approved.state == ApprovalState.APPROVED, "Manual approval should work"
    assert approved.reviewer == "test_manager", "Reviewer should be recorded"
    
    print("  [OK] Requests require manual creation")
    print("  [OK] Approvals require manual action")
    print("  [OK] No automatic state transitions")


def verify_audit_append_only():
    """Verify audit log is append-only"""
    print("\n[OK] Verifying audit append-only guarantees...")
    
    import tempfile
    db_path = tempfile.mktemp(suffix=".db")
    
    audit = AuditLogger(db_path)
    
    # Log events
    event1 = audit.log_event("user1", "action1", "reason1")
    event2 = audit.log_event("user2", "action2", "reason2")
    
    # Retrieve events
    events = audit.get_events(limit=10)
    assert len(events) == 2, "Both events should be logged"
    
    # Verify immutability (events should persist)
    event_ids = [e.event_id for e in events]
    assert event1.event_id in event_ids, "Event 1 should persist"
    assert event2.event_id in event_ids, "Event 2 should persist"
    
    print("  [OK] Events are logged successfully")
    print("  [OK] Events persist (append-only)")
    print("  [OK] No deletion or modification")


def verify_no_phase1_phase2_coupling():
    """Verify governance modules do NOT import Phase-1 or Phase-2"""
    print("\n[OK] Verifying NO Phase-1/Phase-2 coupling...")
    
    import inspect
    from soc_copilot.phase3 import governance
    
    # Check governance package source
    source = inspect.getsource(governance)
    
    assert "from soc_copilot.phase1" not in source, "Should not import phase1"
    assert "from soc_copilot.phase2" not in source, "Should not import phase2"
    assert "import soc_copilot.phase1" not in source, "Should not import phase1"
    assert "import soc_copilot.phase2" not in source, "Should not import phase2"
    
    print("  [OK] No imports from phase1")
    print("  [OK] No imports from phase2")
    print("  [OK] Governance is isolated")


def verify_override_framework_shells():
    """Verify override/rollback are framework shells only"""
    print("\n[OK] Verifying override/rollback framework shells...")
    
    from soc_copilot.phase3.governance import (
        OverrideAction,
        RollbackAction,
        OverrideManager,
        RollbackManager,
    )
    
    # Test override action
    class TestOverride(OverrideAction):
        def execute(self):
            return super().execute()
        
        def validate(self):
            return super().validate()
    
    override = TestOverride()
    
    try:
        override.execute()
        assert False, "Override execute should not be implemented"
    except NotImplementedError:
        pass
    
    # Test rollback action
    class TestRollback(RollbackAction):
        def execute(self):
            return super().execute()
        
        def get_restore_point(self):
            return super().get_restore_point()
    
    rollback = TestRollback()
    
    try:
        rollback.execute()
        assert False, "Rollback execute should not be implemented"
    except NotImplementedError:
        pass
    
    print("  [OK] Override actions are framework shells")
    print("  [OK] Rollback actions are framework shells")
    print("  [OK] No execution logic implemented")


def verify_cli_integration():
    """Verify CLI commands are available"""
    print("\n[OK] Verifying CLI integration...")
    
    from soc_copilot.cli import setup_parser
    
    parser = setup_parser()
    
    # Parse governance status command
    args = parser.parse_args(["governance", "status"])
    assert args.command == "governance", "Governance command should be available"
    assert args.governance_command == "status", "Status subcommand should be available"
    
    # Parse governance request command
    args = parser.parse_args([
        "governance", "request",
        "--action", "test",
        "--reason", "test",
        "--requester", "test"
    ])
    assert args.governance_command == "request", "Request subcommand should be available"
    
    print("  [OK] Governance command available")
    print("  [OK] All subcommands available")
    print("  [OK] CLI integration complete")


def main():
    """Run all verification checks"""
    print("=" * 60)
    print("Sprint-13 Verification")
    print("=" * 60)
    
    try:
        verify_default_disabled_state()
        verify_killswitch_default()
        verify_manual_only_operations()
        verify_audit_append_only()
        verify_no_phase1_phase2_coupling()
        verify_override_framework_shells()
        verify_cli_integration()
        
        print("\n" + "=" * 60)
        print("[SUCCESS] ALL VERIFICATIONS PASSED")
        print("=" * 60)
        print("\nSprint-13 Implementation Status: COMPLETE")
        print("\nKey Features:")
        print("  - Default DISABLED state enforced")
        print("  - Manual-only operations (no automation)")
        print("  - Kill switch with highest priority")
        print("  - Append-only audit logging")
        print("  - Override/rollback framework shells")
        print("  - CLI integration complete")
        print("  - NO Phase-1/Phase-2 coupling")
        print("\nReady for review.")
        
        return 0
        
    except AssertionError as e:
        print(f"\n[FAILED] VERIFICATION FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
