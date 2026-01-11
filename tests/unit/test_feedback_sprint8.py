"""Unit tests for Sprint-8 Feedback Store."""

import pytest
from pathlib import Path

from soc_copilot.phase2.feedback import FeedbackStore, FeedbackStats


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database path."""
    return tmp_path / "feedback.db"


@pytest.fixture
def store(temp_db):
    """Create initialized feedback store."""
    store = FeedbackStore(temp_db)
    store.initialize()
    yield store
    store.close()


class TestFeedbackStore:
    """Tests for FeedbackStore."""
    
    def test_initialize_creates_db(self, temp_db):
        """Should create database file."""
        store = FeedbackStore(temp_db)
        store.initialize()
        
        assert temp_db.exists()
        store.close()
    
    def test_add_feedback_accept(self, store):
        """Should add accept feedback."""
        record_id = store.add_feedback(
            alert_id="alert-123",
            analyst_action="accept",
        )
        
        assert record_id > 0
    
    def test_add_feedback_reject(self, store):
        """Should add reject feedback."""
        record_id = store.add_feedback(
            alert_id="alert-456",
            analyst_action="reject",
            comment="False positive",
        )
        
        assert record_id > 0
    
    def test_add_feedback_reclassify(self, store):
        """Should add reclassify feedback."""
        record_id = store.add_feedback(
            alert_id="alert-789",
            analyst_action="reclassify",
            analyst_label="Malware",
            comment="Actually malware",
        )
        
        assert record_id > 0
    
    def test_add_feedback_invalid_action(self, store):
        """Should reject invalid action."""
        with pytest.raises(ValueError):
            store.add_feedback(
                alert_id="alert-999",
                analyst_action="invalid",
            )
    
    def test_get_feedback_by_alert(self, store):
        """Should retrieve feedback by alert ID."""
        store.add_feedback(
            alert_id="alert-abc",
            analyst_action="accept",
        )
        store.add_feedback(
            alert_id="alert-abc",
            analyst_action="reject",
        )
        
        records = store.get_feedback_by_alert("alert-abc")
        
        assert len(records) == 2
        assert records[0]["alert_id"] == "alert-abc"
    
    def test_get_feedback_stats_empty(self, store):
        """Should return zero stats for empty database."""
        stats = store.get_feedback_stats()
        
        assert stats.total_count == 0
        assert stats.accept_count == 0
        assert stats.reject_count == 0
        assert stats.reclassify_count == 0
    
    def test_get_feedback_stats_with_data(self, store):
        """Should calculate correct statistics."""
        store.add_feedback("alert-1", "accept")
        store.add_feedback("alert-2", "accept")
        store.add_feedback("alert-3", "reject")
        store.add_feedback("alert-4", "reclassify", analyst_label="Malware")
        store.add_feedback("alert-5", "reclassify", analyst_label="DDoS")
        
        stats = store.get_feedback_stats()
        
        assert stats.total_count == 5
        assert stats.accept_count == 2
        assert stats.reject_count == 1
        assert stats.reclassify_count == 2
    
    def test_get_feedback_stats_by_label(self, store):
        """Should group reclassified labels."""
        store.add_feedback("alert-1", "reclassify", analyst_label="Malware")
        store.add_feedback("alert-2", "reclassify", analyst_label="Malware")
        store.add_feedback("alert-3", "reclassify", analyst_label="DDoS")
        
        stats = store.get_feedback_stats()
        
        assert stats.by_label["Malware"] == 2
        assert stats.by_label["DDoS"] == 1
    
    def test_schema_exact_fields(self, store):
        """Should have exact schema per Sprint-8 spec."""
        store.add_feedback(
            alert_id="test-alert",
            analyst_action="accept",
            analyst_label=None,
            comment="Test comment",
        )
        
        records = store.get_feedback_by_alert("test-alert")
        record = records[0]
        
        # Verify exact schema fields
        assert "id" in record
        assert "timestamp" in record
        assert "alert_id" in record
        assert "analyst_action" in record
        assert "analyst_label" in record
        assert "comment" in record
        
        # Verify values
        assert record["alert_id"] == "test-alert"
        assert record["analyst_action"] == "accept"
        assert record["comment"] == "Test comment"
    
    def test_timestamp_utc_iso8601(self, store):
        """Should use UTC ISO 8601 timestamps."""
        store.add_feedback("alert-time", "accept")
        
        records = store.get_feedback_by_alert("alert-time")
        timestamp = records[0]["timestamp"]
        
        # Should end with Z for UTC
        assert timestamp.endswith("Z")
        # Should be ISO 8601 format
        assert "T" in timestamp


class TestFeedbackStoreIntegration:
    """Integration tests."""
    
    def test_multiple_operations(self, store):
        """Should handle multiple operations."""
        # Add multiple feedback
        store.add_feedback("alert-1", "accept")
        store.add_feedback("alert-2", "reject", comment="FP")
        store.add_feedback("alert-3", "reclassify", analyst_label="Malware")
        
        # Query by alert
        records = store.get_feedback_by_alert("alert-2")
        assert len(records) == 1
        assert records[0]["analyst_action"] == "reject"
        
        # Get stats
        stats = store.get_feedback_stats()
        assert stats.total_count == 3
        assert stats.accept_count == 1
        assert stats.reject_count == 1
        assert stats.reclassify_count == 1
    
    def test_default_db_path(self, tmp_path, monkeypatch):
        """Should use default path data/feedback/feedback.db."""
        monkeypatch.chdir(tmp_path)
        
        store = FeedbackStore()
        store.initialize()
        
        assert store.db_path == Path("data/feedback/feedback.db")
        assert store.db_path.parent.exists()
        
        store.close()
