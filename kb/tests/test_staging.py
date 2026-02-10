"""
Tests for T023 Phase 3: Staging Area + Text Editing.

Tests:
- Stage endpoint creates initial edit version (_N_0)
- Save-edit endpoint creates new edit versions
- Generate-visuals endpoint triggers background thread
- Edit-history endpoint returns edit versions
- State transitions in staging flow
- Published/posted gated on ready status
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from copy import deepcopy

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _make_transcript(tmp_path, transcript_id="test-id", round_num=1, with_versioned=True):
    """Create transcript JSON with versioned analysis data."""
    decimal_dir = tmp_path / "50.01.01"
    decimal_dir.mkdir(parents=True, exist_ok=True)

    analysis = {
        "linkedin_v2": {
            "post": "Latest draft text",
            "_model": "gemini-2.0-flash",
            "_analyzed_at": "2026-02-08T10:00:00",
            "_round": round_num,
            "_history": {
                "scores": [
                    {"round": 0, "overall": 3.5, "criteria": {"hook_strength": 3}},
                ]
            },
        },
    }

    if with_versioned:
        for r in range(round_num + 1):
            analysis[f"linkedin_v2_{r}"] = {
                "post": f"Draft {r} text",
                "_model": "gemini-2.0-flash",
                "_analyzed_at": f"2026-02-08T{10+r}:00:00",
            }
            analysis[f"linkedin_judge_{r}"] = {
                "overall_score": 3.5 + r * 0.5,
                "scores": {"hook_strength": 3 + r},
                "improvements": [],
            }
        analysis["linkedin_v2"]["_history"]["scores"] = [
            {"round": r, "overall": 3.5 + r * 0.5, "criteria": {"hook_strength": 3 + r}}
            for r in range(round_num + 1)
        ]

    transcript = {
        "id": transcript_id,
        "title": "Test Transcript",
        "decimal": "50.01.01",
        "transcript": "This is a test transcript.",
        "source": {"type": "audio"},
        "analysis": analysis,
    }
    transcript_path = decimal_dir / f"{transcript_id}.json"
    transcript_path.write_text(json.dumps(transcript))
    return transcript_path


def _make_state(tmp_path, action_id="test-id--linkedin_v2", status="new", **extra):
    """Create action state file."""
    state = {"actions": {}}
    if status is not None:
        state["actions"][action_id] = {
            "status": status,
            "copied_count": 0,
            "created_at": "2026-02-08T09:00:00",
            **extra,
        }
    state_file = tmp_path / "action-state.json"
    state_file.write_text(json.dumps(state))
    return state_file


# ===== Stage Endpoint: Edit Version Creation =====

class TestStageCreatesEditVersion:
    """Tests that staging creates the initial edit version (_N_0)."""

    def test_stage_creates_edit_version_n_0(self, tmp_path):
        """Staging should create linkedin_v2_N_0 in transcript JSON."""
        transcript_path = _make_transcript(tmp_path, round_num=1)
        state_file = _make_state(tmp_path, status="new")

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
                assert data["staged_round"] == 1

        # Check transcript JSON
        transcript_data = json.loads(transcript_path.read_text())
        assert "linkedin_v2_1_0" in transcript_data["analysis"]
        edit_v = transcript_data["analysis"]["linkedin_v2_1_0"]
        assert edit_v["post"] == "Latest draft text"
        assert "_edited_at" in edit_v
        assert edit_v["_source"] == "linkedin_v2_1"

        # Check alias has _edit=0
        alias = transcript_data["analysis"]["linkedin_v2"]
        assert alias["_edit"] == 0

    def test_stage_does_not_duplicate_edit_version(self, tmp_path):
        """If _N_0 already exists, staging should not overwrite it."""
        transcript_path = _make_transcript(tmp_path, round_num=0)

        # Pre-create the _0_0 edit version
        transcript_data = json.loads(transcript_path.read_text())
        transcript_data["analysis"]["linkedin_v2_0_0"] = {
            "post": "Pre-existing edit",
            "_edited_at": "2026-02-08T08:00:00",
            "_source": "linkedin_v2_0",
        }
        transcript_path.write_text(json.dumps(transcript_data))

        state_file = _make_state(tmp_path, status="new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/stage")
                assert response.status_code == 200

        # Check the pre-existing edit was not overwritten
        transcript_data = json.loads(transcript_path.read_text())
        assert transcript_data["analysis"]["linkedin_v2_0_0"]["post"] == "Pre-existing edit"

    def test_stage_records_staged_round_in_state(self, tmp_path):
        """Action state should record staged_round and edit_count."""
        _make_transcript(tmp_path, round_num=2)
        state_file = _make_state(tmp_path, status="new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                client.post("/api/action/test-id--linkedin_v2/stage")

        state = json.loads(state_file.read_text())
        action = state["actions"]["test-id--linkedin_v2"]
        assert action["staged_round"] == 2
        assert action["edit_count"] == 0


# ===== Save Edit Endpoint =====

class TestSaveEdit:
    """Tests for POST /api/action/<id>/save-edit."""

    def _setup_staged(self, tmp_path, round_num=1):
        """Create transcript and state for a staged item with edit _N_0."""
        transcript_path = _make_transcript(tmp_path, round_num=round_num)

        # Add initial edit version
        transcript_data = json.loads(transcript_path.read_text())
        transcript_data["analysis"][f"linkedin_v2_{round_num}_0"] = {
            "post": "Latest draft text",
            "_edited_at": "2026-02-08T10:00:00",
            "_source": f"linkedin_v2_{round_num}",
        }
        transcript_data["analysis"]["linkedin_v2"]["_edit"] = 0
        transcript_path.write_text(json.dumps(transcript_data))

        state_file = _make_state(
            tmp_path, status="staged",
            staged_round=round_num, edit_count=0,
        )
        return transcript_path, state_file

    def test_save_edit_creates_n_1(self, tmp_path):
        """First save should create linkedin_v2_N_1."""
        transcript_path, state_file = self._setup_staged(tmp_path, round_num=1)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-edit",
                    json={"text": "Edited post text v1"},
                    content_type="application/json",
                )
                assert response.status_code == 200

                data = response.get_json()
                assert data["success"] is True
                assert data["edit_key"] == "linkedin_v2_1_1"
                assert data["edit_number"] == 1

        # Check transcript JSON
        transcript_data = json.loads(transcript_path.read_text())
        assert "linkedin_v2_1_1" in transcript_data["analysis"]
        edit = transcript_data["analysis"]["linkedin_v2_1_1"]
        assert edit["post"] == "Edited post text v1"
        assert edit["_source"] == "linkedin_v2_1_0"

        # Alias updated
        alias = transcript_data["analysis"]["linkedin_v2"]
        assert alias["post"] == "Edited post text v1"
        assert alias["_edit"] == 1

    def test_save_edit_increments_correctly(self, tmp_path):
        """Second save should create _N_2."""
        transcript_path, state_file = self._setup_staged(tmp_path, round_num=1)

        # Simulate first edit already done
        transcript_data = json.loads(transcript_path.read_text())
        transcript_data["analysis"]["linkedin_v2_1_1"] = {
            "post": "First edit",
            "_edited_at": "2026-02-08T11:00:00",
            "_source": "linkedin_v2_1_0",
        }
        transcript_data["analysis"]["linkedin_v2"]["_edit"] = 1
        transcript_data["analysis"]["linkedin_v2"]["post"] = "First edit"
        transcript_path.write_text(json.dumps(transcript_data))

        # Update state
        state = json.loads(state_file.read_text())
        state["actions"]["test-id--linkedin_v2"]["edit_count"] = 1
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-edit",
                    json={"text": "Second edit text"},
                    content_type="application/json",
                )
                assert response.status_code == 200
                data = response.get_json()
                assert data["edit_key"] == "linkedin_v2_1_2"
                assert data["edit_number"] == 2

        transcript_data = json.loads(transcript_path.read_text())
        assert "linkedin_v2_1_2" in transcript_data["analysis"]
        assert transcript_data["analysis"]["linkedin_v2_1_2"]["_source"] == "linkedin_v2_1_1"
        assert transcript_data["analysis"]["linkedin_v2"]["_edit"] == 2

    def test_save_edit_requires_staged_status(self, tmp_path):
        """Save-edit should fail if item is not staged."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path, status="new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-edit",
                    json={"text": "some text"},
                    content_type="application/json",
                )
                assert response.status_code == 400

    def test_save_edit_allowed_for_ready_status(self, tmp_path):
        """Save-edit should work for ready items (re-editing after visuals)."""
        transcript_path, _ = self._setup_staged(tmp_path, round_num=1)
        state_file = _make_state(
            tmp_path, status="ready",
            staged_round=1, edit_count=0,
        )

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-edit",
                    json={"text": "Re-edited text"},
                    content_type="application/json",
                )
                assert response.status_code == 200

    def test_save_edit_requires_text_field(self, tmp_path):
        """Save-edit should fail without 'text' in body."""
        _, state_file = self._setup_staged(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-edit",
                    json={"content": "wrong field name"},
                    content_type="application/json",
                )
                assert response.status_code == 400

    def test_save_edit_invalid_id(self):
        """Invalid action ID should return 400."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.post(
                "/api/action/invalid/save-edit",
                json={"text": "test"},
                content_type="application/json",
            )
            assert response.status_code == 400


# ===== Generate Visuals Endpoint =====

class TestGenerateVisuals:
    """Tests for POST /api/action/<id>/generate-visuals."""

    def _setup_staged(self, tmp_path):
        """Create transcript and state for a staged item."""
        transcript_path = _make_transcript(tmp_path, round_num=1)
        state_file = _make_state(
            tmp_path, status="staged",
            staged_round=1, edit_count=0,
        )
        return transcript_path, state_file

    def test_generate_visuals_starts_thread(self, tmp_path):
        """Generate visuals should start a background thread."""
        _, state_file = self._setup_staged(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.threading.Thread") as mock_thread_cls:

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/generate-visuals")
                assert response.status_code == 200

                data = response.get_json()
                assert data["success"] is True
                assert "started" in data["message"].lower()

                mock_thread_cls.assert_called_once()
                mock_thread.start.assert_called_once()

    def test_generate_visuals_requires_staged(self, tmp_path):
        """Generate visuals should fail if item is not staged."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path, status="new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/generate-visuals")
                assert response.status_code == 400

    def test_generate_visuals_blocks_when_already_generating(self, tmp_path):
        """Should reject if visual_status is already 'generating'."""
        _make_transcript(tmp_path)
        state_file = _make_state(
            tmp_path, status="staged",
            visual_status="generating",
        )

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/generate-visuals")
                assert response.status_code == 400

    def test_generate_visuals_invalid_id(self):
        """Invalid action ID should return 400."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.post("/api/action/invalid/generate-visuals")
            assert response.status_code == 400

    def test_generate_visuals_missing_transcript(self, tmp_path):
        """Missing transcript file should return 404."""
        state_file = _make_state(
            tmp_path, status="staged",
            action_id="nonexistent--linkedin_v2",
        )

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/nonexistent--linkedin_v2/generate-visuals")
                assert response.status_code == 404


# ===== Edit History Endpoint =====

class TestEditHistory:
    """Tests for GET /api/action/<id>/edit-history."""

    def _setup_with_edits(self, tmp_path, num_edits=2):
        """Create transcript with edit versions."""
        transcript_path = _make_transcript(tmp_path, round_num=1)
        transcript_data = json.loads(transcript_path.read_text())

        # Add edit versions
        for i in range(num_edits + 1):  # +1 for _0 (original)
            transcript_data["analysis"][f"linkedin_v2_1_{i}"] = {
                "post": f"Edit {i} text",
                "_edited_at": f"2026-02-08T{10+i}:00:00",
                "_source": f"linkedin_v2_1_{i-1}" if i > 0 else "linkedin_v2_1",
            }
        transcript_data["analysis"]["linkedin_v2"]["_edit"] = num_edits
        transcript_path.write_text(json.dumps(transcript_data))

        state_file = _make_state(
            tmp_path, status="staged",
            staged_round=1, edit_count=num_edits,
        )
        return transcript_path, state_file

    def test_returns_edit_history(self, tmp_path):
        """Should return all edit versions for the staged round."""
        _, state_file = self._setup_with_edits(tmp_path, num_edits=2)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-id--linkedin_v2/edit-history")
                assert response.status_code == 200

                data = response.get_json()
                assert data["staged_round"] == 1
                assert data["current_edit"] == 2
                assert data["total_edits"] == 3  # _0, _1, _2
                assert len(data["edits"]) == 3

                # Check edit 0
                assert data["edits"][0]["edit_number"] == 0
                assert data["edits"][0]["post"] == "Edit 0 text"

                # Check edit 2
                assert data["edits"][2]["edit_number"] == 2
                assert data["edits"][2]["post"] == "Edit 2 text"

    def test_returns_empty_when_no_edits(self, tmp_path):
        """Should return empty edits list when no edit versions exist."""
        _make_transcript(tmp_path, round_num=1)
        state_file = _make_state(
            tmp_path, status="staged",
            staged_round=1, edit_count=0,
        )

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-id--linkedin_v2/edit-history")
                assert response.status_code == 200
                data = response.get_json()
                assert data["total_edits"] == 0

    def test_edit_history_invalid_id(self):
        """Invalid action ID should return 400."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.get("/api/action/invalid/edit-history")
            assert response.status_code == 400


