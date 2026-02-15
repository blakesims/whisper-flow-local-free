"""Tests for Phase 4 wiring: DelegationTracker <-> WhisperDaemon <-> DelegationPip."""

import json
import os
import sys
import types
import pytest
from unittest.mock import MagicMock, patch, call

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication.instance() or QApplication(sys.argv)

from app.daemon.whisper_daemon import (
    DelegationTracker,
    DelegationState,
    WhisperDaemon,
)
from app.daemon.recording_indicator import DelegationPip


class FakeConfigManager:
    """Minimal config manager for tests."""

    def __init__(self, config: dict):
        self._config = config

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value


@pytest.fixture
def cc_triage_dirs(tmp_path):
    """Create a temporary cc-triage directory structure with config."""
    inbox = tmp_path / "inbox"
    reports = tmp_path / "reports"
    failed = tmp_path / "failed"
    config_dir = tmp_path / "config"
    for d in (inbox, reports, failed, config_dir):
        d.mkdir()
    config = {
        "inbox_path": "./inbox",
        "reports_path": "./reports",
        "failed_path": "./failed",
    }
    (config_dir / "config.json").write_text(json.dumps(config))
    return tmp_path, inbox, reports, failed


@pytest.fixture
def tracker(cc_triage_dirs):
    root, inbox, reports, failed = cc_triage_dirs
    config = FakeConfigManager({"cc_triage_root": str(root)})
    t = DelegationTracker(config)
    return t


def _make_fake_daemon():
    """Create a simple namespace that has the methods under test without QObject init."""
    ns = types.SimpleNamespace()
    ns._delegation_pips = {}
    ns.indicator = MagicMock()
    ns.delegation_tracker = MagicMock()
    ns.transcription_complete = MagicMock()
    ns.state_changed = MagicMock()
    ns._state = None
    # Bind the actual methods from WhisperDaemon
    ns._on_delegation_state_changed = WhisperDaemon._on_delegation_state_changed.__get__(ns)
    ns._handle_delegation_output = WhisperDaemon._handle_delegation_output.__get__(ns)
    return ns


# --- Task 4.4: glob is now a top-level import ---

class TestGlobImport:
    def test_glob_is_top_level_import(self):
        """glob should be imported at module level, not inside _check_state."""
        import app.daemon.whisper_daemon as mod
        assert hasattr(mod, "glob"), "glob not found as module-level attribute"


# --- Task 4.3: _poll handles per-delegation exceptions ---

class TestPollExceptionHandling:
    def test_poll_continues_after_single_delegation_error(self, tracker, cc_triage_dirs):
        """If _check_state raises for one delegation, others still get checked."""
        root, inbox, reports, failed = cc_triage_dirs

        d1 = "delegation_err.txt"
        d2 = "delegation_ok.txt"
        tracker.track(d1)
        tracker.track(d2)
        tracker._poll_timer.stop()

        original_check = tracker._check_state
        call_count = {"d2_called": False}

        def mock_check(did, state):
            if did == d1:
                raise PermissionError("fake fs error")
            call_count["d2_called"] = True
            return original_check(did, state)

        tracker._check_state = mock_check
        tracker._poll()  # should not raise

        assert call_count["d2_called"]

    def test_poll_does_not_crash_on_exception(self, tracker, cc_triage_dirs):
        """_poll should never propagate exceptions from _check_state."""
        root, inbox, reports, failed = cc_triage_dirs
        tracker.track("delegation_test.txt")
        tracker._poll_timer.stop()

        def always_raise(did, state):
            raise OSError("disk error")

        tracker._check_state = always_raise
        tracker._poll()  # Must not raise


# --- Task 4.1: track() called after file write ---

class TestTrackAfterWrite:
    def test_handle_delegation_output_calls_track_after_save(self):
        """Verify track() is called only after _save_delegation() returns a filepath."""
        daemon = _make_fake_daemon()
        call_order = []

        def mock_save(text):
            call_order.append("save")
            return "/tmp/fake/inbox/delegation_20260215_171033.txt"

        def mock_track(filename):
            call_order.append("track")

        daemon._save_delegation = mock_save
        daemon.delegation_tracker.track = mock_track

        with patch("pyperclip.copy"):
            daemon._handle_delegation_output("test text")

        assert call_order == ["save", "track"], f"Expected save before track, got: {call_order}"

    def test_track_not_called_when_save_fails(self):
        """If _save_delegation returns None, track should not be called."""
        daemon = _make_fake_daemon()
        daemon._save_delegation = lambda text: None

        with patch("pyperclip.copy"):
            daemon._handle_delegation_output("test text")

        daemon.delegation_tracker.track.assert_not_called()


