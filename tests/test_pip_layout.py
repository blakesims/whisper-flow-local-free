"""Tests for Phase 2 — DelegationPip integration into RecordingIndicator layout."""

import sys
import pytest
from PySide6.QtWidgets import QApplication

from app.daemon.recording_indicator import RecordingIndicator, DelegationPip

# QApplication must exist before creating any QWidget
app = QApplication.instance() or QApplication(sys.argv)


class TestPipContainer:
    """Task 2.1: Pip container exists in layout."""

    def test_pip_layout_exists(self):
        indicator = RecordingIndicator()
        assert hasattr(indicator, '_pip_layout')
        assert hasattr(indicator, '_delegation_pips')
        assert indicator._delegation_pips == []

    def test_pip_layout_spacing(self):
        indicator = RecordingIndicator()
        assert indicator._pip_layout.spacing() == 3


class TestAddRemovePip:
    """Task 2.3: add_delegation_pip / remove_delegation_pip."""

    def test_add_pip_returns_delegation_pip(self):
        indicator = RecordingIndicator()
        pip = indicator.add_delegation_pip()
        assert isinstance(pip, DelegationPip)
        assert pip in indicator._delegation_pips

    def test_add_multiple_pips(self):
        indicator = RecordingIndicator()
        p1 = indicator.add_delegation_pip()
        p2 = indicator.add_delegation_pip()
        p3 = indicator.add_delegation_pip()
        assert len(indicator._delegation_pips) == 3
        assert indicator._pip_layout.count() == 3

    def test_remove_pip(self):
        indicator = RecordingIndicator()
        pip = indicator.add_delegation_pip()
        indicator.remove_delegation_pip(pip)
        assert pip not in indicator._delegation_pips
        assert indicator._pip_layout.count() == 0

    def test_remove_nonexistent_pip_is_safe(self):
        indicator = RecordingIndicator()
        orphan = DelegationPip()
        # Should not raise
        indicator.remove_delegation_pip(orphan)
        assert len(indicator._delegation_pips) == 0


class TestPillSizing:
    """Task 2.2: Pill width adjusts when pips are present."""

    def test_idle_no_pips_width_36(self):
        indicator = RecordingIndicator()
        assert indicator.minimumWidth() == 36
        assert indicator.maximumWidth() == 36

    def test_idle_with_one_pip_width_at_least_44(self):
        indicator = RecordingIndicator()
        indicator.add_delegation_pip()
        # _refresh_pill_size called by add_delegation_pip
        assert indicator.minimumWidth() >= 44

    def test_idle_with_two_pips_wider_than_one(self):
        indicator = RecordingIndicator()
        indicator.add_delegation_pip()
        w1 = indicator.minimumWidth()
        indicator.add_delegation_pip()
        w2 = indicator.minimumWidth()
        assert w2 > w1

    def test_idle_shrinks_back_after_pip_removed(self):
        indicator = RecordingIndicator()
        pip = indicator.add_delegation_pip()
        assert indicator.minimumWidth() >= 44
        indicator.remove_delegation_pip(pip)
        assert indicator.minimumWidth() == 36

    def test_pip_width_extra_zero_when_empty(self):
        indicator = RecordingIndicator()
        assert indicator._pip_width_extra() == 0

    def test_pip_width_extra_positive_with_pips(self):
        indicator = RecordingIndicator()
        indicator.add_delegation_pip()
        assert indicator._pip_width_extra() > 0


class TestPipCleanup:
    """Task 2.4: Auto-remove on COMPLETE fade, remove FAILED on recording start."""

    def test_complete_fade_auto_removes_pip(self):
        """COMPLETE pip removed after fade-out finishes."""
        indicator = RecordingIndicator()
        pip = indicator.add_delegation_pip()
        pip.set_state(DelegationPip.STATE_COMPLETE)
        pip._start_complete_fade()

        # Simulate fade ticks until finished
        for _ in range(100):
            if pip._opacity <= 0.0:
                break
            pip._fade_tick()

        # finished signal fires -> lambda removes pip
        assert pip not in indicator._delegation_pips

    def test_failed_pips_removed_on_recording_start(self):
        """FAILED pips cleared when user starts a new recording."""
        indicator = RecordingIndicator()
        p1 = indicator.add_delegation_pip()
        p2 = indicator.add_delegation_pip()
        p1.set_state(DelegationPip.STATE_FAILED)
        p2.set_state(DelegationPip.STATE_PROCESSING)

        # Simulate recording start (calls _remove_failed_pips internally)
        indicator._remove_failed_pips()

        assert p1 not in indicator._delegation_pips
        assert p2 in indicator._delegation_pips
        assert len(indicator._delegation_pips) == 1

    def test_sent_pip_not_removed_on_recording_start(self):
        """SENT pips should survive recording start."""
        indicator = RecordingIndicator()
        pip = indicator.add_delegation_pip()
        assert pip.state == DelegationPip.STATE_SENT
        indicator._remove_failed_pips()
        assert pip in indicator._delegation_pips


class TestRefreshPillSize:
    """_refresh_pill_size updates width for current state."""

    def test_refresh_in_idle(self):
        indicator = RecordingIndicator()
        indicator.add_delegation_pip()
        # Force back to idle to verify refresh logic
        indicator._state = indicator.STATE_IDLE
        indicator._refresh_pill_size()
        assert indicator.minimumWidth() >= 44

    def test_refresh_in_recording(self):
        indicator = RecordingIndicator()
        indicator._state = indicator.STATE_RECORDING
        pip = indicator.add_delegation_pip()
        # Recording base is 130, should be more with pip
        assert indicator.minimumWidth() > 130

    def test_refresh_in_transcribing(self):
        indicator = RecordingIndicator()
        indicator._state = indicator.STATE_TRANSCRIBING
        indicator.add_delegation_pip()
        assert indicator.minimumWidth() > 60

    def test_refresh_in_cancelled(self):
        indicator = RecordingIndicator()
        indicator._state = indicator.STATE_CANCELLED
        indicator.add_delegation_pip()
        assert indicator.minimumWidth() > 160


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
