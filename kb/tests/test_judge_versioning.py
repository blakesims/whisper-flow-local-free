"""
Tests for T023 Phase 1: Judge Versioning + Auto-Judge Pipeline.

Tests:
- Versioned saves (linkedin_v2_0, linkedin_judge_0, etc.)
- Alias updates (_round, _history metadata)
- History injection (JSON array of all prior rounds)
- Backward compat (existing linkedin_v2 without _round)
- Versioned key filtering in scan_actionable_items()
- Auto-judge type mapping
- Migration of approved items to draft
- Starting round calculation
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from copy import deepcopy

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ===== Versioned Key Helpers =====

class TestGetStartingRound:
    """Tests for _get_starting_round helper."""

    def test_fresh_start_returns_zero(self):
        """No existing data should return round 0."""
        from kb.analyze import _get_starting_round
        assert _get_starting_round({}, "linkedin_v2") == 0

    def test_existing_versioned_keys(self):
        """Should return next round after highest versioned key."""
        from kb.analyze import _get_starting_round
        analysis = {
            "linkedin_v2_0": {"post": "draft 0"},
            "linkedin_v2_1": {"post": "draft 1"},
            "linkedin_judge_0": {"overall_score": 3.0},
        }
        assert _get_starting_round(analysis, "linkedin_v2") == 2

    def test_existing_alias_without_round_metadata(self):
        """Alias without _round should be treated as round 0 (backward compat)."""
        from kb.analyze import _get_starting_round
        analysis = {
            "linkedin_v2": {"post": "old draft", "_model": "gemini-2.0-flash"},
        }
        assert _get_starting_round(analysis, "linkedin_v2") == 0

    def test_existing_alias_with_round_metadata(self):
        """Alias with _round but no versioned keys should still check versioned keys."""
        from kb.analyze import _get_starting_round
        analysis = {
            "linkedin_v2": {"post": "draft", "_round": 1},
            "linkedin_v2_0": {"post": "draft 0"},
            "linkedin_v2_1": {"post": "draft 1"},
        }
        assert _get_starting_round(analysis, "linkedin_v2") == 2

    def test_ignores_edit_versions(self):
        """Should not count edit sub-versions (linkedin_v2_1_0) as rounds."""
        from kb.analyze import _get_starting_round
        analysis = {
            "linkedin_v2_0": {"post": "draft 0"},
            "linkedin_v2_0_0": {"post": "edit 0 of round 0"},
            "linkedin_v2_0_1": {"post": "edit 1 of round 0"},
        }
        assert _get_starting_round(analysis, "linkedin_v2") == 1


class TestBuildHistoryFromExisting:
    """Tests for _build_history_from_existing helper."""

    def test_empty_analysis(self):
        """No versioned keys should return empty history."""
        from kb.analyze import _build_history_from_existing
        assert _build_history_from_existing({}, "linkedin_v2", "linkedin_judge") == []

    def test_single_round_with_judge(self):
        """One draft + one judge should produce one history entry."""
        from kb.analyze import _build_history_from_existing
        analysis = {
            "linkedin_v2_0": {"post": "draft text"},
            "linkedin_judge_0": {
                "overall_score": 3.4,
                "scores": {"hook_strength": 3},
                "improvements": [{"criterion": "hook", "suggestion": "fix it"}],
                "rewritten_hook": "Better hook",
            },
        }
        history = _build_history_from_existing(analysis, "linkedin_v2", "linkedin_judge")
        assert len(history) == 1
        assert history[0]["round"] == 0
        assert history[0]["draft"] == "draft text"
        assert history[0]["judge"]["overall_score"] == 3.4
        assert history[0]["judge"]["rewritten_hook"] == "Better hook"

    def test_multiple_rounds(self):
        """Multiple rounds should produce ordered history."""
        from kb.analyze import _build_history_from_existing
        analysis = {
            "linkedin_v2_0": {"post": "draft 0"},
            "linkedin_judge_0": {"overall_score": 3.0, "scores": {}, "improvements": []},
            "linkedin_v2_1": {"post": "draft 1"},
            "linkedin_judge_1": {"overall_score": 4.0, "scores": {}, "improvements": []},
        }
        history = _build_history_from_existing(analysis, "linkedin_v2", "linkedin_judge")
        assert len(history) == 2
        assert history[0]["round"] == 0
        assert history[1]["round"] == 1

    def test_draft_without_judge(self):
        """Draft without corresponding judge should still be in history."""
        from kb.analyze import _build_history_from_existing
        analysis = {
            "linkedin_v2_0": {"post": "draft 0"},
        }
        history = _build_history_from_existing(analysis, "linkedin_v2", "linkedin_judge")
        assert len(history) == 1
        assert "judge" not in history[0]


class TestBuildScoreHistory:
    """Tests for _build_score_history helper."""

    def test_empty(self):
        """No judge keys should return empty list."""
        from kb.analyze import _build_score_history
        assert _build_score_history({}, "linkedin_judge") == []

    def test_builds_scores(self):
        """Should build score entries from versioned judge keys."""
        from kb.analyze import _build_score_history
        analysis = {
            "linkedin_judge_0": {"overall_score": 3.0, "scores": {"hook": 3}},
            "linkedin_judge_1": {"overall_score": 4.0, "scores": {"hook": 4}},
        }
        scores = _build_score_history(analysis, "linkedin_judge")
        assert len(scores) == 2
        assert scores[0] == {"round": 0, "overall": 3.0, "criteria": {"hook": 3}}
        assert scores[1] == {"round": 1, "overall": 4.0, "criteria": {"hook": 4}}


class TestUpdateAlias:
    """Tests for _update_alias helper."""

    def test_sets_round_and_history(self):
        """Alias should have _round and _history metadata."""
        from kb.analyze import _update_alias
        analysis = {
            "linkedin_judge_0": {"overall_score": 3.5, "scores": {"hook": 3}},
        }
        draft = {"post": "text", "_model": "gemini-2.0-flash"}
        _update_alias(analysis, "linkedin_v2", "linkedin_judge", draft, 0)

        alias = analysis["linkedin_v2"]
        assert alias["_round"] == 0
        assert alias["post"] == "text"
        assert "_history" in alias
        assert len(alias["_history"]["scores"]) == 1
        assert alias["_history"]["scores"][0]["overall"] == 3.5

    def test_does_not_mutate_original(self):
        """Alias should be a copy, not the same reference."""
        from kb.analyze import _update_alias
        analysis = {}
        draft = {"post": "text"}
        _update_alias(analysis, "linkedin_v2", "linkedin_judge", draft, 0)

        # Modifying draft should not affect alias
        draft["post"] = "changed"
        assert analysis["linkedin_v2"]["post"] == "text"


# ===== Run With Judge Loop (Versioned) =====

class TestRunWithJudgeLoopVersioned:
    """Tests for refactored run_with_judge_loop with versioning."""

    def _make_transcript_data(self):
        return {
            "id": "test-transcript",
            "title": "Test",
            "transcript": "This is a test transcript.",
            "analysis": {},
        }

    @patch("kb.analyze.run_analysis_with_deps")
    @patch("kb.analyze.analyze_transcript")
    def test_saves_versioned_keys_on_fresh_start(self, mock_analyze, mock_deps):
        """Fresh run should save linkedin_v2_0 and linkedin_judge_0."""
        from kb.analyze import run_with_judge_loop

        draft = {"post": "Draft text", "character_count": 100}
        judge = {
            "overall_score": 3.5,
            "scores": {"hook_strength": 3},
            "improvements": [{"criterion": "hook", "suggestion": "fix"}],
        }
        improved = {"post": "Improved text", "character_count": 120}

        mock_deps.side_effect = [
            (draft, []),    # Initial draft
            (judge, []),    # Judge evaluation
        ]
        mock_analyze.return_value = improved  # Improved draft

        data = self._make_transcript_data()
        final, judge_result = run_with_judge_loop(
            transcript_data=data,
            analysis_type="linkedin_v2",
            judge_type="linkedin_judge",
            max_rounds=1,
            existing_analysis=data["analysis"]
        )

        analysis = data["analysis"]

        # Versioned keys should exist
        assert "linkedin_v2_0" in analysis
        assert "linkedin_judge_0" in analysis
        assert "linkedin_v2_1" in analysis

        # Alias should point to latest
        assert analysis["linkedin_v2"]["post"] == "Improved text"
        assert analysis["linkedin_v2"]["_round"] == 1
        assert "_history" in analysis["linkedin_v2"]

    @patch("kb.analyze.run_analysis_with_deps")
    @patch("kb.analyze.analyze_transcript")
    def test_backward_compat_existing_unversioned(self, mock_analyze, mock_deps):
        """Existing linkedin_v2 without _round should be migrated to _0."""
        from kb.analyze import run_with_judge_loop

        judge = {
            "overall_score": 4.0,
            "scores": {"hook_strength": 4},
            "improvements": [],
        }
        improved = {"post": "Improved text", "character_count": 120}

        mock_deps.return_value = (judge, [])   # Judge evaluation
        mock_analyze.return_value = improved   # Improved draft

        data = self._make_transcript_data()
        # Pre-existing unversioned result
        data["analysis"]["linkedin_v2"] = {
            "post": "Old draft",
            "_model": "gemini-2.0-flash",
            "_analyzed_at": "2026-02-07T10:00:00",
        }

        final, judge_result = run_with_judge_loop(
            transcript_data=data,
            analysis_type="linkedin_v2",
            judge_type="linkedin_judge",
            max_rounds=1,
            existing_analysis=data["analysis"]
        )

        analysis = data["analysis"]

        # Old result should be preserved as _0
        assert "linkedin_v2_0" in analysis
        assert analysis["linkedin_v2_0"]["post"] == "Old draft"

        # Round 1: new draft generated (with history from round 0)
        assert "linkedin_v2_1" in analysis

        # Judge runs on the new draft (round 1), saved as linkedin_judge_1
        assert "linkedin_judge_1" in analysis

        # Improved draft is round 2
        assert "linkedin_v2_2" in analysis
        assert analysis["linkedin_v2_2"]["post"] == "Improved text"

        # Alias should point to latest round
        assert analysis["linkedin_v2"]["_round"] == 2

    @patch("kb.analyze.run_analysis_with_deps")
    @patch("kb.analyze.analyze_transcript")
    def test_backward_compat_existing_unversioned_with_judge(self, mock_analyze, mock_deps):
        """Existing linkedin_v2 + linkedin_judge without _round should both be migrated to _0."""
        from kb.analyze import run_with_judge_loop

        judge = {
            "overall_score": 4.0,
            "scores": {"hook_strength": 4},
            "improvements": [],
        }
        improved = {"post": "Improved text", "character_count": 120}

        mock_deps.return_value = (judge, [])   # Judge evaluation
        mock_analyze.return_value = improved   # Improved draft

        data = self._make_transcript_data()
        # Pre-existing unversioned results (both draft and judge)
        data["analysis"]["linkedin_v2"] = {
            "post": "Old draft",
            "_model": "gemini-2.0-flash",
            "_analyzed_at": "2026-02-07T10:00:00",
        }
        data["analysis"]["linkedin_judge"] = {
            "overall_score": 3.2,
            "scores": {"hook_strength": 3},
            "improvements": [{"criterion": "hook", "suggestion": "fix"}],
        }

        final, judge_result = run_with_judge_loop(
            transcript_data=data,
            analysis_type="linkedin_v2",
            judge_type="linkedin_judge",
            max_rounds=1,
            existing_analysis=data["analysis"]
        )

        analysis = data["analysis"]

        # Old results should be preserved as _0
        assert "linkedin_v2_0" in analysis
        assert analysis["linkedin_v2_0"]["post"] == "Old draft"
        assert "linkedin_judge_0" in analysis
        assert analysis["linkedin_judge_0"]["overall_score"] == 3.2
        assert analysis["linkedin_judge_0"]["scores"]["hook_strength"] == 3

        # Round 1: new draft generated
        assert "linkedin_v2_1" in analysis

        # Alias should point to latest round
        assert analysis["linkedin_v2"]["_round"] == 2

    @patch("kb.analyze.run_analysis_with_deps")
    def test_no_judge_rounds(self, mock_deps):
        """max_rounds=0 should just produce the initial draft."""
        from kb.analyze import run_with_judge_loop

        draft = {"post": "Draft text", "character_count": 100}
        mock_deps.return_value = (draft, [])

        data = self._make_transcript_data()
        final, judge_result = run_with_judge_loop(
            transcript_data=data,
            analysis_type="linkedin_v2",
            judge_type="linkedin_judge",
            max_rounds=0,
            existing_analysis=data["analysis"]
        )

        analysis = data["analysis"]

        # Should have draft _0 and alias, no judge
        assert "linkedin_v2_0" in analysis
        assert "linkedin_judge_0" not in analysis
        assert analysis["linkedin_v2"]["_round"] == 0
        assert judge_result is None

    @patch("kb.analyze.run_analysis_with_deps")
    @patch("kb.analyze.analyze_transcript")
    def test_history_injection_format(self, mock_analyze, mock_deps):
        """Judge feedback should be a JSON array of all prior rounds."""
        from kb.analyze import run_with_judge_loop

        draft = {"post": "Draft 0", "character_count": 100}
        judge = {
            "overall_score": 3.0,
            "scores": {"hook_strength": 3},
            "improvements": [{"criterion": "hook", "suggestion": "fix"}],
            "rewritten_hook": "Better hook",
        }
        improved = {"post": "Draft 1", "character_count": 120}

        mock_deps.side_effect = [
            (draft, []),    # Initial draft
            (judge, []),    # Judge
        ]
        mock_analyze.return_value = improved

        data = self._make_transcript_data()
        run_with_judge_loop(
            transcript_data=data,
            analysis_type="linkedin_v2",
            judge_type="linkedin_judge",
            max_rounds=1,
            existing_analysis=data["analysis"]
        )

        # Verify the judge_feedback passed to analyze_transcript
        call_kwargs = mock_analyze.call_args
        context = call_kwargs.kwargs.get("prerequisite_context") or call_kwargs[1].get("prerequisite_context")
        assert "judge_feedback" in context

        # Parse the judge_feedback as JSON array
        feedback = json.loads(context["judge_feedback"])
        assert isinstance(feedback, list)
        assert len(feedback) == 1
        assert feedback[0]["round"] == 0
        assert feedback[0]["draft"] == "Draft 0"
        assert feedback[0]["judge"]["overall_score"] == 3.0

    @patch("kb.analyze.run_analysis_with_deps")
    def test_judge_failure_keeps_draft(self, mock_deps):
        """If judge fails, draft should be preserved."""
        from kb.analyze import run_with_judge_loop

        draft = {"post": "Good draft", "character_count": 100}
        judge_error = {"error": "API error"}

        mock_deps.side_effect = [
            (draft, []),        # Initial draft
            (judge_error, []),  # Judge fails
        ]

        data = self._make_transcript_data()
        final, judge_result = run_with_judge_loop(
            transcript_data=data,
            analysis_type="linkedin_v2",
            judge_type="linkedin_judge",
            max_rounds=1,
            existing_analysis=data["analysis"]
        )

        # Draft should be saved
        assert final["post"] == "Good draft"
        assert "linkedin_v2_0" in data["analysis"]
        # Alias should point to draft
        assert data["analysis"]["linkedin_v2"]["post"] == "Good draft"
        assert data["analysis"]["linkedin_v2"]["_round"] == 0

    @patch("kb.analyze.run_analysis_with_deps")
    @patch("kb.analyze.analyze_transcript")
    def test_saves_to_file_when_path_provided(self, mock_analyze, mock_deps):
        """Results should be saved to file when save_path provided."""
        from kb.analyze import run_with_judge_loop

        draft = {"post": "Draft text", "character_count": 100}
        judge = {
            "overall_score": 3.5,
            "scores": {"hook_strength": 3},
            "improvements": [],
        }
        improved = {"post": "Better text", "character_count": 110}

        mock_deps.side_effect = [
            (draft, []),
            (judge, []),
        ]
        mock_analyze.return_value = improved

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            data = {
                "id": "test",
                "title": "Test",
                "transcript": "Test transcript",
                "analysis": {},
            }
            json.dump(data, f)
            path = f.name

        try:
            run_with_judge_loop(
                transcript_data=data,
                analysis_type="linkedin_v2",
                judge_type="linkedin_judge",
                max_rounds=1,
                existing_analysis=data["analysis"],
                save_path=path
            )

            # Read back and verify
            with open(path) as f:
                saved = json.load(f)

            assert "linkedin_v2_0" in saved["analysis"]
            assert "linkedin_v2_1" in saved["analysis"]
            assert "linkedin_judge_0" in saved["analysis"]
            assert saved["analysis"]["linkedin_v2"]["_round"] == 1
        finally:
            os.unlink(path)


# ===== Auto-Judge Type Mapping =====

class TestAutoJudgeTypes:
    """Tests for AUTO_JUDGE_TYPES mapping."""

    def test_linkedin_v2_has_auto_judge(self):
        """linkedin_v2 should map to linkedin_judge."""
        from kb.analyze import AUTO_JUDGE_TYPES
        assert AUTO_JUDGE_TYPES["linkedin_v2"] == "linkedin_judge"

    def test_summary_not_auto_judge(self):
        """Non-judge types should not be in AUTO_JUDGE_TYPES."""
        from kb.analyze import AUTO_JUDGE_TYPES
        assert "summary" not in AUTO_JUDGE_TYPES


# ===== Versioned Key Filtering =====

class TestVersionedKeyFiltering:
    """Tests for VERSIONED_KEY_PATTERN in scan_actionable_items."""

    def test_pattern_matches_versioned_draft(self):
        """linkedin_v2_0, linkedin_v2_1 should match versioned pattern."""
        from kb.serve import VERSIONED_KEY_PATTERN
        assert VERSIONED_KEY_PATTERN.match("linkedin_v2_0")
        assert VERSIONED_KEY_PATTERN.match("linkedin_v2_1")
        assert VERSIONED_KEY_PATTERN.match("linkedin_v2_42")

    def test_pattern_matches_versioned_judge(self):
        """linkedin_judge_0 should match versioned pattern."""
        from kb.serve import VERSIONED_KEY_PATTERN
        assert VERSIONED_KEY_PATTERN.match("linkedin_judge_0")
        assert VERSIONED_KEY_PATTERN.match("linkedin_judge_1")

    def test_pattern_matches_edit_versions(self):
        """linkedin_v2_1_0 should match versioned pattern."""
        from kb.serve import VERSIONED_KEY_PATTERN
        assert VERSIONED_KEY_PATTERN.match("linkedin_v2_1_0")
        assert VERSIONED_KEY_PATTERN.match("linkedin_v2_2_1")

    def test_pattern_does_not_match_alias(self):
        """linkedin_v2 (alias) should NOT match versioned pattern."""
        from kb.serve import VERSIONED_KEY_PATTERN
        assert not VERSIONED_KEY_PATTERN.match("linkedin_v2")
        assert not VERSIONED_KEY_PATTERN.match("linkedin_judge")
        assert not VERSIONED_KEY_PATTERN.match("summary")
        assert not VERSIONED_KEY_PATTERN.match("skool_post")

    def test_pattern_does_not_match_unknown_types_ending_in_digits(self):
        """Future analysis types ending in digits should NOT be filtered."""
        from kb.serve import VERSIONED_KEY_PATTERN
        # These are hypothetical analysis types that end with _digits
        # but are NOT versioned keys of known auto-judge types
        assert not VERSIONED_KEY_PATTERN.match("analysis_2025")
        assert not VERSIONED_KEY_PATTERN.match("data_42")
        assert not VERSIONED_KEY_PATTERN.match("report_3")
        assert not VERSIONED_KEY_PATTERN.match("skool_post_1")

    def test_scan_skips_versioned_keys(self, tmp_path):
        """scan_actionable_items should skip versioned keys."""
        from kb.serve import scan_actionable_items, VERSIONED_KEY_PATTERN

        # Create a transcript with versioned and alias keys
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir()

        transcript = {
            "id": "test-id",
            "title": "Test Transcript",
            "source": {"type": "video"},
            "analysis": {
                "linkedin_v2": {"post": "Latest", "_round": 1, "_history": {}},
                "linkedin_v2_0": {"post": "Draft 0"},
                "linkedin_v2_1": {"post": "Draft 1"},
                "linkedin_judge_0": {"overall_score": 3.0},
                "linkedin_judge_1": {"overall_score": 4.0},
                "linkedin_v2_1_0": {"post": "Edit of draft 1"},
            },
        }

        with open(decimal_dir / "test-id.json", "w") as f:
            json.dump(transcript, f)

        with patch("kb.serve.KB_ROOT", tmp_path):
            items = scan_actionable_items()

        # Only the alias should appear, not versioned keys
        types_found = [item["type"] for item in items]
        assert "linkedin_v2" in types_found
        assert "linkedin_v2_0" not in types_found
        assert "linkedin_v2_1" not in types_found
        assert "linkedin_judge_0" not in types_found
        assert "linkedin_judge_1" not in types_found
        assert "linkedin_v2_1_0" not in types_found


# ===== Migration =====

class TestMigrationApprovedToDraft:
    """Tests for migrate_approved_to_draft."""

    def test_migrates_approved_items(self, tmp_path):
        """Approved items should be reset to draft."""
        state_file = tmp_path / "action-state.json"
        state = {
            "actions": {
                "id1--linkedin_v2": {
                    "status": "approved",
                    "completed_at": "2026-02-07T10:00:00",
                },
                "id2--linkedin_v2": {
                    "status": "pending",
                },
                "id3--skool_post": {
                    "status": "approved",
                    "completed_at": "2026-02-06T10:00:00",
                },
            }
        }
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file):
            from kb.serve import migrate_approved_to_draft
            count = migrate_approved_to_draft()

        assert count == 2

        updated = json.loads(state_file.read_text())
        assert updated["actions"]["id1--linkedin_v2"]["status"] == "draft"
        assert updated["actions"]["id1--linkedin_v2"]["_previously_approved_at"] == "2026-02-07T10:00:00"
        assert updated["actions"]["id2--linkedin_v2"]["status"] == "pending"  # Unchanged
        assert updated["actions"]["id3--skool_post"]["status"] == "draft"

    def test_no_approved_items(self, tmp_path):
        """Should return 0 when no approved items."""
        state_file = tmp_path / "action-state.json"
        state = {
            "actions": {
                "id1--linkedin_v2": {"status": "pending"},
            }
        }
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file):
            from kb.serve import migrate_approved_to_draft
            count = migrate_approved_to_draft()

        assert count == 0

    def test_empty_state(self, tmp_path):
        """Should handle empty state gracefully."""
        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')

        with patch("kb.serve.ACTION_STATE_PATH", state_file):
            from kb.serve import migrate_approved_to_draft
            count = migrate_approved_to_draft()

        assert count == 0


class TestMigrateCLI:
    """Tests for the kb migrate CLI command."""

    def test_migrate_module_importable(self):
        """kb.migrate should be importable and have a main function."""
        from kb.migrate import main
        assert callable(main)

    def test_migrate_registered_in_commands(self):
        """migrate should be in the COMMANDS dict."""
        from kb.__main__ import COMMANDS
        assert "migrate" in COMMANDS
        assert COMMANDS["migrate"]["module"] == "kb.migrate"

    def test_migrate_reset_approved_calls_function(self, tmp_path):
        """--reset-approved should call migrate_approved_to_draft."""
        state_file = tmp_path / "action-state.json"
        state = {
            "actions": {
                "id1--linkedin_v2": {
                    "status": "approved",
                    "completed_at": "2026-02-07T10:00:00",
                },
            }
        }
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("sys.argv", ["migrate", "--reset-approved"]):
            from kb.migrate import main
            main()

        updated = json.loads(state_file.read_text())
        assert updated["actions"]["id1--linkedin_v2"]["status"] == "draft"


# ===== LinkedIn V2 JSON Template =====

class TestLinkedinV2HistoryTemplate:
    """Tests for the updated judge_feedback template in linkedin_v2.json."""

    def test_judge_feedback_section_mentions_json_array(self):
        """The improvement round section should reference JSON array history."""
        config_dir = Path(__file__).parent.parent / "config" / "analysis_types"
        with open(config_dir / "linkedin_v2.json") as f:
            config = json.load(f)

        prompt = config["prompt"]
        assert "JSON array" in prompt
        assert "{{judge_feedback}}" in prompt
        assert "{{#if judge_feedback}}" in prompt


# ===== LinkedIn Judge Transcript Access =====

class TestJudgeTranscriptAccess:
    """Verify that linkedin_judge.json has {{transcript}} and it resolves."""

    def test_judge_prompt_contains_transcript_variable(self):
        """Judge prompt should use {{transcript}}."""
        config_dir = Path(__file__).parent.parent / "config" / "analysis_types"
        with open(config_dir / "linkedin_judge.json") as f:
            config = json.load(f)

        assert "{{transcript}}" in config["prompt"]

    def test_resolve_optional_inputs_always_includes_transcript(self):
        """resolve_optional_inputs should always set transcript in context."""
        from kb.analyze import resolve_optional_inputs

        analysis_def = {"optional_inputs": []}
        context = resolve_optional_inputs(analysis_def, {}, "Hello world")

        assert "transcript" in context
        assert context["transcript"] == "Hello world"


# ===== Conditional Template Rendering with History =====

class TestHistoryInjectionTemplate:
    """Tests for history injection through the conditional template system."""

    def test_judge_feedback_renders_when_present(self):
        """{{#if judge_feedback}} block should render when feedback provided."""
        from kb.analyze import render_conditional_template

        template = "Start\n{{#if judge_feedback}}FEEDBACK: {{judge_feedback}}{{/if}}\nEnd"
        context = {"judge_feedback": '[{"round": 0}]'}

        result = render_conditional_template(template, context)
        assert "FEEDBACK:" in result
        assert '[{"round": 0}]' in result

    def test_judge_feedback_omitted_when_absent(self):
        """{{#if judge_feedback}} block should not render without feedback."""
        from kb.analyze import render_conditional_template

        template = "Start\n{{#if judge_feedback}}FEEDBACK: {{judge_feedback}}{{/if}}\nEnd"
        context = {}

        result = render_conditional_template(template, context)
        assert "FEEDBACK:" not in result
        assert "Start" in result
        assert "End" in result
