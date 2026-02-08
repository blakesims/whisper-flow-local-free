"""
Tests for Phase 4: KB Serve Integration + Pipeline Wiring.

Tests:
- Visual status state machine (_update_visual_status)
- Background pipeline helpers (_find_transcript_file)
- /visuals/<path> route (directory traversal prevention, file serving)
- Posting queue API visual_status fields
- Approve endpoint triggers background thread
- Mermaid base64 conversion in render_pipeline
- linkedin_post removed from action_mapping
"""

import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ===== Visual Status State Machine =====

class TestVisualStatusUpdate:
    """Tests for _update_visual_status helper."""

    def test_sets_generating_status(self, tmp_path):
        """visual_status should be set to 'generating'."""
        state_file = tmp_path / "action-state.json"
        state = {
            "actions": {
                "test-id--linkedin_v2": {
                    "status": "approved",
                    "approved_at": "2026-02-07T10:00:00",
                }
            }
        }
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file):
            from kb.serve import _update_visual_status
            _update_visual_status("test-id--linkedin_v2", "generating")

            updated = json.loads(state_file.read_text())
            assert updated["actions"]["test-id--linkedin_v2"]["visual_status"] == "generating"

    def test_sets_ready_status_with_data(self, tmp_path):
        """visual_status 'ready' should include visual_data."""
        state_file = tmp_path / "action-state.json"
        state = {
            "actions": {
                "test-id--linkedin_v2": {
                    "status": "approved",
                    "visual_status": "generating",
                }
            }
        }
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file):
            from kb.serve import _update_visual_status
            _update_visual_status("test-id--linkedin_v2", "ready", {
                "format": "CAROUSEL",
                "pdf_path": "/tmp/carousel.pdf",
                "thumbnail_paths": ["/tmp/slide-1.png"],
            })

            updated = json.loads(state_file.read_text())
            action = updated["actions"]["test-id--linkedin_v2"]
            assert action["visual_status"] == "ready"
            assert action["visual_data"]["format"] == "CAROUSEL"
            assert action["visual_data"]["pdf_path"] == "/tmp/carousel.pdf"

    def test_sets_failed_status(self, tmp_path):
        """visual_status should be set to 'failed' with error info."""
        state_file = tmp_path / "action-state.json"
        state = {
            "actions": {
                "test-id--linkedin_v2": {
                    "status": "approved",
                    "visual_status": "generating",
                }
            }
        }
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file):
            from kb.serve import _update_visual_status
            _update_visual_status("test-id--linkedin_v2", "failed", {"error": "render crashed"})

            updated = json.loads(state_file.read_text())
            action = updated["actions"]["test-id--linkedin_v2"]
            assert action["visual_status"] == "failed"
            assert "render crashed" in action["visual_data"]["error"]

    def test_sets_text_only_status(self, tmp_path):
        """visual_status 'text_only' for TEXT_ONLY classified posts."""
        state_file = tmp_path / "action-state.json"
        state = {
            "actions": {
                "test-id--linkedin_v2": {
                    "status": "approved",
                    "visual_status": "generating",
                }
            }
        }
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file):
            from kb.serve import _update_visual_status
            _update_visual_status("test-id--linkedin_v2", "text_only", {"format": "TEXT_ONLY"})

            updated = json.loads(state_file.read_text())
            assert updated["actions"]["test-id--linkedin_v2"]["visual_status"] == "text_only"

    def test_noop_for_unknown_action(self, tmp_path):
        """Should not crash for unknown action_id."""
        state_file = tmp_path / "action-state.json"
        state = {"actions": {}}
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file):
            from kb.serve import _update_visual_status
            # Should not raise
            _update_visual_status("nonexistent--linkedin_v2", "generating")


# ===== Visuals Route =====

