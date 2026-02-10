"""
Tests for T023 Phase 4: Slide Editing + Template Selection.

Tests:
- GET /api/templates returns available templates
- GET /api/action/<id>/slides returns carousel slide data
- POST /api/action/<id>/save-slides saves edited slide data
- POST /api/action/<id>/render re-renders with specified template
- Save-edit on ready items invalidates visuals (Phase 3 code review fix)
- kb publish --template flag support
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from copy import deepcopy

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _make_transcript(tmp_path, transcript_id="test-id", round_num=1, with_slides=True):
    """Create transcript JSON with versioned analysis data and optional carousel_slides."""
    decimal_dir = tmp_path / "50.01.01"
    decimal_dir.mkdir(parents=True, exist_ok=True)

    analysis = {
        "linkedin_v2": {
            "post": "Latest draft text",
            "_model": "gemini-2.0-flash",
            "_analyzed_at": "2026-02-08T10:00:00",
            "_round": round_num,
            "_edit": 0,
            "_history": {
                "scores": [
                    {"round": 0, "overall": 3.5, "criteria": {"hook_strength": 3}},
                ]
            },
        },
    }

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

    if with_slides:
        analysis["carousel_slides"] = {
            "output": {
                "slides": [
                    {"slide_number": 1, "type": "hook", "title": "Hook Title", "content": "Hook content here", "words": 5},
                    {"slide_number": 2, "type": "content", "title": "Content Title", "content": "- Bullet one\n- Bullet two", "words": 10},
                    {"slide_number": 3, "type": "mermaid", "title": "Diagram", "content": "graph LR\n  A-->B", "words": 0},
                    {"slide_number": 4, "type": "cta", "title": "Follow me", "content": "Connect with me for more", "words": 8},
                ],
                "total_slides": 4,
                "has_mermaid": True,
            },
            "_model": "gemini-2.0-flash",
            "_analyzed_at": "2026-02-08T11:00:00",
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


def _make_state(tmp_path, action_id="test-id--linkedin_v2", status="staged", **extra):
    """Create action state file."""
    state = {"actions": {}}
    if status is not None:
        state["actions"][action_id] = {
            "status": status,
            "copied_count": 0,
            "created_at": "2026-02-08T09:00:00",
            "staged_round": 1,
            "edit_count": 0,
            **extra,
        }
    state_file = tmp_path / "action-state.json"
    state_file.write_text(json.dumps(state))
    return state_file


# ===== GET /api/templates =====

class TestGetTemplates:
    """Tests for GET /api/templates endpoint."""

    def test_returns_templates(self):
        """Should return list of available templates."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.get("/api/templates")
            assert response.status_code == 200

            data = response.get_json()
            assert "templates" in data
            assert "default" in data
            assert len(data["templates"]) > 0

            # Check template structure
            tpl = data["templates"][0]
            assert "name" in tpl
            assert "description" in tpl
            assert "is_default" in tpl

    def test_default_template_marked(self):
        """One template should be marked as default."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.get("/api/templates")
            data = response.get_json()

            defaults = [t for t in data["templates"] if t["is_default"]]
            assert len(defaults) == 1
            assert defaults[0]["name"] == data["default"]

    def test_known_templates_present(self):
        """brand-purple, modern-editorial, tech-minimal should be present."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.get("/api/templates")
            data = response.get_json()

            names = {t["name"] for t in data["templates"]}
            assert "brand-purple" in names
            assert "modern-editorial" in names
            assert "tech-minimal" in names


# ===== GET /api/action/<id>/slides =====

