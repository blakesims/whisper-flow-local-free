"""
Tests for T023 Phase 2: kb serve Iteration View + Approve Rewire.

Tests:
- Stage endpoint (/api/action/<id>/stage)
- Iterate endpoint (/api/action/<id>/iterate)
- Iterations endpoint (/api/action/<id>/iterations)
- Posting queue v2 (iteration grouping)
- Approve handler rewire (no visual pipeline for auto-judge types)
- Migration wiring
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


# ===== Stage Endpoint =====

class TestStageEndpoint:
    """Tests for POST /api/action/<id>/stage."""

    def _setup(self, tmp_path, status="new"):
        """Create transcript and action state."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)
        transcript = {
            "id": "test-id",
            "title": "Test Transcript",
            "decimal": "50.01.01",
            "transcript": "This is a test.",
            "source": {"type": "audio"},
            "analysis": {
                "linkedin_v2": {
                    "post": "Test post content",
                    "_model": "gemini-2.0-flash",
                    "_analyzed_at": "2026-02-08T10:00:00",
                    "_round": 0,
                    "_history": {"scores": []},
                },
            },
        }
        (decimal_dir / "test-id.json").write_text(json.dumps(transcript))

        state = {"actions": {}}
        if status != "new":
            state["actions"]["test-id--linkedin_v2"] = {
                "status": status,
                "copied_count": 0,
                "created_at": "2026-02-08T09:00:00",
            }
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))
        return state_file

    def test_stage_new_item(self, tmp_path):
        """Staging a new item should succeed."""
        state_file = self._setup(tmp_path, "new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/stage")
                assert response.status_code == 200

                data = response.get_json()
                assert data["success"] is True

        # Check state file
        state = json.loads(state_file.read_text())
        assert state["actions"]["test-id--linkedin_v2"]["status"] == "staged"
        assert "staged_at" in state["actions"]["test-id--linkedin_v2"]

    def test_stage_staged_item_succeeds(self, tmp_path):
        """Staging an already-staged item should succeed (re-staging after iteration)."""
        state_file = self._setup(tmp_path, "staged")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/stage")
                assert response.status_code == 200

        state = json.loads(state_file.read_text())
        assert state["actions"]["test-id--linkedin_v2"]["status"] == "staged"

    def test_stage_done_item_fails(self, tmp_path):
        """Staging a done item should fail."""
        state_file = self._setup(tmp_path, "done")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/stage")
                assert response.status_code == 400

    def test_stage_does_not_trigger_visual_pipeline(self, tmp_path):
        """Stage should NOT trigger visual pipeline."""
        state_file = self._setup(tmp_path, "new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.threading.Thread") as mock_thread_cls, \
             patch("kb.serve.pyperclip.copy"):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/stage")
                assert response.status_code == 200

                # No thread should be created (no visual pipeline)
                mock_thread_cls.assert_not_called()

    def test_stage_invalid_id(self, tmp_path):
        """Invalid action ID should return 400."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.post("/api/action/invalid/stage")
            assert response.status_code == 400

    def test_stage_nonexistent_item(self, tmp_path):
        """Staging a nonexistent item should return 404."""
        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/nonexistent--linkedin_v2/stage")
                assert response.status_code == 404


# ===== Iterate Endpoint =====

class TestIterateEndpoint:
    """Tests for POST /api/action/<id>/iterate."""

    def _setup(self, tmp_path):
        """Create transcript with versioned analysis and staged action state."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)
        transcript = {
            "id": "test-id",
            "title": "Test Transcript",
            "decimal": "50.01.01",
            "transcript": "This is a test transcript for iteration.",
            "source": {"type": "audio"},
            "analysis": {
                "linkedin_v2": {
                    "post": "Draft 0 text",
                    "_model": "gemini-2.0-flash",
                    "_analyzed_at": "2026-02-08T10:00:00",
                    "_round": 0,
                    "_history": {"scores": [{"round": 0, "overall": 3.5, "criteria": {"hook_strength": 3}}]},
                },
                "linkedin_v2_0": {
                    "post": "Draft 0 text",
                    "_model": "gemini-2.0-flash",
                    "_analyzed_at": "2026-02-08T10:00:00",
                },
                "linkedin_judge_0": {
                    "overall_score": 3.5,
                    "scores": {"hook_strength": 3},
                    "improvements": [{"criterion": "hook", "suggestion": "improve it"}],
                },
            },
        }
        transcript_path = decimal_dir / "test-id.json"
        transcript_path.write_text(json.dumps(transcript))

        # T028: iterate requires staged status
        state = {"actions": {"test-id--linkedin_v2": {"status": "staged", "copied_count": 0, "created_at": "2026-02-08T09:00:00"}}}
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))
        return state_file, transcript_path

    def test_iterate_starts_background_thread(self, tmp_path):
        """Iterate should start a background thread."""
        state_file, _ = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.threading.Thread") as mock_thread_cls:

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/iterate")
                assert response.status_code == 200

                data = response.get_json()
                assert data["success"] is True
                assert "started" in data["message"].lower()

                mock_thread_cls.assert_called_once()
                mock_thread.start.assert_called_once()

    def test_iterate_sets_iterating_flag(self, tmp_path):
        """Iterate should set iterating=True in action state."""
        state_file, _ = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.threading.Thread") as mock_thread_cls:

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                client.post("/api/action/test-id--linkedin_v2/iterate")

        state = json.loads(state_file.read_text())
        assert state["actions"]["test-id--linkedin_v2"]["iterating"] is True

    def test_iterate_rejects_non_autojudge(self, tmp_path):
        """Iterate should reject non-auto-judge types."""
        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--skool_post/iterate")
                assert response.status_code == 400

    def test_iterate_invalid_id(self):
        """Invalid action ID should return 400."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.post("/api/action/invalid/iterate")
            assert response.status_code == 400

    def test_iterate_missing_transcript(self, tmp_path):
        """Missing transcript file should return 404."""
        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/nonexistent--linkedin_v2/iterate")
                assert response.status_code == 404


# ===== Iterations Endpoint =====

class TestIterationsEndpoint:
    """Tests for GET /api/action/<id>/iterations."""

    def _setup(self, tmp_path, with_scores=True, with_versioned=True):
        """Create transcript with optional versioned analysis."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True, exist_ok=True)

        analysis = {}

        if with_versioned:
            analysis["linkedin_v2"] = {
                "post": "Draft 1 text",
                "_model": "gemini-2.0-flash",
                "_analyzed_at": "2026-02-08T11:00:00",
                "_round": 1,
                "_history": {
                    "scores": [
                        {"round": 0, "overall": 3.5, "criteria": {"hook_strength": 3, "structure": 4}},
                        {"round": 1, "overall": 4.2, "criteria": {"hook_strength": 4, "structure": 4}},
                    ]
                },
            }
            analysis["linkedin_v2_0"] = {
                "post": "Draft 0 text",
                "_model": "gemini-2.0-flash",
                "_analyzed_at": "2026-02-08T10:00:00",
            }
            analysis["linkedin_v2_1"] = {
                "post": "Draft 1 text",
                "_model": "gemini-2.0-flash",
                "_analyzed_at": "2026-02-08T11:00:00",
            }
            if with_scores:
                analysis["linkedin_judge_0"] = {
                    "overall_score": 3.5,
                    "scores": {"hook_strength": 3, "structure": 4},
                    "improvements": [{"criterion": "hook", "suggestion": "improve it"}],
                    "rewritten_hook": "Better hook",
                }
                analysis["linkedin_judge_1"] = {
                    "overall_score": 4.2,
                    "scores": {"hook_strength": 4, "structure": 4},
                    "improvements": [],
                }
        else:
            # Pre-T023 content: alias only, no versioned keys
            analysis["linkedin_v2"] = {
                "post": "Old draft text",
                "_model": "gemini-2.0-flash",
                "_analyzed_at": "2026-02-07T10:00:00",
            }

        transcript = {
            "id": "test-id",
            "title": "Test Transcript",
            "decimal": "50.01.01",
            "transcript": "This is a test.",
            "source": {"type": "audio"},
            "analysis": analysis,
        }
        (decimal_dir / "test-id.json").write_text(json.dumps(transcript))

        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')
        return state_file

    def test_returns_iterations_with_scores(self, tmp_path):
        """Should return all iterations with judge scores."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-id--linkedin_v2/iterations")
                assert response.status_code == 200

                data = response.get_json()
                assert data["total_rounds"] == 2
                assert len(data["iterations"]) == 2

                # Round 0
                r0 = data["iterations"][0]
                assert r0["round"] == 0
                assert r0["post"] == "Draft 0 text"
                assert r0["scores"]["overall"] == 3.5
                assert r0["scores"]["criteria"]["hook_strength"] == 3

                # Round 1
                r1 = data["iterations"][1]
                assert r1["round"] == 1
                assert r1["post"] == "Draft 1 text"
                assert r1["scores"]["overall"] == 4.2

    def test_returns_score_history(self, tmp_path):
        """Should return score_history from alias metadata."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-id--linkedin_v2/iterations")
                data = response.get_json()
                assert len(data["score_history"]) == 2
                assert data["current_round"] == 1

    def test_pre_t023_content_no_versioned_keys(self, tmp_path):
        """Pre-T023 content (no versioned keys) should show as single iteration."""
        state_file = self._setup(tmp_path, with_versioned=False)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-id--linkedin_v2/iterations")
                data = response.get_json()
                assert data["total_rounds"] == 1
                assert data["iterations"][0]["post"] == "Old draft text"
                assert data["iterations"][0]["scores"] is None  # Not judged

    def test_iterations_without_scores(self, tmp_path):
        """Iterations without judge scores should have scores=None."""
        state_file = self._setup(tmp_path, with_scores=False)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-id--linkedin_v2/iterations")
                data = response.get_json()
                assert data["total_rounds"] == 2
                # No judge scores
                assert data["iterations"][0]["scores"] is None
                assert data["iterations"][1]["scores"] is None

    def test_iterating_flag(self, tmp_path):
        """Should reflect iterating state from action-state.json."""
        state_file = self._setup(tmp_path)
        state = json.loads(state_file.read_text())
        state["actions"]["test-id--linkedin_v2"] = {"iterating": True}
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-id--linkedin_v2/iterations")
                data = response.get_json()
                assert data["iterating"] is True

    def test_rejects_non_autojudge(self):
        """Should reject non-auto-judge types."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.get("/api/action/test-id--skool_post/iterations")
            assert response.status_code == 400

    def test_invalid_id(self):
        """Invalid action ID should return 400."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.get("/api/action/invalid/iterations")
            assert response.status_code == 400