class TestVisualsRoute:
    """Tests for GET /visuals/<path:filepath> route."""

    @pytest.fixture
    def client(self, tmp_path):
        """Create a test client with tmp KB_ROOT."""
        with patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                yield client

    def test_serves_existing_file(self, client, tmp_path):
        """Should serve a file that exists in KB_ROOT."""
        # Create a test file
        visuals_dir = tmp_path / "50.01.01" / "visuals"
        visuals_dir.mkdir(parents=True)
        test_pdf = visuals_dir / "carousel.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 fake pdf data")

        with patch("kb.serve.KB_ROOT", tmp_path):
            response = client.get("/visuals/50.01.01/visuals/carousel.pdf")
            assert response.status_code == 200

    def test_404_for_missing_file(self, client, tmp_path):
        """Should return 404 for nonexistent file."""
        with patch("kb.serve.KB_ROOT", tmp_path):
            response = client.get("/visuals/50.01.01/visuals/nonexistent.pdf")
            assert response.status_code == 404

    def test_prevents_directory_traversal(self, client, tmp_path):
        """Should block path traversal attempts."""
        with patch("kb.serve.KB_ROOT", tmp_path):
            response = client.get("/visuals/../../../etc/passwd")
            assert response.status_code in (403, 404)

    def test_serves_png_thumbnail(self, client, tmp_path):
        """Should serve PNG thumbnail files."""
        visuals_dir = tmp_path / "50.01.01" / "visuals"
        visuals_dir.mkdir(parents=True)
        thumb = visuals_dir / "slide-1.png"
        thumb.write_bytes(b"\x89PNG fake png")

        with patch("kb.serve.KB_ROOT", tmp_path):
            response = client.get("/visuals/50.01.01/visuals/slide-1.png")
            assert response.status_code == 200


# ===== Posting Queue API Visual Fields =====

class TestPostingQueueVisualFields:
    """Tests that posting queue API includes visual status."""

    @pytest.fixture
    def client(self, tmp_path):
        with patch("kb.serve.KB_ROOT", tmp_path):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                yield client

    def test_posting_queue_includes_visual_status(self, client, tmp_path):
        """Items should have visual_status field."""
        # Create a transcript file
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)
        transcript = {
            "id": "test-transcript",
            "title": "Test",
            "decimal": "50.01.01",
            "transcript": "Hello world",
            "source": {"type": "audio"},
            "analysis": {
                "linkedin_v2": {
                    "post": "Test post content",
                    "_model": "gemini",
                    "_analyzed_at": "2026-02-07T10:00:00",
                }
            }
        }
        (decimal_dir / "test-transcript.json").write_text(json.dumps(transcript))

        # Set up action state with approved + visual_status
        state = {
            "actions": {
                "test-transcript--linkedin_v2": {
                    "status": "approved",
                    "approved_at": "2026-02-07T10:00:00",
                    "visual_status": "ready",
                    "visual_data": {
                        "format": "CAROUSEL",
                        "pdf_path": str(tmp_path / "50.01.01" / "visuals" / "carousel.pdf"),
                        "thumbnail_paths": [str(tmp_path / "50.01.01" / "visuals" / "slide-1.png")],
                    }
                }
            }
        }

        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):
            response = client.get("/api/posting-queue")
            data = response.get_json()

            assert data["total"] >= 1
            item = data["items"][0]
            assert item["visual_status"] == "ready"
            assert item["visual_format"] == "CAROUSEL"
            assert item["thumbnail_url"] is not None
            assert item["pdf_url"] is not None
            assert "/visuals/" in item["thumbnail_url"]


# ===== Approve Triggers Background Thread =====

