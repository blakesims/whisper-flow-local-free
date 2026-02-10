"""
Tests for Phase 8A: Iteration Feedback Rendering.

Tests:
- /api/action/<id>/iterations includes strengths in response
- Rounds with no judge data have scores=None (no crash)
- score_history data structure present and ordered
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestIterationsIncludesStrengths:
    """Test that GET /api/action/<id>/iterations includes strengths field."""

    def _setup(self, tmp_path):
        """Create transcript with judge data including strengths."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)

        transcript = {
            "id": "test-strengths",
            "title": "Strengths Test",
            "decimal": "50.01.01",
            "transcript": "Test content.",
            "source": {"type": "audio"},
            "analysis": {
                "linkedin_v2": {
                    "post": "Draft 1 text",
                    "_model": "gemini-2.0-flash",
                    "_analyzed_at": "2026-02-09T10:00:00",
                    "_round": 1,
                    "_history": {
                        "scores": [
                            {"round": 0, "overall": 3.2},
                            {"round": 1, "overall": 4.1},
                        ]
                    },
                },
                "linkedin_v2_0": {
                    "post": "Draft 0 text",
                    "_model": "gemini-2.0-flash",
                    "_analyzed_at": "2026-02-09T09:00:00",
                },
                "linkedin_v2_1": {
                    "post": "Draft 1 text",
                    "_model": "gemini-2.0-flash",
                    "_analyzed_at": "2026-02-09T10:00:00",
                },
                "linkedin_judge_0": {
                    "overall_score": 3.2,
                    "scores": {"hook_strength": 3, "structure": 4},
                    "improvements": [
                        {
                            "criterion": "hook_strength",
                            "current_issue": "Hook is generic",
                            "suggestion": "Use a specific stat or question",
                        }
                    ],
                    "strengths": [
                        "Clear structure with logical flow",
                        "Good use of examples",
                    ],
                    "rewritten_hook": "Did you know 80% of content fails?",
                },
                "linkedin_judge_1": {
                    "overall_score": 4.1,
                    "scores": {"hook_strength": 4, "structure": 4},
                    "improvements": [],
                    "strengths": [
                        "Strong hook with data point",
                        "Excellent structure",
                        "Engaging closing CTA",
                    ],
                    "rewritten_hook": None,
                },
            },
        }
        (decimal_dir / "test-strengths.json").write_text(json.dumps(transcript))

        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')
        return state_file

    def test_strengths_present_in_response(self, tmp_path):
        """Iterations response should include strengths array."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-strengths--linkedin_v2/iterations")
                assert response.status_code == 200

                data = response.get_json()
                assert data["total_rounds"] == 2

                # Round 0 should have strengths
                r0 = data["iterations"][0]
                assert "strengths" in r0["scores"]
                assert len(r0["scores"]["strengths"]) == 2
                assert "Clear structure" in r0["scores"]["strengths"][0]

                # Round 1 should have strengths
                r1 = data["iterations"][1]
                assert "strengths" in r1["scores"]
                assert len(r1["scores"]["strengths"]) == 3

    def test_improvements_have_full_structure(self, tmp_path):
        """Improvements should include criterion, current_issue, suggestion."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-strengths--linkedin_v2/iterations")
                data = response.get_json()

                r0 = data["iterations"][0]
                improvements = r0["scores"]["improvements"]
                assert len(improvements) == 1
                assert improvements[0]["criterion"] == "hook_strength"
                assert "generic" in improvements[0]["current_issue"]
                assert "stat" in improvements[0]["suggestion"]

    def test_rewritten_hook_present_when_provided(self, tmp_path):
        """Rewritten hook should be present when judge provided one."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-strengths--linkedin_v2/iterations")
                data = response.get_json()

                r0 = data["iterations"][0]
                assert r0["scores"]["rewritten_hook"] == "Did you know 80% of content fails?"

                r1 = data["iterations"][1]
                assert r1["scores"]["rewritten_hook"] is None

    def test_score_history_present_and_ordered(self, tmp_path):
        """score_history should be present with correct order."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-strengths--linkedin_v2/iterations")
                data = response.get_json()

                assert len(data["score_history"]) == 2
                assert data["score_history"][0]["overall"] == 3.2
                assert data["score_history"][1]["overall"] == 4.1

    def test_empty_strengths_when_not_in_judge_data(self, tmp_path):
        """Strengths should default to empty list when missing from judge data."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)

        transcript = {
            "id": "no-strengths",
            "title": "No Strengths",
            "decimal": "50.01.01",
            "transcript": "Test.",
            "source": {"type": "audio"},
            "analysis": {
                "linkedin_v2": {
                    "post": "Draft",
                    "_model": "gemini",
                    "_analyzed_at": "2026-02-09T10:00:00",
                    "_round": 0,
                    "_history": {"scores": []},
                },
                "linkedin_v2_0": {"post": "Draft", "_analyzed_at": "2026-02-09T10:00:00"},
                "linkedin_judge_0": {
                    "overall_score": 3.0,
                    "scores": {"hook_strength": 3},
                    "improvements": [],
                    # Note: no "strengths" key at all
                },
            },
        }
        (decimal_dir / "no-strengths.json").write_text(json.dumps(transcript))

        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/no-strengths--linkedin_v2/iterations")
                data = response.get_json()

                r0 = data["iterations"][0]
                assert r0["scores"]["strengths"] == []


class TestNoJudgeDataNoCrash:
    """Test that rounds without judge data render safely."""

    def test_unjudged_round_has_scores_none(self, tmp_path):
        """Round without judge data should have scores=None."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)

        transcript = {
            "id": "unjudged",
            "title": "Unjudged",
            "decimal": "50.01.01",
            "transcript": "Test.",
            "source": {"type": "audio"},
            "analysis": {
                "linkedin_v2": {
                    "post": "Draft 0",
                    "_model": "gemini",
                    "_analyzed_at": "2026-02-09T10:00:00",
                    "_round": 0,
                    "_history": {"scores": []},
                },
                "linkedin_v2_0": {"post": "Draft 0", "_analyzed_at": "2026-02-09T10:00:00"},
                # No linkedin_judge_0 -- not yet judged
            },
        }
        (decimal_dir / "unjudged.json").write_text(json.dumps(transcript))

        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/unjudged--linkedin_v2/iterations")
                assert response.status_code == 200

                data = response.get_json()
                assert data["total_rounds"] == 1
                assert data["iterations"][0]["scores"] is None