class TestGetSlides:
    """Tests for GET /api/action/<id>/slides endpoint."""

    def test_returns_slides(self, tmp_path):
        """Should return carousel slide data."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-id--linkedin_v2/slides")
                assert response.status_code == 200

                data = response.get_json()
                assert data["total_slides"] == 4
                assert len(data["slides"]) == 4
                assert data["has_mermaid"] is True

                # Check slide structure
                hook = data["slides"][0]
                assert hook["type"] == "hook"
                assert hook["title"] == "Hook Title"

    def test_returns_404_without_slides(self, tmp_path):
        """Should return 404 if no carousel_slides data."""
        _make_transcript(tmp_path, with_slides=False)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/test-id--linkedin_v2/slides")
                assert response.status_code == 404

    def test_invalid_action_id(self):
        """Invalid action ID should return 400."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.get("/api/action/invalid/slides")
            assert response.status_code == 400

    def test_missing_transcript(self, tmp_path):
        """Missing transcript should return 404."""
        state_file = _make_state(tmp_path, action_id="nonexistent--linkedin_v2")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/action/nonexistent--linkedin_v2/slides")
                assert response.status_code == 404


# ===== POST /api/action/<id>/save-slides =====

class TestSaveSlides:
    """Tests for POST /api/action/<id>/save-slides endpoint."""

    def test_save_slides_updates_content(self, tmp_path):
        """Saving slides should update title and content in transcript JSON."""
        transcript_path = _make_transcript(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 1, "title": "New Hook", "content": "Updated hook content"},
                        {"slide_number": 2, "title": "New Content", "content": "- Updated bullet"},
                    ]},
                    content_type="application/json",
                )
                assert response.status_code == 200
                data = response.get_json()
                assert data["success"] is True
                assert data["slides_count"] == 4  # all slides still present

        # Verify transcript updated
        transcript_data = json.loads(transcript_path.read_text())
        slides = transcript_data["analysis"]["carousel_slides"]["output"]["slides"]
        assert slides[0]["title"] == "New Hook"
        assert slides[0]["content"] == "Updated hook content"
        assert slides[1]["title"] == "New Content"
        # Slide 3 (mermaid) unchanged
        assert slides[2]["title"] == "Diagram"

    def test_save_slides_preserves_type(self, tmp_path):
        """Slide types should not be changed by save-slides."""
        transcript_path = _make_transcript(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                # Try to change type (should be ignored)
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 1, "type": "cta", "title": "Changed"},
                    ]},
                    content_type="application/json",
                )
                assert response.status_code == 200

        transcript_data = json.loads(transcript_path.read_text())
        slides = transcript_data["analysis"]["carousel_slides"]["output"]["slides"]
        # Type should still be "hook", not "cta"
        assert slides[0]["type"] == "hook"
        assert slides[0]["title"] == "Changed"

    def test_save_slides_invalidates_visuals(self, tmp_path):
        """Saving slides should set visual_status to stale."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path, status="ready", visual_status="ready")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 1, "title": "Edited"},
                    ]},
                    content_type="application/json",
                )
                assert response.status_code == 200

        # Check state
        state = json.loads(state_file.read_text())
        action = state["actions"]["test-id--linkedin_v2"]
        assert action["visual_status"] == "stale"
        assert action["status"] == "staged"  # reset from ready

    def test_save_slides_requires_staged(self, tmp_path):
        """Should reject if item is not staged or ready."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path, status="pending")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [{"slide_number": 1, "title": "test"}]},
                    content_type="application/json",
                )
                assert response.status_code == 400

    def test_save_slides_requires_slides_field(self, tmp_path):
        """Should reject if request body missing 'slides'."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"content": "wrong"},
                    content_type="application/json",
                )
                assert response.status_code == 400

    def test_save_slides_records_timestamp(self, tmp_path):
        """Should record _slides_edited_at timestamp."""
        transcript_path = _make_transcript(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [{"slide_number": 1, "title": "test"}]},
                    content_type="application/json",
                )

        transcript_data = json.loads(transcript_path.read_text())
        assert "_slides_edited_at" in transcript_data["analysis"]["carousel_slides"]


# ===== Phase 7: Save bullets, format, subtitle =====

def _make_transcript_with_bullets(tmp_path, transcript_id="test-id"):
    """Create transcript with Phase 6 bullet-format slide data."""
    decimal_dir = tmp_path / "50.01.01"
    decimal_dir.mkdir(parents=True, exist_ok=True)

    analysis = {
        "linkedin_v2": {
            "post": "Draft text",
            "_round": 1,
            "_edit": 0,
        },
        "carousel_slides": {
            "output": {
                "slides": [
                    {"slide_number": 1, "type": "hook", "title": "Hook", "content": "Headline", "subtitle": "Subheading", "words": 3},
                    {"slide_number": 2, "type": "content", "title": "Key Points", "bullets": ["Point A", "Point B", "Point C"], "format": "bullets", "content": "Point A. Point B. Point C", "words": 10},
                    {"slide_number": 3, "type": "content", "title": "Steps", "bullets": ["Step 1", "Step 2"], "format": "numbered", "content": "Step 1. Step 2", "words": 6},
                    {"slide_number": 4, "type": "content", "title": "Summary", "content": "A paragraph of text.", "format": "paragraph", "words": 5},
                    {"slide_number": 5, "type": "mermaid", "title": "Diagram", "content": "graph LR\n  A-->B", "words": 0},
                    {"slide_number": 6, "type": "cta", "title": "Follow Me", "content": "What do you think?", "subtitle": "Drop a comment", "words": 5},
                ],
                "total_slides": 6,
                "has_mermaid": True,
            },
        },
    }

    transcript = {
        "id": transcript_id,
        "title": "Test Transcript",
        "decimal": "50.01.01",
        "transcript": "Test.",
        "source": {"type": "audio"},
        "analysis": analysis,
    }
    path = decimal_dir / f"{transcript_id}.json"
    path.write_text(json.dumps(transcript))
    return path


class TestSaveSlidesPhase7:
    """Tests for Phase 7 save-slides: bullets, format, subtitle handling."""

    def test_save_bullets(self, tmp_path):
        """Saving bullets array should persist both bullets and content fallback."""
        transcript_path = _make_transcript_with_bullets(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 2, "title": "Key Points", "bullets": ["New A", "New B"], "format": "bullets", "content": "New A. New B"},
                    ]},
                    content_type="application/json",
                )
                assert response.status_code == 200

        data = json.loads(transcript_path.read_text())
        slide = data["analysis"]["carousel_slides"]["output"]["slides"][1]
        assert slide["bullets"] == ["New A", "New B"]
        assert slide["content"] == "New A. New B"
        assert slide["format"] == "bullets"

    def test_save_paragraph_clears_bullets(self, tmp_path):
        """Saving paragraph format should clear bullets field."""
        transcript_path = _make_transcript_with_bullets(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 2, "content": "Now a paragraph.", "format": "paragraph", "bullets": None},
                    ]},
                    content_type="application/json",
                )
                assert response.status_code == 200

        data = json.loads(transcript_path.read_text())
        slide = data["analysis"]["carousel_slides"]["output"]["slides"][1]
        assert slide["content"] == "Now a paragraph."
        assert slide["format"] == "paragraph"
        assert "bullets" not in slide

    def test_save_subtitle(self, tmp_path):
        """Saving subtitle on hook/CTA should persist."""
        transcript_path = _make_transcript_with_bullets(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 1, "title": "Hook", "content": "New headline", "subtitle": "New subheading"},
                        {"slide_number": 6, "title": "Follow Me", "content": "Updated CTA", "subtitle": "Updated sub"},
                    ]},
                    content_type="application/json",
                )
                assert response.status_code == 200

        data = json.loads(transcript_path.read_text())
        hook = data["analysis"]["carousel_slides"]["output"]["slides"][0]
        cta = data["analysis"]["carousel_slides"]["output"]["slides"][5]
        assert hook["subtitle"] == "New subheading"
        assert cta["subtitle"] == "Updated sub"

    def test_save_numbered_format(self, tmp_path):
        """Saving numbered format should persist format field."""
        transcript_path = _make_transcript_with_bullets(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 3, "bullets": ["Updated 1", "Updated 2", "Updated 3"], "format": "numbered", "content": "Updated 1. Updated 2. Updated 3"},
                    ]},
                    content_type="application/json",
                )
                assert response.status_code == 200

        data = json.loads(transcript_path.read_text())
        slide = data["analysis"]["carousel_slides"]["output"]["slides"][2]
        assert slide["format"] == "numbered"
        assert slide["bullets"] == ["Updated 1", "Updated 2", "Updated 3"]

    def test_invalid_format_returns_400(self, tmp_path):
        """Invalid format value should return 400."""
        _make_transcript_with_bullets(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 2, "format": "invalid_format"},
                    ]},
                    content_type="application/json",
                )
                assert response.status_code == 400
                assert "Invalid format" in response.get_json()["error"]

    def test_invalid_bullets_returns_400(self, tmp_path):
        """Non-list bullets should return 400."""
        _make_transcript_with_bullets(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 2, "bullets": "not a list"},
                    ]},
                    content_type="application/json",
                )
                assert response.status_code == 400
                assert "bullets" in response.get_json()["error"]

    def test_invalid_subtitle_returns_400(self, tmp_path):
        """Non-string subtitle should return 400."""
        _make_transcript_with_bullets(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 1, "subtitle": 123},
                    ]},
                    content_type="application/json",
                )
                assert response.status_code == 400
                assert "subtitle" in response.get_json()["error"]

    def test_save_and_refetch_bullets(self, tmp_path):
        """Saved bullets should be returned on next GET."""
        _make_transcript_with_bullets(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 2, "bullets": ["Saved A", "Saved B"], "format": "bullets", "content": "Saved A. Saved B"},
                    ]},
                    content_type="application/json",
                )

                response = client.get("/api/action/test-id--linkedin_v2/slides")
                assert response.status_code == 200
                data = response.get_json()
                slide = data["slides"][1]
                assert slide["bullets"] == ["Saved A", "Saved B"]
                assert slide["format"] == "bullets"


# ===== POST /api/action/<id>/render =====

class TestRenderEndpoint:
    """Tests for POST /api/action/<id>/render endpoint."""

    def test_render_starts_thread(self, tmp_path):
        """Render should start a background thread."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.threading.Thread") as mock_thread_cls:

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/render",
                    json={"template": "brand-purple"},
                    content_type="application/json",
                )
                assert response.status_code == 200
                data = response.get_json()
                assert data["success"] is True
                assert data["template"] == "brand-purple"

                mock_thread_cls.assert_called_once()
                mock_thread.start.assert_called_once()

    def test_render_uses_default_template(self, tmp_path):
        """Without template specified, should use default."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.threading.Thread") as mock_thread_cls:

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/render",
                    json={},
                    content_type="application/json",
                )
                assert response.status_code == 200
                data = response.get_json()
                assert data["template"] == "default"

    def test_render_requires_staged_or_ready(self, tmp_path):
        """Should reject if item is not staged or ready."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path, status="pending")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/render",
                    json={"template": "brand-purple"},
                    content_type="application/json",
                )
                assert response.status_code == 400

    def test_render_blocks_when_generating(self, tmp_path):
        """Should reject if already generating."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path, visual_status="generating")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/render",
                    json={"template": "brand-purple"},
                    content_type="application/json",
                )
                assert response.status_code == 400

    def test_render_works_for_ready_status(self, tmp_path):
        """Render should work for ready items (re-rendering)."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path, status="ready", visual_status="ready")

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.threading.Thread") as mock_thread_cls:

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/render",
                    json={"template": "modern-editorial"},
                    content_type="application/json",
                )
                assert response.status_code == 200
                data = response.get_json()
                assert data["template"] == "modern-editorial"


