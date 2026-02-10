"""
Tests for T028: Content Lifecycle — Queue/Review State Machine.

Tests:
- Migration function (idempotent, all old statuses, preserves posted_at)
- Queue -> staged flow for linkedin_v2 ([a] -> status=staged, appears in Review)
- Queue -> done flow for skool_post ([a] -> status=done, copied, never in Review)
- [d] blocked for complex types (400 response)
- Iterate rejected for non-staged items (400 response)
- Staged -> iterate -> ready -> publish -> done flow
- Skip from both views (Queue and Review)
- No old status literals remain in serve.py (grep assertion)
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _make_transcript(tmp_path, transcript_id="test-id", analysis_type="linkedin_v2",
                     round_num=0, with_versioned=False):
    """Create transcript JSON with analysis data."""
    decimal_dir = tmp_path / "50.01.01"
    decimal_dir.mkdir(parents=True, exist_ok=True)

    analysis = {
        analysis_type: {
            "post": "Test post content",
            "_model": "gemini-2.0-flash",
            "_analyzed_at": "2026-02-10T10:00:00",
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
            analysis[f"{analysis_type}_{r}"] = {
                "post": f"Draft {r} text",
                "_model": "gemini-2.0-flash",
                "_analyzed_at": f"2026-02-10T{10+r}:00:00",
            }

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


def _make_state(tmp_path, action_id=None, status=None, **extra):
    """Create action state file. If action_id and status given, pre-populate."""
    state = {"actions": {}}
    if action_id and status:
        state["actions"][action_id] = {
            "status": status,
            "copied_count": 0,
            "created_at": "2026-02-10T09:00:00",
            **extra,
        }
    state_file = tmp_path / "action-state.json"
    state_file.write_text(json.dumps(state))
    return state_file


def _load_state(state_file):
    """Load and return action state dict."""
    return json.loads(state_file.read_text())


# ===== 4.1: Migration Tests =====

class TestMigration:
    """Tests for migrate_to_t028_statuses()."""

    def test_pending_migrates_to_new(self, tmp_path):
        state_file = _make_state(tmp_path, "a--linkedin_v2", "pending")
        from kb.serve_state import migrate_to_t028_statuses
        count = migrate_to_t028_statuses(path=state_file)
        assert count == 1
        state = _load_state(state_file)
        assert state["actions"]["a--linkedin_v2"]["status"] == "new"

    def test_approved_migrates_to_staged(self, tmp_path):
        state_file = _make_state(tmp_path, "a--linkedin_v2", "approved",
                                 approved_at="2026-02-09T10:00:00")
        from kb.serve_state import migrate_to_t028_statuses
        count = migrate_to_t028_statuses(path=state_file)
        assert count == 1
        state = _load_state(state_file)
        assert state["actions"]["a--linkedin_v2"]["status"] == "staged"
        assert state["actions"]["a--linkedin_v2"]["staged_at"] == "2026-02-09T10:00:00"

    def test_draft_migrates_to_new(self, tmp_path):
        state_file = _make_state(tmp_path, "a--linkedin_v2", "draft")
        from kb.serve_state import migrate_to_t028_statuses
        count = migrate_to_t028_statuses(path=state_file)
        assert count == 1
        state = _load_state(state_file)
        assert state["actions"]["a--linkedin_v2"]["status"] == "new"

    def test_posted_migrates_to_done_preserves_posted_at(self, tmp_path):
        state_file = _make_state(tmp_path, "a--linkedin_v2", "posted",
                                 posted_at="2026-02-08T15:00:00")
        from kb.serve_state import migrate_to_t028_statuses
        count = migrate_to_t028_statuses(path=state_file)
        assert count == 1
        state = _load_state(state_file)
        assert state["actions"]["a--linkedin_v2"]["status"] == "done"
        assert state["actions"]["a--linkedin_v2"]["posted_at"] == "2026-02-08T15:00:00"

    def test_skipped_migrates_to_skip(self, tmp_path):
        state_file = _make_state(tmp_path, "a--linkedin_v2", "skipped")
        from kb.serve_state import migrate_to_t028_statuses
        count = migrate_to_t028_statuses(path=state_file)
        assert count == 1
        state = _load_state(state_file)
        assert state["actions"]["a--linkedin_v2"]["status"] == "skip"

    def test_idempotent(self, tmp_path):
        """Running migration twice produces same result."""
        state_file = _make_state(tmp_path, "a--linkedin_v2", "pending")
        from kb.serve_state import migrate_to_t028_statuses
        count1 = migrate_to_t028_statuses(path=state_file)
        assert count1 == 1
        count2 = migrate_to_t028_statuses(path=state_file)
        assert count2 == 0
        state = _load_state(state_file)
        assert state["actions"]["a--linkedin_v2"]["status"] == "new"

    def test_handles_all_old_statuses(self, tmp_path):
        """Migrates multiple items with different old statuses at once."""
        state = {"actions": {
            "a--linkedin_v2": {"status": "pending", "copied_count": 0},
            "b--linkedin_v2": {"status": "approved", "copied_count": 0, "approved_at": "2026-02-09T10:00:00"},
            "c--skool_post": {"status": "draft", "copied_count": 0},
            "d--linkedin_v2": {"status": "posted", "copied_count": 0, "posted_at": "2026-02-08T12:00:00"},
            "e--skool_post": {"status": "skipped", "copied_count": 0},
            "f--linkedin_v2": {"status": "new", "copied_count": 0},  # already migrated
        }}
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))

        from kb.serve_state import migrate_to_t028_statuses
        count = migrate_to_t028_statuses(path=state_file)
        assert count == 5  # f is already "new", not migrated

        result = _load_state(state_file)
        assert result["actions"]["a--linkedin_v2"]["status"] == "new"
        assert result["actions"]["b--linkedin_v2"]["status"] == "staged"
        assert result["actions"]["c--skool_post"]["status"] == "new"
        assert result["actions"]["d--linkedin_v2"]["status"] == "done"
        assert result["actions"]["e--skool_post"]["status"] == "skip"
        assert result["actions"]["f--linkedin_v2"]["status"] == "new"

    def test_empty_state(self, tmp_path):
        """No items to migrate returns 0."""
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps({"actions": {}}))
        from kb.serve_state import migrate_to_t028_statuses
        count = migrate_to_t028_statuses(path=state_file)
        assert count == 0


# ===== 4.2: Queue -> Staged for linkedin_v2 =====

class TestApproveComplexType:
    """[a] on linkedin_v2 -> status=staged, appears in Review."""

    def _setup(self, tmp_path):
        transcript_path = _make_transcript(tmp_path, "test-id", "linkedin_v2")
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "new")
        return transcript_path, state_file

    def test_approve_linkedin_v2_sets_staged(self, tmp_path):
        transcript_path, state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/approve")
                assert response.status_code == 200
                data = response.get_json()
                assert data["action"] == "staged"

        state = _load_state(state_file)
        assert state["actions"]["test-id--linkedin_v2"]["status"] == "staged"
        assert "staged_at" in state["actions"]["test-id--linkedin_v2"]

    def test_approve_linkedin_v2_not_in_queue(self, tmp_path):
        """After approve, item should NOT appear in queue (new items only)."""
        transcript_path, state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                # Approve first
                client.post("/api/action/test-id--linkedin_v2/approve")

                # Check queue
                response = client.get("/api/queue")
                data = response.get_json()
                ids = [item["id"] for item in data["pending"]]
                assert "test-id--linkedin_v2" not in ids

    def test_approve_rejects_non_new(self, tmp_path):
        """Cannot approve item that is already staged."""
        _make_transcript(tmp_path, "test-id", "linkedin_v2")
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "staged")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/approve")
                assert response.status_code == 400


# ===== 4.3: Queue -> Done for skool_post =====

class TestApproveSimpleType:
    """[a] on skool_post -> status=done, copied, never in Review."""

    def _setup(self, tmp_path):
        transcript_path = _make_transcript(tmp_path, "test-id", "skool_post")
        state_file = _make_state(tmp_path, "test-id--skool_post", "new")
        return transcript_path, state_file

    def test_approve_skool_post_sets_done(self, tmp_path):
        transcript_path, state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy") as mock_copy:
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--skool_post/approve")
                assert response.status_code == 200
                data = response.get_json()
                assert data["action"] == "done"
                assert data["copied"] is True
                mock_copy.assert_called_once()

        state = _load_state(state_file)
        assert state["actions"]["test-id--skool_post"]["status"] == "done"
        assert "completed_at" in state["actions"]["test-id--skool_post"]

    def test_simple_type_never_in_review(self, tmp_path):
        """After approve, skool_post should not appear in Review (posting-queue-v2)."""
        transcript_path, state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.pyperclip.copy"):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                # Approve (done)
                client.post("/api/action/test-id--skool_post/approve")

                # Check Review
                response = client.get("/api/posting-queue-v2")
                data = response.get_json()
                ids = [item["id"] for item in data["items"]]
                assert "test-id--skool_post" not in ids


# ===== 4.4: [d] Blocked for Complex Types =====

class TestDoneBlockedForComplexTypes:
    """[d] on linkedin_v2 in Queue returns 400."""

    def test_done_blocked_for_linkedin_v2(self, tmp_path):
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/done")
                assert response.status_code == 400
                data = response.get_json()
                assert "Use [a] to stage or [s] to skip" in data["error"]

        # Status should remain unchanged
        state = _load_state(state_file)
        assert state["actions"]["test-id--linkedin_v2"]["status"] == "new"

    def test_done_allowed_for_simple_types(self, tmp_path):
        state_file = _make_state(tmp_path, "test-id--skool_post", "new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--skool_post/done")
                assert response.status_code == 200

        state = _load_state(state_file)
        assert state["actions"]["test-id--skool_post"]["status"] == "done"


# ===== 4.5: Iterate Rejected for Non-Staged =====

class TestIterateRequiresStaged:
    """[i] iterate rejects non-staged items with 400."""

    def test_iterate_rejects_new(self, tmp_path):
        _make_transcript(tmp_path, "test-id", "linkedin_v2")
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/iterate")
                assert response.status_code == 400
                data = response.get_json()
                assert "must be staged" in data["error"]

    def test_iterate_rejects_done(self, tmp_path):
        _make_transcript(tmp_path, "test-id", "linkedin_v2")
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "done")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/iterate")
                assert response.status_code == 400

    def test_iterate_rejects_skip(self, tmp_path):
        _make_transcript(tmp_path, "test-id", "linkedin_v2")
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "skip")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/iterate")
                assert response.status_code == 400


# ===== 4.6: Staged -> Iterate -> Ready -> Publish -> Done =====

class TestPublishFlow:
    """Publish from Review sets status=done with posted_at."""

    def test_publish_staged_item(self, tmp_path):
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "staged")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/posted")
                assert response.status_code == 200

        state = _load_state(state_file)
        assert state["actions"]["test-id--linkedin_v2"]["status"] == "done"
        assert "posted_at" in state["actions"]["test-id--linkedin_v2"]
        assert "completed_at" in state["actions"]["test-id--linkedin_v2"]

    def test_publish_ready_item(self, tmp_path):
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "ready")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/posted")
                assert response.status_code == 200

        state = _load_state(state_file)
        assert state["actions"]["test-id--linkedin_v2"]["status"] == "done"

    def test_publish_rejects_new(self, tmp_path):
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/posted")
                assert response.status_code == 400

    def test_published_item_not_in_review(self, tmp_path):
        """After publishing, item should not appear in Review."""
        _make_transcript(tmp_path, "test-id", "linkedin_v2")
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "staged")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                # Publish
                client.post("/api/action/test-id--linkedin_v2/posted")

                # Check Review
                response = client.get("/api/posting-queue-v2")
                data = response.get_json()
                ids = [item["id"] for item in data["items"]]
                assert "test-id--linkedin_v2" not in ids


# ===== 4.7: Skip from Both Views =====

class TestSkipFromBothViews:
    """Skip works from Queue (new items) and Review (staged items)."""

    def test_skip_new_item(self, tmp_path):
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/skip")
                assert response.status_code == 200

        state = _load_state(state_file)
        assert state["actions"]["test-id--linkedin_v2"]["status"] == "skip"

    def test_skip_staged_item(self, tmp_path):
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "staged")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/skip")
                assert response.status_code == 200

        state = _load_state(state_file)
        assert state["actions"]["test-id--linkedin_v2"]["status"] == "skip"

    def test_skipped_item_not_in_queue(self, tmp_path):
        """Skipped items should not appear in Queue."""
        _make_transcript(tmp_path, "test-id", "linkedin_v2")
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "skip")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/queue")
                data = response.get_json()
                ids = [item["id"] for item in data["pending"]]
                assert "test-id--linkedin_v2" not in ids

    def test_skipped_item_not_in_review(self, tmp_path):
        """Skipped items should not appear in Review."""
        _make_transcript(tmp_path, "test-id", "linkedin_v2")
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "skip")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/posting-queue-v2")
                data = response.get_json()
                ids = [item["id"] for item in data["items"]]
                assert "test-id--linkedin_v2" not in ids


# ===== 4.8: No Old Status Literals in serve.py =====

class TestNoOldStatusLiterals:
    """Verify old status strings are not used in serve.py (except comments/legacy)."""

    def test_no_old_statuses_in_serve(self):
        """grep assertion: no pending/approved/draft/skipped/posted status assignments."""
        serve_path = Path(__file__).parent.parent / "serve.py"
        content = serve_path.read_text()

        lines = content.split("\n")
        violations = []

        # Old status values that should not appear as string literals
        old_statuses = ['"pending"', '"approved"', '"draft"', '"skipped"', '"posted"']

        # Track docstring blocks (triple-quoted)
        in_docstring = False

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Track docstring open/close
            if '"""' in stripped:
                count_triple = stripped.count('"""')
                if count_triple == 1:
                    in_docstring = not in_docstring
                # count_triple >= 2 means open+close on same line, no state change
                continue

            if in_docstring:
                continue

            # Skip comments
            if stripped.startswith("#"):
                continue
            # Skip the legacy migration function
            if "migrate_approved_to_draft" in line:
                continue
            # Skip noqa lines
            if "noqa" in line:
                continue
            # Skip the API JSON key "pending" in get_queue response
            if '"pending":' in line and "new_items" in line:
                continue

            for old_status in old_statuses:
                if old_status in line:
                    violations.append(f"Line {i}: {line.strip()}")

        assert violations == [], (
            f"Old status literals found in serve.py:\n" +
            "\n".join(violations)
        )


