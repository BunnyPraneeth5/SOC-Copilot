"""Test event deduplication functionality"""

import time
from soc_copilot.models.ensemble.deduplication import EventDeduplicator


def test_deduplication_basic():
    """Test basic deduplication with cooldown"""
    dedup = EventDeduplicator(cooldown_seconds=2.0)
    
    # First event should be processed
    fp1 = dedup.fingerprint_event("Benign", 0.1, "192.168.1.1")
    assert dedup.should_process(fp1) is True
    
    # Immediate duplicate should be suppressed
    assert dedup.should_process(fp1) is False
    
    # Wait for cooldown
    time.sleep(2.1)
    
    # After cooldown, should be processed again
    assert dedup.should_process(fp1) is True


def test_fingerprint_stability():
    """Test fingerprint is stable for same inputs"""
    dedup = EventDeduplicator()
    
    fp1 = dedup.fingerprint_event("Benign", 0.123, "192.168.1.1")
    fp2 = dedup.fingerprint_event("Benign", 0.123, "192.168.1.1")
    
    assert fp1 == fp2


def test_fingerprint_bucketing():
    """Test anomaly score bucketing reduces noise"""
    dedup = EventDeduplicator()
    
    # Similar scores should produce same fingerprint
    fp1 = dedup.fingerprint_event("Benign", 0.123, "192.168.1.1")
    fp2 = dedup.fingerprint_event("Benign", 0.129, "192.168.1.1")
    
    assert fp1 == fp2  # Both round to 0.1


def test_different_events():
    """Test different events get different fingerprints"""
    dedup = EventDeduplicator()
    
    fp1 = dedup.fingerprint_event("Benign", 0.1, "192.168.1.1")
    fp2 = dedup.fingerprint_event("DDoS", 0.1, "192.168.1.1")
    fp3 = dedup.fingerprint_event("Benign", 0.1, "192.168.1.2")
    
    assert fp1 != fp2  # Different classification
    assert fp1 != fp3  # Different IP


def test_cleanup():
    """Test cleanup removes old entries"""
    dedup = EventDeduplicator(cooldown_seconds=1.0)
    
    fp1 = dedup.fingerprint_event("Benign", 0.1, "192.168.1.1")
    dedup.should_process(fp1)
    
    assert len(dedup._seen) == 1
    
    # Cleanup with short max_age
    time.sleep(0.1)
    dedup.cleanup_old_entries(max_age_seconds=0.05)
    
    assert len(dedup._seen) == 0


if __name__ == "__main__":
    test_deduplication_basic()
    test_fingerprint_stability()
    test_fingerprint_bucketing()
    test_different_events()
    test_cleanup()
    print("✓ All deduplication tests passed")
