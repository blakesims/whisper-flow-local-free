"""Tests for DelegationPip widget — timer connection management and state transitions."""

import sys
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, SIGNAL

from app.daemon.recording_indicator import DelegationPip, COLORS

# QApplication must exist before creating any QWidget
app = QApplication.instance() or QApplication(sys.argv)

# PySide6 receivers() requires SIGNAL() byte format
TIMEOUT_SIGNAL = SIGNAL("timeout()")


class TestDelegationPipInit:
    """Test initial state."""

    def test_initial_state_is_sent(self):
        pip = DelegationPip()
        assert pip.state == DelegationPip.STATE_SENT

    def test_initial_opacity(self):
        pip = DelegationPip()
        assert pip._opacity == 0.85

    def test_initial_color_is_orange(self):
        pip = DelegationPip()
        assert pip._color.name() == COLORS['orange'].name()

    def test_fade_timer_not_connected_at_init(self):
        """Critical: _fade_timer must NOT have any handler connected in __init__."""
        pip = DelegationPip()
        assert not pip._fade_timer.isActive()
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 0


class TestDelegationPipStates:
    """Test state transitions set correct color/opacity."""

    def test_sent_state(self):
        pip = DelegationPip()
        pip.set_state(DelegationPip.STATE_SENT)
        assert pip._color.name() == COLORS['orange'].name()
        assert pip._opacity == 0.85

    def test_processing_state_starts_pulse(self):
        pip = DelegationPip()
        pip.set_state(DelegationPip.STATE_PROCESSING)
        assert pip._color.name() == COLORS['orange'].name()
        assert pip._opacity == 1.0
        assert pip._pulse_timer.isActive()

    def test_complete_state_color_green(self):
        pip = DelegationPip()
        pip.set_state(DelegationPip.STATE_COMPLETE)
        assert pip._color.name() == COLORS['green'].name()
        assert pip._opacity == 1.0

    def test_failed_state_color_red(self):
        pip = DelegationPip()
        pip.set_state(DelegationPip.STATE_FAILED)
        assert pip._color.name() == COLORS['red'].name()
        assert pip._opacity == 1.0


class TestFadeTimerConnections:
    """Verify _fade_timer has exactly one handler connected per state."""

    def test_complete_fade_connects_fade_tick(self):
        pip = DelegationPip()
        pip.set_state(DelegationPip.STATE_COMPLETE)
        pip._start_complete_fade()
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 1
        assert pip._fade_timer.isActive()

    def test_failed_settle_connects_settle_tick(self):
        pip = DelegationPip()
        pip.set_state(DelegationPip.STATE_FAILED)
        pip._start_failed_settle()
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 1
        assert pip._fade_timer.isActive()

    def test_stop_all_timers_disconnects_fade_timer(self):
        pip = DelegationPip()
        pip._start_complete_fade()
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 1
        pip._stop_all_timers()
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 0
        assert not pip._fade_timer.isActive()

    def test_no_dual_handlers_complete_after_failed(self):
        """FAILED -> COMPLETE must not leave _settle_tick connected."""
        pip = DelegationPip()
        pip.set_state(DelegationPip.STATE_FAILED)
        pip._start_failed_settle()
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 1

        # Transition to COMPLETE -- _stop_all_timers disconnects _settle_tick
        pip.set_state(DelegationPip.STATE_COMPLETE)
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 0

        # Now start complete fade -- exactly 1 handler
        pip._start_complete_fade()
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 1

    def test_no_dual_handlers_failed_after_complete(self):
        """COMPLETE -> FAILED must not leave _fade_tick connected."""
        pip = DelegationPip()
        pip.set_state(DelegationPip.STATE_COMPLETE)
        pip._start_complete_fade()
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 1

        pip.set_state(DelegationPip.STATE_FAILED)
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 0

        pip._start_failed_settle()
        assert pip._fade_timer.receivers(TIMEOUT_SIGNAL) == 1


class TestFailedDoesNotEmitFinished:
    """Critical: FAILED state must never emit the finished signal."""

    def test_settle_tick_does_not_emit_finished(self):
        pip = DelegationPip()
        finished_emitted = []
        pip.finished.connect(lambda: finished_emitted.append(True))

        pip.set_state(DelegationPip.STATE_FAILED)
        pip._start_failed_settle()

        # Simulate enough ticks to go from 1.0 well past 0.35
        for _ in range(100):
            pip._settle_tick()

        assert len(finished_emitted) == 0
        assert pip._opacity == 0.35

    def test_failed_opacity_settles_at_035(self):
        pip = DelegationPip()
        pip.set_state(DelegationPip.STATE_FAILED)
        pip._start_failed_settle()

        for _ in range(50):
            pip._settle_tick()

        assert pip._opacity == 0.35


class TestCompleteFadeEmitsFinished:
    """COMPLETE state fade-out must emit finished exactly once when opacity reaches 0."""

    def test_fade_tick_emits_finished_once(self):
        pip = DelegationPip()
        finished_emitted = []
        pip.finished.connect(lambda: finished_emitted.append(True))

        pip.set_state(DelegationPip.STATE_COMPLETE)
        pip._start_complete_fade()

        # Simulate ticks; _fade_tick stops the timer at 0.0 but we call manually,
        # so count until opacity hits 0 and stop.
        for _ in range(100):
            if pip._opacity <= 0.0:
                break
            pip._fade_tick()

        assert len(finished_emitted) == 1
        assert pip._opacity == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
