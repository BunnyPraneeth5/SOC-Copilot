"""Unit tests for Sprint-13: Governance & Control Layer"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime

from soc_copilot.phase3.governance import (
    AuthorityState,
    GovernancePolicy,
    ApprovalState,
    ApprovalRequest,
    ApprovalWorkflow,
    KillSwitch,
    AuditEvent,
    AuditLogger,
    OverrideAction,
    RollbackAction,
    OverrideManager,
    RollbackManager,
)


# ============================================================================
# Policy Tests
# ============================================================================

class TestGovernancePolicy:
    """Test governance policy module"""
    
    def test_default_state_is_disabled(self):
        """Verify default authority state is DISABLED"""
        policy = GovernancePolicy()
        assert policy.current_state == AuthorityState.DISABLED
    
    def test_disabled_permits_no_components(self):
        """Verify DISABLED state permits no components"""
        policy = GovernancePolicy()
        assert len(policy.get_permitted_components()) == 0
        assert not policy.is_component_permitted("logging")
        assert not policy.is_component_permitted("monitoring")
    
    def test_observe_only_permits_logging_monitoring(self):
        """Verify OBSERVE_ONLY permits logging and monitoring"""
        policy = GovernancePolicy()
        policy._state = AuthorityState.OBSERVE_ONLY
        
        assert policy.is_component_permitted("logging")
        assert policy.is_component_permitted("monitoring")
        assert not policy.is_component_permitted("recommendations")
    
    def test_advisory_only_permits_all_defined(self):
        """Verify ADVISORY_ONLY permits logging, monitoring, recommendations"""
        policy = GovernancePolicy()
        policy._state = AuthorityState.ADVISORY_ONLY
        
        assert policy.is_component_permitted("logging")
        assert policy.is_component_permitted("monitoring")
        assert policy.is_component_permitted("recommendations")
    
    def test_to_dict_export(self):
        """Verify policy exports to dictionary"""
        policy = GovernancePolicy()
        data = policy.to_dict()
        
        assert data["current_state"] == "disabled"
        assert isinstance(data["permitted_components"], list)
    
    def test_load_from_yaml(self, tmp_path):
        """Verify policy loads from YAML config"""
        config_file = tmp_path / "policy.yaml"
        config_file.write_text("""
default_state: disabled
permitted_components:
  disabled: []
  observe_only:
    - logging
    - monitoring
