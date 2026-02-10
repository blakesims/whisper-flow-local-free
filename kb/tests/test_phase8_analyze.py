"""
Tests for Phase 8C: Trigger Analysis from UI.

Tests:
- POST /api/transcript/<id>/analyze returns 200 with valid types, 400 with invalid, 404 with bad id
- GET /api/analysis-types returns only user-facing types (excludes internal)
- Concurrent analysis rejection (409)
- GET /api/processing returns processing state
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestAnalysisTypesEndpoint:
    """Tests for GET /api/analysis-types."""

    def test_returns_user_facing_types(self):
        """Should return analysis types excluding internal ones."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.get("/api/analysis-types")
            assert response.status_code == 200

            data = response.get_json()
            names = [t["name"] for t in data["types"]]

            # Should include user-facing types
            assert "linkedin_v2" in names
            assert "skool_post" in names
            assert "summary" in names

            # Should exclude internal types
            assert "visual_format" not in names
            assert "carousel_slides" not in names
            assert "linkedin_judge" not in names
            assert "linkedin_post" not in names

    def test_each_type_has_name_and_description(self):
        """Each type should have name and description fields."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.get("/api/analysis-types")
            data = response.get_json()

            for t in data["types"]:
                assert "name" in t
                assert "description" in t


class TestAnalyzeEndpoint:
    """Tests for POST /api/transcript/<id>/analyze."""

    def _setup(self, tmp_path):
        """Create a transcript file for testing."""
        decimal_dir = tmp_path / "50.01.01"
        decimal_dir.mkdir(parents=True)
        transcript = {
            "id": "test-analyze",
            "title": "Test Transcript for Analysis",
            "decimal": "50.01.01",
            "transcript": "This is a test transcript with enough content for analysis.",
            "source": {"type": "audio"},
            "analysis": {},
        }
        (decimal_dir / "test-analyze.json").write_text(json.dumps(transcript))

        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')
        return state_file

    def test_valid_analysis_returns_200(self, tmp_path):
        """Valid analysis request should return 200."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.threading.Thread") as mock_thread_cls:

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/transcript/test-analyze/analyze",
                    json={"analysis_types": ["summary"]},
                )
                assert response.status_code == 200

                data = response.get_json()
                assert data["success"] is True
                assert "summary" in data["types"]

                # Thread should have been started
                mock_thread_cls.assert_called_once()
                mock_thread.start.assert_called_once()

    def test_invalid_type_returns_400(self, tmp_path):
        """Unknown analysis type should return 400."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/transcript/test-analyze/analyze",
                    json={"analysis_types": ["nonexistent_type"]},
                )
                assert response.status_code == 400
                assert "Unknown" in response.get_json()["error"]

    def test_missing_transcript_returns_404(self, tmp_path):
        """Nonexistent transcript should return 404."""
        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/transcript/nonexistent-id/analyze",
                    json={"analysis_types": ["summary"]},
                )
                assert response.status_code == 404

    def test_invalid_transcript_id_returns_400(self, tmp_path):
        """Invalid transcript ID format should return 400."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            # Semicolon passes Flask routing but fails our ^[\w\.\-]+$ regex
            response = client.post(
                "/api/transcript/bad;id/analyze",
                json={"analysis_types": ["summary"]},
            )
            assert response.status_code == 400
            assert "Invalid" in response.get_json()["error"]

    def test_empty_types_returns_400(self, tmp_path):
        """Empty analysis_types list should return 400."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/transcript/test-analyze/analyze",
                    json={"analysis_types": []},
                )
                assert response.status_code == 400

    def test_missing_body_returns_400(self, tmp_path):
        """Missing request body should return 400."""
        from kb.serve import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            response = client.post(
                "/api/transcript/test-analyze/analyze",
                content_type="application/json",
                data="{}",
            )
            assert response.status_code == 400

    def test_concurrent_analysis_returns_409(self, tmp_path):
        """Concurrent analysis for same transcript should return 409."""
        state_file = self._setup(tmp_path)

        # Pre-set processing state
        state = json.loads(state_file.read_text())
        state["processing"] = {
            "test-analyze": {
                "types": ["summary"],
                "started_at": "2026-02-10T10:00:00",
            }
        }
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path):

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/transcript/test-analyze/analyze",
                    json={"analysis_types": ["linkedin_v2"]},
                )
                assert response.status_code == 409

    def test_sets_processing_state(self, tmp_path):
        """Should set processing state in action-state.json."""
        state_file = self._setup(tmp_path)

        with patch("kb.serve.ACTION_STATE_PATH", state_file), \
             patch("kb.serve.KB_ROOT", tmp_path), \
             patch("kb.serve.threading.Thread") as mock_thread_cls:

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/api/transcript/test-analyze/analyze",
                    json={"analysis_types": ["summary"]},
                )
                assert response.status_code == 200

        # Check processing state was set
        state = json.loads(state_file.read_text())
        assert "test-analyze" in state.get("processing", {})
        assert state["processing"]["test-analyze"]["types"] == ["summary"]


class TestProcessingEndpoint:
    """Tests for GET /api/processing."""

    def test_returns_processing_state(self, tmp_path):
        """Should return current processing state."""
        state_file = tmp_path / "action-state.json"
        state = {
            "actions": {},
            "processing": {
                "transcript-1": {
                    "types": ["linkedin_v2"],
                    "started_at": "2026-02-10T10:00:00",
                }
            }
        }
        state_file.write_text(json.dumps(state))

        with patch("kb.serve.ACTION_STATE_PATH", state_file):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/processing")
                assert response.status_code == 200

                data = response.get_json()
                assert "transcript-1" in data["processing"]

    def test_empty_processing(self, tmp_path):
        """Should return empty processing when nothing is running."""
        state_file = tmp_path / "action-state.json"
        state_file.write_text('{"actions": {}}')

        with patch("kb.serve.ACTION_STATE_PATH", state_file):
            from kb.serve import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.get("/api/processing")
                assert response.status_code == 200

                data = response.get_json()
                assert data["processing"] == {}