# ===== Posting Queue V2 =====

class TestPostingQueueV2:
    """Tests for GET /api/posting-queue-v2."""

    def _setup(self, tmp_path):
        """Create transcripts for queue testing."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)

        transcript = {
            "id": "test-id",
            "title": "Test Transcript",
            "decimal": "50.01.01",
            "transcript": "This is a test.",
            "source": {"type": "audio"},
            "analysis": {
                "linkedin_v2": {
                    "post": "Draft text",
                    "_model": "gemini-2.0-flash",
                    "_analyzed_at": "2026-02-08T10:00:00",
                    "_round": 1,
                    "_history": {
                        "scores": [
                            {"round": 0, "overall": 3.5, "criteria": {"hook_strength": 3}},
                            {"round": 1, "overall": 4.2, "criteria": {"hook_strength": 4}},
                        ]
                    },
                },
                "linkedin_v2_0": {"post": "Draft 0"},
                "linkedin_v2_1": {"post": "Draft 1"},
                "linkedin_judge_0": {"overall_score": 3.5, "scores": {"hook_strength": 3}},
                "linkedin_judge_1": {"overall_score": 4.2, "scores": {"hook_strength": 4}},
            },
        }
        (decimal_dir / "test-id.json").write_text(json.dumps(transcript))

        # T028: posting-queue-v2 only shows staged/ready items
        state = {"actions": {"test-id--linkedin_v2": {"status": "staged", "copied_count": 0, "created_at": "2026-02-08T09:00:00"}}}
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))
        return state_file

    def test_returns_entities_not_iterations(self, tmp_path):
        """Queue should return one entity per transcript/analysis, not per iteration."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/posting-queue-v2")
                assert response.status_code == 200

                data = response.get_json()
                # Should have exactly 1 entity (linkedin_v2 alias only)
                assert data["total"] == 1
                assert data["items"][0]["id"] == "test-id--linkedin_v2"

    def test_includes_iteration_count(self, tmp_path):
        """Each entity should have iteration_count."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/posting-queue-v2")
                data = response.get_json()
                item = data["items"][0]
                assert item["iteration_count"] == 2  # rounds 0 and 1

    def test_includes_latest_score(self, tmp_path):
        """Each entity should have latest_score from score_history."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/posting-queue-v2")
                data = response.get_json()
                item = data["items"][0]
                assert item["latest_score"] == 4.2

    def test_excludes_new_items(self, tmp_path):
        """New items should not appear in the Review queue (only staged/ready)."""
        state_file = self._setup(tmp_path)
        state = json.loads(state_file.read_text())
        state["actions"]["test-id--linkedin_v2"] = {"status": "new"}
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/posting-queue-v2")
                data = response.get_json()
                assert data["total"] == 0

    def test_excludes_done_items(self, tmp_path):
        """Done items should not appear in the Review queue."""
        state_file = self._setup(tmp_path)
        state = json.loads(state_file.read_text())
        state["actions"]["test-id--linkedin_v2"] = {"status": "done"}
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/posting-queue-v2")
                data = response.get_json()
                assert data["total"] == 0


# ===== Approve Handler Rewire =====

class TestApproveRewire:
    """Tests that approve no longer triggers visual pipeline for auto-judge types."""

    def test_approve_linkedin_v2_no_visual(self, tmp_path):
        """Approving linkedin_v2 should NOT trigger visual pipeline."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)
        transcript = {
            "id": "test-id",
            "title": "Test",
            "decimal": "50.01.01",
            "transcript": "test",
            "source": {"type": "audio"},
            "analysis": {
                "linkedin_v2": {
                    "post": "Test post",
                    "_model": "gemini",
                    "_analyzed_at": "2026-02-07T10:00:00",
                },
            },
        }
        (decimal_dir / "test-id.json").write_text(json.dumps(transcript))

        state = {"actions": {}}
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.threading.Thread") as mock_thread_cls, \
             patch("kb.serve.pyperclip.copy"):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/approve")
                assert response.status_code == 200

                # No visual pipeline thread for auto-judge types
                mock_thread_cls.assert_not_called()