# ===== Cross-Cutting: No Item in Both Views =====

class TestNoItemInBothViews:
    """No item should appear in both Queue and Review simultaneously."""

    def test_new_item_only_in_queue(self, tmp_path):
        _make_transcript(tmp_path, "test-id", "linkedin_v2")
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "new")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                queue_resp = client.get("/api/queue")
                review_resp = client.get("/api/posting-queue-v2")

                queue_ids = {item["id"] for item in queue_resp.get_json()["pending"]}
                review_ids = {item["id"] for item in review_resp.get_json()["items"]}

                overlap = queue_ids & review_ids
                assert overlap == set(), f"Items in both views: {overlap}"

                # The new item should be in queue
                assert "test-id--linkedin_v2" in queue_ids
                assert "test-id--linkedin_v2" not in review_ids

    def test_staged_item_only_in_review(self, tmp_path):
        _make_transcript(tmp_path, "test-id", "linkedin_v2")
        state_file = _make_state(tmp_path, "test-id--linkedin_v2", "staged")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                queue_resp = client.get("/api/queue")
                review_resp = client.get("/api/posting-queue-v2")

                queue_ids = {item["id"] for item in queue_resp.get_json()["pending"]}
                review_ids = {item["id"] for item in review_resp.get_json()["items"]}

                overlap = queue_ids & review_ids
                assert overlap == set(), f"Items in both views: {overlap}"

                assert "test-id--linkedin_v2" not in queue_ids
                assert "test-id--linkedin_v2" in review_ids