class TestPreT023StrengthsBackwardCompat:
    """Test strengths in pre-T023 backward compat path."""

    def test_unversioned_judge_includes_strengths(self, tmp_path):
        """Pre-T023 content with unversioned judge should include strengths."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)

        transcript = {
            "id": "old-content",
            "title": "Old Content",
            "decimal": "50.01.01",
            "transcript": "Test.",
            "source": {"type": "audio"},
            "analysis": {
                "linkedin_v2": {
                    "post": "Old post text",
                    "_model": "gemini",
                    "_analyzed_at": "2026-02-07T10:00:00",
                },
                # Unversioned judge (no _0 suffix)
                "linkedin_judge": {
                    "overall_score": 3.0,
                    "scores": {"hook_strength": 3},
                    "improvements": [],
                    "strengths": ["Good opener", "Solid structure"],
                    "rewritten_hook": "Better hook text",
                },
            },
        }
        (decimal_dir / "old-content.json").write_text(json.dumps(transcript))

        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/old-content--linkedin_v2/iterations")
                assert response.status_code == 200

                data = response.get_json()
                assert data["total_rounds"] == 1
                r0 = data["iterations"][0]
                assert r0["scores"]["strengths"] == ["Good opener", "Solid structure"]
                assert r0["scores"]["rewritten_hook"] == "Better hook text"