# ===== State Transitions =====

class TestStateTransitions:
    """Tests for the full staging state machine."""

    def test_staging_flow_end_to_end(self, tmp_path):
        """Full flow: stage -> edit -> generate -> ready -> publish."""
        transcript_path = _make_transcript(tmp_path, round_num=1)
        state_file = _make_state(tmp_path, status="new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"), \
             patch("kb.serve.threading.Thread") as mock_thread_cls:

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                # 1. Stage
                response = client.post("/api/action/test-id--linkedin_v2/stage")
                assert response.status_code == 200

                state = json.loads(state_file.read_text())
                assert state["actions"]["test-id--linkedin_v2"]["status"] == "staged"

                # 2. Save edit
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-edit",
                    json={"text": "Edited text"},
                    content_type="application/json",
                )
                assert response.status_code == 200

                # 3. Generate visuals
                response = client.post("/api/action/test-id--linkedin_v2/generate-visuals")
                assert response.status_code == 200

                mock_thread.start.assert_called_once()

    def test_posted_requires_staged_or_ready(self, tmp_path):
        """Mark-posted should only work for staged or ready items."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path, status="new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                # New items cannot be posted directly
                response = client.post("/api/action/test-id--linkedin_v2/posted")
                assert response.status_code == 400

    def test_posted_works_for_ready(self, tmp_path):
        """Mark-posted should work for ready items, setting status to done."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path, status="ready")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/posted")
                assert response.status_code == 200

                state = json.loads(state_file.read_text())
                assert state["actions"]["test-id--linkedin_v2"]["status"] == "done"
                assert "posted_at" in state["actions"]["test-id--linkedin_v2"]