class TestApproveTriggersThread:
    """Tests that approve endpoint starts background pipeline thread."""

    def test_approve_starts_background_thread(self, tmp_path):
        """Approve should trigger a background thread for visual pipeline."""
        # Create transcript
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
                }
            }
        }
        (decimal_dir / "test-id.json").write_text(json.dumps(transcript))

        # Empty action state (item is pending)
        state = {"actions": {}}
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.run_visual_pipeline") as mock_pipeline, \
             patch("kb.serve.threading.Thread") as mock_thread_cls, \
             patch("kb.serve.pyperclip.copy"):

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post("/api/action/test-id--linkedin_v2/approve")
                assert response.status_code == 200

                data = response.get_json()
                assert data["success"] is True

                # Thread should have been created and started
                mock_thread_cls.assert_called_once()
                call_kwargs = mock_thread_cls.call_args[1]
                assert call_kwargs["target"] == mock_pipeline
                assert call_kwargs["daemon"] is True
                mock_thread.start.assert_called_once()

    def test_approve_returns_immediately(self, tmp_path):
        """Approve should return < 1s (not waiting for pipeline)."""
        import time

        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)
        transcript = {
            "id": "speed-test",
            "title": "Speed",
            "decimal": "50.01.01",
            "transcript": "test",
            "source": {"type": "audio"},
            "analysis": {
                "linkedin_v2": {
                    "post": "Post",
                    "_model": "gemini",
                    "_analyzed_at": "2026-02-07T10:00:00",
                }
            }
        }
        (decimal_dir / "speed-test.json").write_text(json.dumps(transcript))

        state = {"actions": {}}
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.run_visual_pipeline"), \
             patch("kb.serve.pyperclip.copy"):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                start = time.time()
                response = client.post("/api/action/speed-test--linkedin_v2/approve")
                elapsed = time.time() - start

                assert response.status_code == 200
                assert elapsed < 1.0, f"Approve took {elapsed:.2f}s (should be < 1s)"


# ===== Mermaid Base64 Conversion =====

