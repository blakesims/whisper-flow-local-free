"""Tests for DelegationTracker — filesystem polling and state machine."""

import json
import os
import sys
import tempfile
import pytest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# QApplication must exist before creating any QObject
app = QApplication.instance() or QApplication(sys.argv)

from app.daemon.whisper_daemon import DelegationTracker, DelegationState


class FakeConfigManager:
    """Minimal config manager for tests."""

    def __init__(self, config: dict):
        self._config = config

    def get(self, key, default=None):
        return self._config.get(key, default)


@pytest.fixture
def cc_triage_dirs(tmp_path):
    """Create a temporary cc-triage directory structure with config."""
    inbox = tmp_path / "inbox"
    reports = tmp_path / "reports"
    failed = tmp_path / "failed"
    config_dir = tmp_path / "config"

    inbox.mkdir()
    reports.mkdir()
    failed.mkdir()
    config_dir.mkdir()

    # Write cc-triage config.json
    config = {
        "inbox_path": "./inbox",
        "reports_path": "./reports",
        "failed_path": "./failed",
    }
    (config_dir / "config.json").write_text(json.dumps(config))

    return tmp_path, inbox, reports, failed


@pytest.fixture
def tracker(cc_triage_dirs):
    """Create a DelegationTracker with resolved dirs pointing to tmp."""
    root, inbox, reports, failed = cc_triage_dirs
    config = FakeConfigManager({"cc_triage_root": str(root)})
    t = DelegationTracker(config)
    return t


DELEGATION_ID = "delegation_20260215_171033.txt"


class TestDelegationTrackerInit:
    """Test tracker initialization."""

    def test_no_active_delegations_at_start(self, tracker):
        assert tracker.active_count == 0

    def test_not_polling_at_start(self, tracker):
        assert not tracker.is_polling

    def test_dirs_not_resolved_until_track(self):
        config = FakeConfigManager({"cc_triage_root": "/nonexistent"})
        t = DelegationTracker(config)
        assert not t._dirs_resolved


class TestDirResolution:
    """Test cc-triage config reading."""

    def test_resolves_dirs_from_config(self, cc_triage_dirs):
        root, inbox, reports, failed = cc_triage_dirs
        config = FakeConfigManager({"cc_triage_root": str(root)})
        t = DelegationTracker(config)
        assert t._resolve_dirs()
        assert t._inbox_dir == str(inbox)
        assert t._reports_dir == str(reports)
        assert t._failed_dir == str(failed)

    def test_fails_without_cc_triage_root(self):
        config = FakeConfigManager({})
        t = DelegationTracker(config)
        assert not t._resolve_dirs()

    def test_fails_with_missing_config_file(self, tmp_path):
        config = FakeConfigManager({"cc_triage_root": str(tmp_path)})
        t = DelegationTracker(config)
        assert not t._resolve_dirs()

    def test_fails_with_invalid_json(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "config.json").write_text("not json")
        config = FakeConfigManager({"cc_triage_root": str(tmp_path)})
        t = DelegationTracker(config)
        assert not t._resolve_dirs()


class TestTrack:
    """Test track() method."""

    def test_track_sets_state_sent(self, tracker):
        tracker.track(DELEGATION_ID)
        assert tracker._active[DELEGATION_ID] == DelegationState.SENT

    def test_track_starts_polling(self, tracker):
        tracker.track(DELEGATION_ID)
        assert tracker.is_polling
        tracker._poll_timer.stop()  # cleanup

    def test_track_emits_signal(self, tracker):
        signals = []
        tracker.delegation_state_changed.connect(lambda did, s: signals.append((did, s)))
        tracker.track(DELEGATION_ID)
        assert signals == [(DELEGATION_ID, "sent")]

    def test_track_without_config_does_not_crash(self):
        config = FakeConfigManager({})
        t = DelegationTracker(config)
        t.track(DELEGATION_ID)  # should not raise
        assert t.active_count == 0

    def test_track_increments_count(self, tracker):
        tracker.track("delegation_001.txt")
        tracker.track("delegation_002.txt")
        assert tracker.active_count == 2
        tracker._poll_timer.stop()


