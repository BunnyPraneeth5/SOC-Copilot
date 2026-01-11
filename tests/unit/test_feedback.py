"""Unit tests for Phase-2 feedback store."""

import pytest
import tempfile
from pathlib import Path

from soc_copilot.phase2.feedback import (
    FeedbackStore,
    FeedbackRecord,
    FeedbackStats,
    Verdict,
    get_feedback_store,
)


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


@pytest.fixture
def sample_feedback():
    """Create sample feedback record."""
    return FeedbackRecord(
        alert_id="test-alert-123",
        verdict=Verdict.FALSE_POSITIVE,
        analyst_id="analyst@example.com",
        notes="Known admin activity",
        priority="P2-Medium",
        threat_category="BruteForce",
        anomaly_score=0.65,
        classification="BruteForce",
        classification_confidence=0.82,
    )


# =============================================================================
# Verdict Tests
# =============================================================================

class TestVerdict:
    """Tests for Verdict enum."""
    
    def test_verdict_values(self):
        """Should have correct values."""
        assert Verdict.TRUE_POSITIVE.value == "TP"
        assert Verdict.FALSE_POSITIVE.value == "FP"
        assert Verdict.UNKNOWN.value == "UNKNOWN"
    
    def test_verdict_from_string(self):
        """Should create from string."""
        assert Verdict("TP") == Verdict.TRUE_POSITIVE
        assert Verdict("FP") == Verdict.FALSE_POSITIVE


# =============================================================================
# FeedbackRecord Tests
# =============================================================================

class TestFeedbackRecord:
    """Tests for FeedbackRecord model."""
    
    def test_minimal_record(self):
        """Should create with minimal fields."""
        record = FeedbackRecord(
            alert_id="abc123",
            verdict=Verdict.TRUE_POSITIVE,
        )
        assert record.alert_id == "abc123"
        assert record.verdict == Verdict.TRUE_POSITIVE
        assert record.reviewed_at is not None
    
    def test_full_record(self, sample_feedback):
        """Should create with all fields."""
        assert sample_feedback.alert_id == "test-alert-123"
        assert sample_feedback.verdict == Verdict.FALSE_POSITIVE
        assert sample_feedback.analyst_id == "analyst@example.com"
        assert sample_feedback.notes == "Known admin activity"
        assert sample_feedback.priority == "P2-Medium"
        assert sample_feedback.anomaly_score == 0.65


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
    
    def test_add_feedback(self, store, sample_feedback):
        """Should add feedback record."""
        record_id = store.add_feedback(sample_feedback)
        
        assert record_id is not None
        assert record_id > 0
    
    def test_get_feedback_by_id(self, store, sample_feedback):
        """Should retrieve feedback by alert ID."""
        store.add_feedback(sample_feedback)
        
        records = store.get_feedback(alert_id=sample_feedback.alert_id)
        
        assert len(records) == 1
        assert records[0].alert_id == sample_feedback.alert_id
        assert records[0].verdict == Verdict.FALSE_POSITIVE
    
    def test_get_feedback_by_verdict(self, store):
        """Should filter by verdict."""
        store.add_feedback(FeedbackRecord(
            alert_id="alert-1",
            verdict=Verdict.TRUE_POSITIVE,
        ))
        store.add_feedback(FeedbackRecord(
            alert_id="alert-2",
            verdict=Verdict.FALSE_POSITIVE,
        ))
        store.add_feedback(FeedbackRecord(
            alert_id="alert-3",
            verdict=Verdict.FALSE_POSITIVE,
        ))
        
        tp_records = store.get_feedback(verdict=Verdict.TRUE_POSITIVE)
        fp_records = store.get_feedback(verdict=Verdict.FALSE_POSITIVE)
        
        assert len(tp_records) == 1
        assert len(fp_records) == 2
    
    def test_get_feedback_with_limit(self, store):
        """Should respect limit."""
        for i in range(10):
            store.add_feedback(FeedbackRecord(
                alert_id=f"alert-{i}",
                verdict=Verdict.TRUE_POSITIVE,
            ))
        
        records = store.get_feedback(limit=5)
        
        assert len(records) == 5
    
    def test_delete_feedback(self, store, sample_feedback):
        """Should delete feedback record."""
        record_id = store.add_feedback(sample_feedback)
        
        deleted = store.delete_feedback(record_id)
        assert deleted is True
        
        records = store.get_feedback(alert_id=sample_feedback.alert_id)
        assert len(records) == 0
    
    def test_delete_nonexistent(self, store):
        """Should return False for nonexistent record."""
        deleted = store.delete_feedback(99999)
        assert deleted is False