# ===== Save-edit invalidates visuals (Phase 3 code review fix) =====

class TestSaveEditInvalidatesVisuals:
    """Tests that save-edit on ready items resets visual status."""

    def _setup_ready(self, tmp_path):
        """Create transcript and state for a ready item with edit _N_0."""
        transcript_path = _make_transcript(tmp_path, round_num=1)
        transcript_data = json.loads(transcript_path.read_text())
        transcript_data["analysis"]["linkedin_v2_1_0"] = {
            "post": "Latest draft text",
            "_edited_at": "2026-02-08T10:00:00",
            "_source": "linkedin_v2_1",
        }
        transcript_path.write_text(json.dumps(transcript_data))

        state_file = _make_state(
            tmp_path, status="ready",
            staged_round=1, edit_count=0,
            visual_status="ready",
        )
        return transcript_path, state_file

    def test_save_edit_on_ready_resets_to_staged(self, tmp_path):
        """Editing a ready item should reset status to staged."""
        _, state_file = self._setup_ready(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-edit",
                    json={"text": "Re-edited text after visuals"},
                    content_type="application/json",
                )
                assert response.status_code == 200

        state = json.loads(state_file.read_text())
        action = state["actions"]["test-id--linkedin_v2"]
        assert action["status"] == "staged"
        assert action["visual_status"] == "stale"

    def test_save_edit_on_staged_does_not_change_status(self, tmp_path):
        """Editing a staged item should not change status."""
        transcript_path = _make_transcript(tmp_path, round_num=1)
        transcript_data = json.loads(transcript_path.read_text())
        transcript_data["analysis"]["linkedin_v2_1_0"] = {
            "post": "Latest draft text",
            "_edited_at": "2026-02-08T10:00:00",
            "_source": "linkedin_v2_1",
        }
        transcript_path.write_text(json.dumps(transcript_data))

        state_file = _make_state(
            tmp_path, status="staged",
            staged_round=1, edit_count=0,
        )

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/action/test-id--linkedin_v2/save-edit",
                    json={"text": "Edited text"},
                    content_type="application/json",
                )
                assert response.status_code == 200

        state = json.loads(state_file.read_text())
        action = state["actions"]["test-id--linkedin_v2"]
        assert action["status"] == "staged"  # unchanged