# --- Task 4.2: Signal -> pip state mapping ---

class TestDelegationStateChangedHandler:
    def test_on_delegation_state_changed_updates_pip(self):
        """_on_delegation_state_changed should call pip.set_state with the new state."""
        daemon = _make_fake_daemon()
        mock_pip = MagicMock()
        daemon._delegation_pips["delegation_001.txt"] = mock_pip

        daemon._on_delegation_state_changed("delegation_001.txt", "processing")

        mock_pip.set_state.assert_called_once_with("processing")

    def test_on_delegation_state_changed_cleans_up_on_complete(self):
        """Terminal state 'complete' should remove the pip from the map."""
        daemon = _make_fake_daemon()
        mock_pip = MagicMock()
        daemon._delegation_pips["delegation_001.txt"] = mock_pip

        daemon._on_delegation_state_changed("delegation_001.txt", "complete")

        assert "delegation_001.txt" not in daemon._delegation_pips

    def test_on_delegation_state_changed_cleans_up_on_failed(self):
        """Terminal state 'failed' should remove the pip from the map."""
        daemon = _make_fake_daemon()
        mock_pip = MagicMock()
        daemon._delegation_pips["delegation_001.txt"] = mock_pip

        daemon._on_delegation_state_changed("delegation_001.txt", "failed")

        assert "delegation_001.txt" not in daemon._delegation_pips

    def test_on_delegation_state_changed_ignores_unknown_id(self):
        """If delegation_id has no pip, should not raise."""
        daemon = _make_fake_daemon()
        daemon._on_delegation_state_changed("unknown.txt", "processing")

    def test_processing_state_does_not_remove_pip(self):
        """Non-terminal state should keep pip in the map."""
        daemon = _make_fake_daemon()
        mock_pip = MagicMock()
        daemon._delegation_pips["delegation_001.txt"] = mock_pip

        daemon._on_delegation_state_changed("delegation_001.txt", "processing")

        assert "delegation_001.txt" in daemon._delegation_pips

    def test_sent_state_does_not_remove_pip(self):
        """SENT state should keep pip in the map."""
        daemon = _make_fake_daemon()
        mock_pip = MagicMock()
        daemon._delegation_pips["delegation_001.txt"] = mock_pip

        daemon._on_delegation_state_changed("delegation_001.txt", "sent")

        assert "delegation_001.txt" in daemon._delegation_pips


# --- Task 4.5: Composite states ---

class TestCompositeStates:
    def test_pip_created_in_delegation_pips_map(self):
        """After _handle_delegation_output, pip should be in _delegation_pips."""
        daemon = _make_fake_daemon()
        daemon._save_delegation = lambda text: "/tmp/inbox/delegation_20260215_171033.txt"

        mock_pip = MagicMock()
        daemon.indicator.add_delegation_pip.return_value = mock_pip

        with patch("pyperclip.copy"):
            daemon._handle_delegation_output("test text")

        assert "delegation_20260215_171033.txt" in daemon._delegation_pips
        assert daemon._delegation_pips["delegation_20260215_171033.txt"] is mock_pip

    def test_multiple_delegations_create_multiple_pips(self):
        """Two delegation outputs should create two separate pip entries."""
        daemon = _make_fake_daemon()
        call_count = [0]

        def mock_save(text):
            call_count[0] += 1
            return f"/tmp/inbox/delegation_00{call_count[0]}.txt"

        daemon._save_delegation = mock_save

        pip1 = MagicMock()
        pip2 = MagicMock()
        daemon.indicator.add_delegation_pip.side_effect = [pip1, pip2]

        with patch("pyperclip.copy"):
            daemon._handle_delegation_output("text 1")
            daemon._handle_delegation_output("text 2")

        assert len(daemon._delegation_pips) == 2
        assert daemon._delegation_pips["delegation_001.txt"] is pip1
        assert daemon._delegation_pips["delegation_002.txt"] is pip2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