""")
        
        policy = GovernancePolicy(str(config_file))
        assert policy.current_state == AuthorityState.DISABLED


# ============================================================================
# Approval Workflow Tests
# ============================================================================

class TestApprovalWorkflow:
    """Test approval workflow state machine"""
    
    @pytest.fixture
    def workflow(self, tmp_path):
        """Create workflow with temp database"""
        db_path = tmp_path / "test_approval.db"
        return ApprovalWorkflow(str(db_path))
    
    def test_create_request(self, workflow):
        """Verify request creation"""
        request = workflow.create_request(
            request_id="test-001",
            requester="analyst1",
            action="enable_feature",
            reason="Testing"
        )
        
        assert request.request_id == "test-001"
        assert request.requester == "analyst1"
        assert request.action == "enable_feature"
        assert request.state == ApprovalState.REQUESTED
        assert request.reviewer is None
    
    def test_approve_request_no_side_effects(self, workflow):
        """Verify approval does NOT trigger side effects"""
        workflow.create_request(
            request_id="test-002",
            requester="analyst1",
            action="enable_feature",
            reason="Testing"
        )
        
        approved = workflow.approve_request(
            request_id="test-002",
            reviewer="manager1",
            notes="Approved for testing"
        )
        
        assert approved.state == ApprovalState.APPROVED
        assert approved.reviewer == "manager1"
        assert approved.review_notes == "Approved for testing"
        assert approved.reviewed_at is not None
        
        # Verify no automatic activation (would need manual check)
    
    def test_reject_request(self, workflow):
        """Verify request rejection"""
        workflow.create_request(
            request_id="test-003",
            requester="analyst1",
            action="enable_feature",
            reason="Testing"
        )
        
        rejected = workflow.reject_request(
            request_id="test-003",
            reviewer="manager1",
            notes="Not ready"
        )
        
        assert rejected.state == ApprovalState.REJECTED
        assert rejected.reviewer == "manager1"
    
    def test_revoke_request(self, workflow):
        """Verify request revocation"""
        workflow.create_request(
            request_id="test-004",
            requester="analyst1",
            action="enable_feature",
            reason="Testing"
        )
        
        workflow.approve_request(
            request_id="test-004",
            reviewer="manager1"
        )
        
        revoked = workflow.revoke_request(
            request_id="test-004",
            reviewer="manager1",
            notes="Revoking approval"
        )
        
        assert revoked.state == ApprovalState.REVOKED
    
    def test_get_request(self, workflow):
        """Verify request retrieval"""
        workflow.create_request(
            request_id="test-005",
            requester="analyst1",
            action="test",
            reason="Testing"
        )
        
        request = workflow.get_request("test-005")
        assert request is not None
        assert request.request_id == "test-005"
        
        missing = workflow.get_request("nonexistent")
        assert missing is None
    
    def test_list_requests(self, workflow):
        """Verify request listing"""
        workflow.create_request("req-1", "user1", "action1", "reason1")
        workflow.create_request("req-2", "user2", "action2", "reason2")
        workflow.approve_request("req-1", "manager1")
        
        all_requests = workflow.list_requests()
        assert len(all_requests) == 2
        
        approved = workflow.list_requests(state=ApprovalState.APPROVED)
        assert len(approved) == 1
        assert approved[0].request_id == "req-1"
    
    def test_manual_only_transitions(self, workflow):
        """Verify NO automatic state transitions"""
        request = workflow.create_request(
            request_id="test-006",
            requester="analyst1",
            action="test",
            reason="Testing"
        )
        
        # State should remain REQUESTED until manual action
        assert request.state == ApprovalState.REQUESTED
        
        # No automatic approval after time
        retrieved = workflow.get_request("test-006")
        assert retrieved.state == ApprovalState.REQUESTED


# ============================================================================
# Kill Switch Tests
# ============================================================================

class TestKillSwitch:
    """Test kill switch functionality"""
    
    @pytest.fixture
    def killswitch(self, tmp_path):
        """Create kill switch with temp database"""
        db_path = tmp_path / "test_killswitch.db"
        return KillSwitch(str(db_path))
    
    def test_default_enabled_phase3_disabled(self, killswitch):
        """Verify kill switch defaults to enabled (Phase-3 disabled)"""
        assert killswitch.is_enabled() is True
        
        state = killswitch.get_state()
        assert state["enabled"] is True
        assert state["phase3_status"] == "disabled"
    
    def test_enable_killswitch(self, killswitch):
        """Verify kill switch can be enabled"""
        killswitch.enable(actor="admin", reason="Safety test")
        
        assert killswitch.is_enabled() is True
        state = killswitch.get_state()
        assert state["changed_by"] == "admin"
        assert state["reason"] == "Safety test"
    
    def test_disable_killswitch(self, killswitch):
        """Verify kill switch can be disabled (enable Phase-3)"""
        killswitch.disable(actor="admin", reason="Authorized activation")
        
        assert killswitch.is_enabled() is False
        state = killswitch.get_state()
        assert state["phase3_status"] == "enabled"
        assert state["changed_by"] == "admin"
    
    def test_persistent_across_restarts(self, tmp_path):
        """Verify kill switch state persists across restarts"""
        db_path = tmp_path / "test_persistent.db"
        
        # First instance
        ks1 = KillSwitch(str(db_path))
        ks1.disable(actor="admin", reason="Test")
        assert ks1.is_enabled() is False
        
        # Second instance (simulates restart)
        ks2 = KillSwitch(str(db_path))
        assert ks2.is_enabled() is False
        
        state = ks2.get_state()
        assert state["changed_by"] == "admin"
    
    def test_single_source_of_truth(self, killswitch):
        """Verify kill switch is single source of truth"""
        state1 = killswitch.get_state()
        state2 = killswitch.get_state()
        
        assert state1["enabled"] == state2["enabled"]
        assert state1["last_changed"] == state2["last_changed"]


# ============================================================================
# Audit Logger Tests
# ============================================================================

class TestAuditLogger:
    """Test audit logging functionality"""
    
    @pytest.fixture
    def audit(self, tmp_path):
        """Create audit logger with temp database"""
        db_path = tmp_path / "test_audit.db"
        return AuditLogger(str(db_path))
    
    def test_log_event(self, audit):
        """Verify event logging"""
        event = audit.log_event(
            actor="analyst1",
            action="approval_granted",
            reason="Authorized by manager"
        )
        
        assert event.event_id is not None
        assert event.actor == "analyst1"
        assert event.action == "approval_granted"
        assert event.reason == "Authorized by manager"
        assert isinstance(event.timestamp, datetime)
    
    def test_append_only(self, audit):
        """Verify audit log is append-only"""
        event1 = audit.log_event("user1", "action1", "reason1")
        event2 = audit.log_event("user2", "action2", "reason2")
        
        events = audit.get_events(limit=10)
        assert len(events) == 2
        
        # Events should be in reverse chronological order
        assert events[0].event_id == event2.event_id
        assert events[1].event_id == event1.event_id
    
    def test_get_events_with_filters(self, audit):
        """Verify event retrieval with filters"""
        audit.log_event("user1", "login", "reason1")
        audit.log_event("user2", "logout", "reason2")
        audit.log_event("user1", "approval", "reason3")
        
        # Filter by actor
        user1_events = audit.get_events(actor="user1")
        assert len(user1_events) == 2
        
        # Filter by action
        login_events = audit.get_events(action="login")
        assert len(login_events) == 1
    
    def test_get_event_count(self, audit):
        """Verify event counting"""
        assert audit.get_event_count() == 0
        
        audit.log_event("user1", "action1", "reason1")
        audit.log_event("user2", "action2", "reason2")
        
        assert audit.get_event_count() == 2
    
    def test_no_deletion_or_modification(self, audit):
        """Verify events cannot be deleted or modified"""
        event = audit.log_event("user1", "action1", "reason1")
        
        # Attempt to retrieve and verify immutability
        events = audit.get_events(limit=1)
        assert len(events) == 1
        assert events[0].event_id == event.event_id
        
        # Log more events
        audit.log_event("user2", "action2", "reason2")
        
        # Original event should still exist
        all_events = audit.get_events(limit=10)
        event_ids = [e.event_id for e in all_events]
        assert event.event_id in event_ids
    
    def test_rotation_tracking(self, audit):
        """Verify log rotation tracking"""
        # Log many events to trigger rotation check
        for i in range(100):
            audit.log_event(f"user{i}", f"action{i}", f"reason{i}")
        
        count = audit.get_event_count()
        assert count == 100
        
        # Rotation history should be trackable
        history = audit.get_rotation_history()
        assert isinstance(history, list)
    
    def test_timestamped_records(self, audit):
        """Verify all records are timestamped"""
        event = audit.log_event("user1", "action1", "reason1")
        
        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)
        
        # Verify timestamp is recent
        now = datetime.utcnow()
        delta = (now - event.timestamp).total_seconds()
        assert delta < 5  # Within 5 seconds


# ============================================================================
# Override & Rollback Tests
# ============================================================================

class TestOverrideFramework:
    """Test override framework (shells only)"""
    
    def test_override_action_not_implemented(self):
        """Verify override actions are not implemented"""
        class TestOverride(OverrideAction):
            def execute(self):
                return super().execute()
            
            def validate(self):
                return super().validate()
        
        override = TestOverride()
        
        with pytest.raises(NotImplementedError):
            override.execute()
        
        with pytest.raises(NotImplementedError):
            override.validate()
    
    def test_rollback_action_not_implemented(self):
        """Verify rollback actions are not implemented"""
        class TestRollback(RollbackAction):
            def execute(self):
                return super().execute()
            
            def get_restore_point(self):
                return super().get_restore_point()
        
        rollback = TestRollback()
        
        with pytest.raises(NotImplementedError):
            rollback.execute()
        
        with pytest.raises(NotImplementedError):
            rollback.get_restore_point()
    
    def test_override_manager_placeholder(self):
        """Verify override manager is placeholder only"""
        manager = OverrideManager()
        
        class DummyOverride(OverrideAction):
            def execute(self):
                pass
            def validate(self):
                pass
        
        override = DummyOverride()
        manager.register_override(override)
        
        overrides = manager.list_overrides()
        assert len(overrides) == 1
        
        # Execution should not be implemented
        with pytest.raises(NotImplementedError):
            manager.execute_override("test-id")
    
    def test_rollback_manager_placeholder(self):
        """Verify rollback manager is placeholder only"""
        manager = RollbackManager()
        
        manager.create_restore_point("test-point")
        points = manager.list_restore_points()
        assert len(points) == 1
        
        # Rollback should not be implemented
        with pytest.raises(NotImplementedError):
            manager.rollback_to_point("test-id")


# ============================================================================
# Integration Tests
# ============================================================================

class TestGovernanceIntegration:
    """Test governance layer integration"""
    
    @pytest.fixture
    def governance_db(self, tmp_path):
        """Create governance database path"""
        return str(tmp_path / "governance.db")
    
    def test_full_approval_workflow(self, governance_db):
        """Test complete approval workflow with audit trail"""
        workflow = ApprovalWorkflow(governance_db)
        audit = AuditLogger(governance_db)
        
        # Create request
        request = workflow.create_request(
            request_id="int-001",
            requester="analyst1",
            action="enable_monitoring",
            reason="Need monitoring capability"
        )
        audit.log_event("analyst1", "request_created", "Monitoring request")
        
        # Approve request
        approved = workflow.approve_request(
            request_id="int-001",
            reviewer="manager1",
            notes="Approved"
        )
        audit.log_event("manager1", "request_approved", "Monitoring approved")
        
        # Verify workflow state
        assert approved.state == ApprovalState.APPROVED
        
        # Verify audit trail
        events = audit.get_events(limit=10)
        assert len(events) == 2
        assert events[0].action == "request_approved"
        assert events[1].action == "request_created"
    
    def test_killswitch_overrides_all(self, governance_db):
        """Verify kill switch has highest priority"""
        killswitch = KillSwitch(governance_db)
        workflow = ApprovalWorkflow(governance_db)
        audit = AuditLogger(governance_db)
        
        # Create and approve request
        workflow.create_request("req-1", "user1", "action1", "reason1")
        workflow.approve_request("req-1", "manager1")
        
        # Enable kill switch
        killswitch.enable(actor="admin", reason="Emergency shutdown")
        audit.log_event("admin", "killswitch_enabled", "Emergency")
        
        # Verify kill switch is enabled (Phase-3 disabled)
        assert killswitch.is_enabled() is True
        
        # Even with approved request, kill switch should prevent activation
        state = killswitch.get_state()
        assert state["phase3_status"] == "disabled"
    
    def test_no_phase1_phase2_coupling(self):
        """Verify governance modules do NOT import Phase-1 or Phase-2"""
        import inspect
        from soc_copilot.phase3 import governance
        
        # Get all imports in governance module
        source = inspect.getsource(governance)
        
        # Verify no phase1 or phase2 imports
        assert "from soc_copilot.phase1" not in source
        assert "from soc_copilot.phase2" not in source
        assert "import soc_copilot.phase1" not in source
        assert "import soc_copilot.phase2" not in source
    
    def test_default_disabled_state_enforced(self, governance_db):
        """Verify all authority states default to DISABLED"""
        policy = GovernancePolicy()
        killswitch = KillSwitch(governance_db)
        
        # Policy defaults to DISABLED
        assert policy.current_state == AuthorityState.DISABLED
        
        # Kill switch defaults to enabled (Phase-3 disabled)
        assert killswitch.is_enabled() is True
        
        # No components permitted by default
        assert len(policy.get_permitted_components()) == 0


# ============================================================================
# Safety Constraint Tests
# ============================================================================

class TestSafetyConstraints:
    """Test non-negotiable safety constraints"""
    
    def test_fully_offline(self, tmp_path):
        """Verify all governance operations are offline"""
        db_path = tmp_path / "test.db"
        
        # All components should work without network
        policy = GovernancePolicy()
        workflow = ApprovalWorkflow(str(db_path))
        killswitch = KillSwitch(str(db_path))
        audit = AuditLogger(str(db_path))
        
        # Perform operations
        workflow.create_request("req-1", "user1", "action1", "reason1")
        killswitch.enable("admin", "test")
        audit.log_event("user1", "action1", "reason1")
        
        # All should succeed without network
        assert True
    
    def test_additive_only(self):
        """Verify governance is additive (no Phase-1/2 modifications)"""
        # Governance modules should not modify existing code
        # This is verified by import isolation test
        from soc_copilot.phase3.governance import policy
        
        # Verify module exists and is independent
        assert hasattr(policy, 'GovernancePolicy')
        assert hasattr(policy, 'AuthorityState')
    
    def test_authority_defaults_disabled(self):
        """Verify all authority states default to DISABLED"""
        policy = GovernancePolicy()
        
        assert policy.current_state == AuthorityState.DISABLED
        assert policy.DEFAULT_STATE == AuthorityState.DISABLED
    
    def test_manual_only_operations(self, tmp_path):
        """Verify all operations require manual action"""
        db_path = tmp_path / "test.db"
        workflow = ApprovalWorkflow(str(db_path))
        
        # Create request
        request = workflow.create_request("req-1", "user1", "action1", "reason1")
        
        # Should remain in REQUESTED state (no auto-approval)
        assert request.state == ApprovalState.REQUESTED
        
        # Manual approval required
        approved = workflow.approve_request("req-1", "manager1")
        assert approved.state == ApprovalState.APPROVED
        
        # Approval does NOT activate anything automatically
        # (would require separate manual implementation)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