class TestMermaidBase64:
    """Tests for mermaid PNG -> base64 data URI conversion in render_pipeline."""

    @patch("kb.render.render_carousel")
    @patch("kb.render.render_mermaid")
    def test_mermaid_path_converted_to_base64(self, mock_mermaid, mock_carousel):
        """render_pipeline should convert mermaid PNG to base64 data URI."""
        import copy
        from kb.render import render_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake PNG file for mermaid
            mermaid_dir = os.path.join(tmpdir, "mermaid")
            os.makedirs(mermaid_dir)
            fake_png = os.path.join(mermaid_dir, "mermaid.png")
            with open(fake_png, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n fake png content")

            mock_mermaid.return_value = fake_png
            mock_carousel.return_value = {
                "pdf_path": os.path.join(tmpdir, "carousel.pdf"),
                "thumbnail_paths": [],
                "html": "<html>test</html>",
            }

            slides_data = {
                "slides": [
                    {"slide_number": 1, "type": "hook", "content": "Hook", "words": 1},
                    {"slide_number": 2, "type": "mermaid", "content": "graph LR\n  A-->B", "words": 3},
                    {"slide_number": 3, "type": "cta", "content": "CTA", "words": 1},
                ],
                "total_slides": 3,
                "has_mermaid": True,
            }

            result = render_pipeline(slides_data, tmpdir)

            # Check the slide data was mutated to have base64 URI
            mermaid_slide = slides_data["slides"][1]
            assert mermaid_slide["mermaid_image_path"].startswith("data:image/png;base64,")
            assert len(mermaid_slide["mermaid_image_path"]) > 30  # Not empty

    @patch("kb.render.render_carousel")
    @patch("kb.render.render_mermaid")
    def test_mermaid_fallback_on_read_error(self, mock_mermaid, mock_carousel):
        """If PNG can't be read, fallback to raw file path."""
        from kb.render import render_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            # Point to a nonexistent file (render_mermaid returned path but file was deleted)
            mock_mermaid.return_value = "/nonexistent/mermaid.png"
            mock_carousel.return_value = {
                "pdf_path": os.path.join(tmpdir, "carousel.pdf"),
                "thumbnail_paths": [],
                "html": "<html>test</html>",
            }

            slides_data = {
                "slides": [
                    {"slide_number": 1, "type": "mermaid", "content": "graph LR\n  A-->B", "words": 3},
                ],
                "total_slides": 1,
                "has_mermaid": True,
            }

            result = render_pipeline(slides_data, tmpdir)

            # Should fallback to raw path (not crash)
            mermaid_slide = slides_data["slides"][0]
            assert mermaid_slide["mermaid_image_path"] == "/nonexistent/mermaid.png"


# ===== Action Mapping Transition =====

class TestActionMappingTransition:
    """Tests for linkedin_post removal and linkedin_v2 in action_mapping."""

    def test_linkedin_v2_in_defaults(self):
        """linkedin_v2 should be in default action_mapping."""
        from kb.__main__ import DEFAULTS
        mapping = DEFAULTS["serve"]["action_mapping"]
        assert "linkedin_v2" in mapping
        assert mapping["linkedin_v2"] == "LinkedIn"

    def test_linkedin_post_not_in_defaults(self):
        """linkedin_post should NOT be in default action_mapping."""
        from kb.__main__ import DEFAULTS
        mapping = DEFAULTS["serve"]["action_mapping"]
        assert "linkedin_post" not in mapping

    def test_old_linkedin_post_items_not_in_queue(self, tmp_path):
        """Old linkedin_post should not appear in default action_mapping."""
        from kb.__main__ import DEFAULTS
        from kb.serve import get_destination_for_action

        # Check defaults only — user config.yaml may still have linkedin_post
        mapping = DEFAULTS["serve"]["action_mapping"]
        # Build the expanded mapping the same way serve.py does
        expanded = {}
        for pattern, dest in mapping.items():
            expanded[("*", pattern)] = dest
        dest = get_destination_for_action("audio", "linkedin_post", expanded)
        assert dest is None, "linkedin_post should not have a destination in default mapping"

    def test_linkedin_v2_has_destination(self):
        """linkedin_v2 should map to 'LinkedIn' destination."""
        from kb.serve import get_action_mapping, get_destination_for_action

        mapping = get_action_mapping()
        dest = get_destination_for_action("audio", "linkedin_v2", mapping)
        assert dest == "LinkedIn"


# ===== Publish.py AttributeError Fix =====

class TestPublishAttributeError:
    """Tests for AttributeError handling in find_renderables."""

    def test_handles_attribute_error_gracefully(self, tmp_path):
        """find_renderables should not crash on AttributeError."""
        from kb.publish import find_renderables

        # Create a transcript where carousel_slides has a string value (not dict)
        # which would cause AttributeError when calling .get()
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)
        transcript = {
            "id": "bad-format",
            "title": "Bad",
            "decimal": "50.01.01",
            "analysis": {
                "carousel_slides": "raw string not dict"
            }
        }
        (decimal_dir / "bad-format.json").write_text(json.dumps(transcript))

        with patch("kb.publish.KB_ROOT", tmp_path):
            # Should not raise AttributeError
            renderables = find_renderables()
            # The bad transcript should be skipped, not crash
            assert isinstance(renderables, list)


# ===== Run Visual Pipeline Function =====