# =============================================================================
# FeedbackStats Tests
# =============================================================================

class TestFeedbackStats:
    """Tests for feedback statistics."""
    
    def test_empty_stats(self, store):
        """Should return zeros for empty database."""
        stats = store.get_statistics()
        
        assert stats.total_count == 0
        assert stats.tp_count == 0
        assert stats.fp_count == 0
        assert stats.tp_rate == 0.0
        assert stats.fp_rate == 0.0
    
    def test_stats_with_data(self, store):
        """Should calculate correct statistics."""
        # Add 3 TP, 2 FP, 1 Unknown
        for _ in range(3):
            store.add_feedback(FeedbackRecord(
                alert_id="tp-alert",
                verdict=Verdict.TRUE_POSITIVE,
            ))
        for _ in range(2):
            store.add_feedback(FeedbackRecord(
                alert_id="fp-alert",
                verdict=Verdict.FALSE_POSITIVE,
            ))
        store.add_feedback(FeedbackRecord(
            alert_id="unknown-alert",
            verdict=Verdict.UNKNOWN,
        ))
        
        stats = store.get_statistics()
        
        assert stats.total_count == 6
        assert stats.tp_count == 3
        assert stats.fp_count == 2
        assert stats.unknown_count == 1
        assert stats.tp_rate == 0.5
        assert abs(stats.fp_rate - 0.333) < 0.01
    
    def test_stats_by_priority(self, store):
        """Should group by priority."""
        store.add_feedback(FeedbackRecord(
            alert_id="alert-1",
            verdict=Verdict.TRUE_POSITIVE,
            priority="P0-Critical",
        ))
        store.add_feedback(FeedbackRecord(
            alert_id="alert-2",
            verdict=Verdict.FALSE_POSITIVE,
            priority="P0-Critical",
        ))
        store.add_feedback(FeedbackRecord(
            alert_id="alert-3",
            verdict=Verdict.TRUE_POSITIVE,
            priority="P2-Medium",
        ))
        
        stats = store.get_statistics()
        
        assert "P0-Critical" in stats.by_priority
        assert stats.by_priority["P0-Critical"]["TP"] == 1
        assert stats.by_priority["P0-Critical"]["FP"] == 1
        assert "P2-Medium" in stats.by_priority
    
    def test_stats_by_threat_category(self, store):
        """Should group by threat category."""
        store.add_feedback(FeedbackRecord(
            alert_id="alert-1",
            verdict=Verdict.TRUE_POSITIVE,
            threat_category="Malware",
        ))
        store.add_feedback(FeedbackRecord(
            alert_id="alert-2",
            verdict=Verdict.FALSE_POSITIVE,
            threat_category="DDoS",
        ))
        
        stats = store.get_statistics()
        
        assert "Malware" in stats.by_threat_category
        assert "DDoS" in stats.by_threat_category


# =============================================================================
# Integration Tests
# =============================================================================

class TestFeedbackStoreIntegration:
    """Integration tests for feedback store."""
    
    def test_multiple_operations(self, store):
        """Should handle multiple operations."""
        # Add
        id1 = store.add_feedback(FeedbackRecord(
            alert_id="alert-1",
            verdict=Verdict.TRUE_POSITIVE,
            priority="P1-High",
        ))
        id2 = store.add_feedback(FeedbackRecord(
            alert_id="alert-2",
            verdict=Verdict.FALSE_POSITIVE,
            priority="P2-Medium",
        ))
        
        # Query
        all_records = store.get_feedback()
        assert len(all_records) == 2
        
        # Stats
        stats = store.get_statistics()
        assert stats.total_count == 2
        
        # Delete
        store.delete_feedback(id1)
        
        # Verify
        remaining = store.get_feedback()
        assert len(remaining) == 1
        assert remaining[0].alert_id == "alert-2"
    
    def test_get_feedback_store_convenience(self, temp_db):
        """Should work with convenience function."""
        store = get_feedback_store(str(temp_db))
        
        store.add_feedback(FeedbackRecord(
            alert_id="test",
            verdict=Verdict.UNKNOWN,
        ))
        
        records = store.get_feedback()
        assert len(records) == 1