# ===== kb publish --template support =====

class TestPublishTemplateFlag:
    """Tests for kb publish template selection."""

    def test_render_one_passes_template(self, tmp_path):
        """render_one should pass template_name to render_pipeline."""
        from kb.publish import render_one

        renderable = {
            "title": "Test",
            "visuals_dir": str(tmp_path / "visuals"),
            "slides_data": {
                "slides": [{"slide_number": 1, "type": "hook", "content": "test"}],
                "total_slides": 1,
                "has_mermaid": False,
            },
        }

        with patch("kb.render.render_pipeline") as mock_render:
            mock_render.return_value = {
                "pdf_path": "/tmp/test.pdf",
                "thumbnail_paths": [],
                "errors": [],
            }

            result = render_one(renderable, template_name="tech-minimal")
            assert result["status"] == "success"

            # Verify template was passed
            mock_render.assert_called_once()
            call_kwargs = mock_render.call_args
            assert call_kwargs[1]["template_name"] == "tech-minimal"

    def test_render_one_dry_run(self, tmp_path):
        """Dry run should not call render_pipeline."""
        from kb.publish import render_one

        renderable = {
            "title": "Test",
            "visuals_dir": str(tmp_path / "visuals"),
            "slides_data": {
                "slides": [{"slide_number": 1}],
                "total_slides": 1,
                "has_mermaid": False,
            },
        }

        result = render_one(renderable, dry_run=True, template_name="brand-purple")
        assert result["status"] == "dry_run"


# ===== Slides persist across page refreshes =====

class TestSlidesPersistence:
    """Test that slide edits persist (verified via save + re-fetch)."""

    def test_save_and_refetch_slides(self, tmp_path):
        """Saved slide edits should be returned on next GET."""
        _make_transcript(tmp_path)
        state_file = _make_state(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                # Save edits
                client.post(
                    "/api/action/test-id--linkedin_v2/save-slides",
                    json={"slides": [
                        {"slide_number": 1, "title": "Persisted Title", "content": "Persisted content"},
                    ]},
                    content_type="application/json",
                )

                # Re-fetch
                response = client.get("/api/action/test-id--linkedin_v2/slides")
                assert response.status_code == 200
                data = response.get_json()

                hook_slide = data["slides"][0]
                assert hook_slide["title"] == "Persisted Title"
                assert hook_slide["content"] == "Persisted content"