# ===== Posting Queue V2 with Staging =====

class TestPostingQueueV2Staging:
    """Tests for posting-queue-v2 with staged/ready items."""

    def test_includes_staged_items(self, tmp_path):
        """Staged items should appear in posting-queue-v2."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path, status="staged", staged_round=1)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/posting-queue-v2")
                data = response.get_json()
                assert data["total"] == 1
                assert data["items"][0]["status"] == "staged"

    def test_includes_ready_items(self, tmp_path):
        """Ready items should appear in posting-queue-v2."""
        _make_transcript(tmp_path)
        state_file = _make_state(
            tmp_path, status="ready",
            visual_status="ready",
            staged_round=1,
        )

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/posting-queue-v2")
                data = response.get_json()
                assert data["total"] == 1
                assert data["items"][0]["status"] == "ready"
                assert data["items"][0]["visual_status"] == "ready"

    def test_includes_visual_status_metadata(self, tmp_path):
        """Items should include visual_status and staging metadata."""
        _make_transcript(tmp_path)
        state_file = _make_state(
            tmp_path, status="staged",
            staged_round=2, edit_count=3,
            visual_status="generating",
        )

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/posting-queue-v2")
                data = response.get_json()
                item = data["items"][0]
                assert item["visual_status"] == "generating"
                assert item["staged_round"] == 2
                assert item["edit_count"] == 3
