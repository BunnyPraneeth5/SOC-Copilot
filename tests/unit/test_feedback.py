"""Unit tests for Phase-2 feedback store."""

import pytest
import tempfile
from pathlib import Path

from soc_copilot.phase2.feedback import FeedbackStore, FeedbackStats


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database path."""
    return tmp_path / "test_feedback.db"


@pytest.fixture
def store(temp_db):
    """Create an initialized feedback store."""
    store = FeedbackStore(temp_db)
    store.initialize()
    return store


# =============================================================================
# FeedbackStats Tests
# =============================================================================

class TestFeedbackStats:
    """Tests for FeedbackStats class."""
    
    def test_default_stats(self):
        """Should have zero counts by default."""
        stats = FeedbackStats()
        
        assert stats.total_count == 0
        assert stats.accept_count == 0
        assert stats.reject_count == 0
        assert stats.reclassify_count == 0
        assert stats.by_label == {}


# =============================================================================
# FeedbackStore Tests
# =============================================================================

class TestFeedbackStore:
    """Tests for FeedbackStore."""
    
    def test_initialize_creates_db(self, temp_db):
        """Should create database file."""
        store = FeedbackStore(temp_db)
        store.initialize()
        
        assert temp_db.exists()
    
    def test_add_feedback_accept(self, store):
        """Should add accept feedback record."""
        record_id = store.add_feedback(
            alert_id="test-alert-123",
            analyst_action="accept",
        )
        
        assert record_id is not None
        assert record_id > 0
    
    def test_add_feedback_reject(self, store):
        """Should add reject feedback record."""
        record_id = store.add_feedback(
            alert_id="test-alert-456",
            analyst_action="reject",
            comment="Known false positive",
        )
        
        assert record_id > 0
    
    def test_add_feedback_reclassify(self, store):
        """Should add reclassify feedback record."""
        record_id = store.add_feedback(
            alert_id="test-alert-789",
            analyst_action="reclassify",
            analyst_label="Phishing",
            comment="Recategorized",
        )
        
        assert record_id > 0
    
    def test_add_feedback_invalid_action(self, store):
        """Should reject invalid action."""
        with pytest.raises(ValueError):
            store.add_feedback(
                alert_id="test",
                analyst_action="invalid",
            )
    
    def test_get_feedback_by_alert(self, store):
        """Should retrieve feedback by alert ID."""
        store.add_feedback(
            alert_id="alert-123",
            analyst_action="accept",
        )
        store.add_feedback(
            alert_id="alert-123",
            analyst_action="reject",
            comment="Changed mind",
        )
        
        records = store.get_feedback_by_alert("alert-123")
        
        assert len(records) == 2
        assert records[0]["alert_id"] == "alert-123"
    
    def test_get_feedback_empty(self, store):
        """Should return empty list for unknown alert."""
        records = store.get_feedback_by_alert("nonexistent")
        
        assert records == []


# =============================================================================
# FeedbackStats Integration Tests
# =============================================================================

class TestFeedbackStatsIntegration:
    """Integration tests for feedback statistics."""
    
    def test_empty_stats(self, store):
        """Should return zeros for empty database."""
        stats = store.get_feedback_stats()
        
        assert stats.total_count == 0
        assert stats.accept_count == 0
        assert stats.reject_count == 0
    
    def test_stats_with_data(self, store):
        """Should calculate correct statistics."""
        # Add 3 accepts, 2 rejects, 1 reclassify
        for i in range(3):
            store.add_feedback(alert_id=f"accept-{i}", analyst_action="accept")
        for i in range(2):
            store.add_feedback(alert_id=f"reject-{i}", analyst_action="reject")
        store.add_feedback(
            alert_id="reclassify-1",
            analyst_action="reclassify",
            analyst_label="Malware",
        )
        
        stats = store.get_feedback_stats()
        
        assert stats.total_count == 6
        assert stats.accept_count == 3
        assert stats.reject_count == 2
        assert stats.reclassify_count == 1
    
    def test_stats_by_label(self, store):
        """Should group reclassify by label."""
        store.add_feedback(
            alert_id="alert-1",
            analyst_action="reclassify",
            analyst_label="Malware",
        )
        store.add_feedback(
            alert_id="alert-2",
            analyst_action="reclassify",
            analyst_label="Phishing",
        )
        store.add_feedback(
            alert_id="alert-3",
            analyst_action="reclassify",
            analyst_label="Malware",
        )
        
        stats = store.get_feedback_stats()
        
        assert "Malware" in stats.by_label
        assert stats.by_label["Malware"] == 2
        assert "Phishing" in stats.by_label
        assert stats.by_label["Phishing"] == 1


# =============================================================================
# Store Lifecycle Tests
# =============================================================================

class TestFeedbackStoreLifecycle:
    """Tests for store lifecycle operations."""
    
    def test_close_and_reopen(self, temp_db):
        """Should persist data across close/reopen."""
        # Create and add
        store1 = FeedbackStore(temp_db)
        store1.initialize()
        store1.add_feedback(alert_id="persist-test", analyst_action="accept")
        store1.close()
        
        # Reopen and verify
        store2 = FeedbackStore(temp_db)
        store2.initialize()
        records = store2.get_feedback_by_alert("persist-test")
        
        assert len(records) == 1
        assert records[0]["analyst_action"] == "accept"
        store2.close()