class TestStateTransitions:
    """Test _check_state and _poll for filesystem-driven transitions."""

    def test_sent_to_processing_when_file_removed(self, tracker, cc_triage_dirs):
        root, inbox, reports, failed = cc_triage_dirs
        # File initially in inbox
        (inbox / DELEGATION_ID).write_text("test")
        tracker.track(DELEGATION_ID)
        tracker._poll_timer.stop()

        # Verify SENT (file exists)
        result = tracker._check_state(DELEGATION_ID, DelegationState.SENT)
        assert result is None  # no change, still SENT

        # Remove file (cc-triage picked it up)
        (inbox / DELEGATION_ID).unlink()
        result = tracker._check_state(DELEGATION_ID, DelegationState.SENT)
        assert result == DelegationState.PROCESSING

    def test_processing_to_complete_when_report_exists(self, tracker, cc_triage_dirs):
        root, inbox, reports, failed = cc_triage_dirs
        tracker.track(DELEGATION_ID)
        tracker._poll_timer.stop()

        # Create report file
        stem = os.path.splitext(DELEGATION_ID)[0]
        (reports / f"triage_{stem}.json").write_text("{}")

        result = tracker._check_state(DELEGATION_ID, DelegationState.PROCESSING)
        assert result == DelegationState.COMPLETE

    def test_processing_to_failed_when_failed_file_exists(self, tracker, cc_triage_dirs):
        root, inbox, reports, failed = cc_triage_dirs
        tracker.track(DELEGATION_ID)
        tracker._poll_timer.stop()

        # Create failed file (cc-triage appends timestamp)
        stem = os.path.splitext(DELEGATION_ID)[0]
        (failed / f"{stem}_20260215_171100.txt").write_text("error")

        result = tracker._check_state(DELEGATION_ID, DelegationState.PROCESSING)
        assert result == DelegationState.FAILED

    def test_sent_stays_sent_while_file_in_inbox(self, tracker, cc_triage_dirs):
        root, inbox, reports, failed = cc_triage_dirs
        (inbox / DELEGATION_ID).write_text("test")
        tracker.track(DELEGATION_ID)
        tracker._poll_timer.stop()

        result = tracker._check_state(DELEGATION_ID, DelegationState.SENT)
        assert result is None

    def test_complete_report_takes_priority_over_inbox(self, tracker, cc_triage_dirs):
        """If report exists, state should be COMPLETE even if file still in inbox."""
        root, inbox, reports, failed = cc_triage_dirs
        (inbox / DELEGATION_ID).write_text("test")
        stem = os.path.splitext(DELEGATION_ID)[0]
        (reports / f"triage_{stem}.json").write_text("{}")
        tracker.track(DELEGATION_ID)
        tracker._poll_timer.stop()

        result = tracker._check_state(DELEGATION_ID, DelegationState.SENT)
        assert result == DelegationState.COMPLETE

    def test_stale_delegation_stays_sent(self, tracker, cc_triage_dirs):
        """If file is in inbox and cc-triage is not running, stays SENT (no false positive)."""
        root, inbox, reports, failed = cc_triage_dirs
        (inbox / DELEGATION_ID).write_text("test")
        tracker.track(DELEGATION_ID)
        tracker._poll_timer.stop()

        # Poll multiple times — should stay SENT
        for _ in range(5):
            result = tracker._check_state(DELEGATION_ID, DelegationState.SENT)
            assert result is None


class TestPollIntegration:
    """Test _poll() method with signal emission."""

    def test_poll_emits_transition_signal(self, tracker, cc_triage_dirs):
        root, inbox, reports, failed = cc_triage_dirs
        (inbox / DELEGATION_ID).write_text("test")
        tracker.track(DELEGATION_ID)
        tracker._poll_timer.stop()

        signals = []
        tracker.delegation_state_changed.connect(lambda did, s: signals.append((did, s)))

        # Remove file to trigger SENT -> PROCESSING
        (inbox / DELEGATION_ID).unlink()
        tracker._poll()

        assert (DELEGATION_ID, "processing") in signals

    def test_poll_stops_when_no_active_delegations(self, tracker, cc_triage_dirs):
        tracker.track(DELEGATION_ID)
        assert tracker.is_polling

        # Manually remove and poll
        del tracker._active[DELEGATION_ID]
        tracker._poll()
        assert not tracker.is_polling


class TestCleanup:
    """Test auto-cleanup of terminal states."""

    def test_cleanup_removes_delegation(self, tracker, cc_triage_dirs):
        tracker.track(DELEGATION_ID)
        tracker._poll_timer.stop()
        assert tracker.active_count == 1

        tracker._cleanup(DELEGATION_ID)
        assert tracker.active_count == 0

    def test_cleanup_stops_polling_when_last_removed(self, tracker, cc_triage_dirs):
        tracker.track(DELEGATION_ID)
        assert tracker.is_polling

        tracker._cleanup(DELEGATION_ID)
        assert not tracker.is_polling

    def test_cleanup_nonexistent_id_is_safe(self, tracker):
        tracker._cleanup("nonexistent.txt")  # should not raise

    def test_cleanup_with_others_keeps_polling(self, tracker, cc_triage_dirs):
        tracker.track("delegation_001.txt")
        tracker.track("delegation_002.txt")
        tracker._cleanup("delegation_001.txt")
        assert tracker.is_polling
        assert tracker.active_count == 1
        tracker._poll_timer.stop()


class TestMultipleConcurrent:
    """Test multiple delegations tracked independently."""

    def test_two_delegations_independent_states(self, tracker, cc_triage_dirs):
        root, inbox, reports, failed = cc_triage_dirs

        d1 = "delegation_001.txt"
        d2 = "delegation_002.txt"

        (inbox / d1).write_text("test1")
        (inbox / d2).write_text("test2")

        tracker.track(d1)
        tracker.track(d2)
        tracker._poll_timer.stop()

        # Remove d1 from inbox, d2 stays
        (inbox / d1).unlink()

        tracker._poll()

        assert tracker._active[d1] == DelegationState.PROCESSING
        assert tracker._active[d2] == DelegationState.SENT

    def test_three_delegations_different_terminal_states(self, tracker, cc_triage_dirs):
        root, inbox, reports, failed = cc_triage_dirs

        d1 = "delegation_001.txt"
        d2 = "delegation_002.txt"
        d3 = "delegation_003.txt"

        tracker.track(d1)
        tracker.track(d2)
        tracker.track(d3)
        tracker._poll_timer.stop()

        # d1 -> COMPLETE, d2 -> FAILED, d3 -> still SENT (in inbox)
        (reports / "triage_delegation_001.json").write_text("{}")
        (failed / "delegation_002_20260215_999999.txt").write_text("err")
        (inbox / d3).write_text("test")

        tracker._poll()

        assert tracker._active[d1] == DelegationState.COMPLETE
        assert tracker._active[d2] == DelegationState.FAILED
        assert tracker._active[d3] == DelegationState.SENT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