class TestRunVisualPipeline:
    """Tests for the run_visual_pipeline background function."""

    def test_sets_text_only_for_non_carousel(self, tmp_path):
        """Pipeline should set text_only status for TEXT_ONLY posts."""
        # Create transcript with visual_format = TEXT_ONLY
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)
        transcript = {
            "id": "text-only-test",
            "title": "Text Only Post",
            "decimal": "50.01.01",
            "transcript": "Short opinion take",
            "analysis": {
                "linkedin_v2": {"post": "My opinion", "_model": "gemini", "_analyzed_at": "2026-02-07"},
                "visual_format": {"format": "TEXT_ONLY", "_model": "gemini", "_analyzed_at": "2026-02-07"},
            }
        }
        (decimal_dir / "text-only-test.json").write_text(json.dumps(transcript))

        state = {
            "actions": {
                "text-only-test--linkedin_v2": {
                    "status": "approved",
                }
            }
        }
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import run_visual_pipeline
            run_visual_pipeline(
                "text-only-test--linkedin_v2",
                str(decimal_dir / "text-only-test.json"),
            )

            updated = json.loads(state_file.read_text())
            action = updated["actions"]["text-only-test--linkedin_v2"]
            assert action["visual_status"] == "text_only"

    def test_sets_generating_then_ready_on_success(self, tmp_path):
        """Pipeline should set generating then ready on success."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)
        transcript = {
            "id": "carousel-test",
            "title": "Carousel Post",
            "decimal": "50.01.01",
            "transcript": "How to build a content engine...",
            "analysis": {
                "linkedin_v2": {"post": "My post", "_model": "gemini", "_analyzed_at": "2026-02-07"},
                "visual_format": {"format": "CAROUSEL", "_model": "gemini", "_analyzed_at": "2026-02-07"},
                "carousel_slides": {
                    "slides": [
                        {"slide_number": 1, "type": "hook", "content": "Hook", "words": 1},
                        {"slide_number": 2, "type": "cta", "content": "CTA", "words": 1},
                    ],
                    "total_slides": 2,
                    "has_mermaid": False,
                    "_model": "gemini",
                    "_analyzed_at": "2026-02-07",
                }
            }
        }
        (decimal_dir / "carousel-test.json").write_text(json.dumps(transcript))

        state = {
            "actions": {
                "carousel-test--linkedin_v2": {
                    "status": "approved",
                }
            }
        }
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))

        # Track status transitions
        statuses = []
        original_update = None

        def track_status(action_id, status, data=None):
            statuses.append(status)
            # Actually write to file
            s = json.loads(state_file.read_text())
            if action_id in s["actions"]:
                s["actions"][action_id]["visual_status"] = status
                if data:
                    s["actions"][action_id]["visual_data"] = data
                state_file.write_text(json.dumps(s))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve._update_visual_status", side_effect=track_status), \
             patch("kb.render.render_pipeline") as mock_render:

            mock_render.return_value = {
                "pdf_path": str(decimal_dir / "visuals" / "carousel.pdf"),
                "thumbnail_paths": [str(decimal_dir / "visuals" / "slide-1.png")],
                "errors": [],
            }

            from kb.serve import run_visual_pipeline
            run_visual_pipeline(
                "carousel-test--linkedin_v2",
                str(decimal_dir / "carousel-test.json"),
            )

            # Should have transitioned: generating -> ready
            assert "generating" in statuses
            assert "ready" in statuses

    def test_sets_failed_on_render_error(self, tmp_path):
        """Pipeline should set failed status on render error."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)
        transcript = {
            "id": "fail-test",
            "title": "Fail",
            "decimal": "50.01.01",
            "transcript": "test",
            "analysis": {
                "linkedin_v2": {"post": "Post", "_model": "gemini", "_analyzed_at": "2026-02-07"},
                "visual_format": {"format": "CAROUSEL", "_model": "gemini", "_analyzed_at": "2026-02-07"},
                "carousel_slides": {
                    "slides": [{"slide_number": 1, "type": "hook", "content": "H", "words": 1}],
                    "total_slides": 1,
                    "has_mermaid": False,
                    "_model": "gemini",
                    "_analyzed_at": "2026-02-07",
                }
            }
        }
        (decimal_dir / "fail-test.json").write_text(json.dumps(transcript))

        state = {
            "actions": {
                "fail-test--linkedin_v2": {
                    "status": "approved",
                }
            }
        }
        state_file = tmp_path / "action-state.json"
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.render.render_pipeline") as mock_render:

            mock_render.return_value = {
                "pdf_path": None,
                "thumbnail_paths": [],
                "errors": ["Playwright crashed"],
            }

            from kb.serve import run_visual_pipeline
            run_visual_pipeline(
                "fail-test--linkedin_v2",
                str(decimal_dir / "fail-test.json"),
            )

            updated = json.loads(state_file.read_text())
            assert updated["actions"]["fail-test--linkedin_v2"]["visual_status"] == "failed"
