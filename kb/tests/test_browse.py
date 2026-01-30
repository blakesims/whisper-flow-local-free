"""Tests for browse mode functionality in kb/serve.py."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil


class TestGetCategories:
    """Tests for /api/categories endpoint."""

    def test_returns_categories_with_counts(self):
        """Categories endpoint returns decimals with transcript counts."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)

            # Create test directories with JSON files
            (kb_root / "50.01.01").mkdir()
            (kb_root / "50.01.01" / "transcript1.json").write_text('{}')
            (kb_root / "50.01.01" / "transcript2.json").write_text('{}')

            (kb_root / "50.02.01").mkdir()
            (kb_root / "50.02.01" / "transcript3.json").write_text('{}')

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/categories')
                    data = response.get_json()

                    assert response.status_code == 200
                    assert 'categories' in data
                    assert len(data['categories']) == 2

                    # Check counts
                    cat_map = {c['decimal']: c['count'] for c in data['categories']}
                    assert cat_map['50.01.01'] == 2
                    assert cat_map['50.02.01'] == 1

    def test_excludes_config_directory(self):
        """Config directory is excluded from categories."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)

            # Create config dir with files
            (kb_root / "config").mkdir()
            (kb_root / "config" / "settings.json").write_text('{}')

            # Create valid decimal dir
            (kb_root / "50.01.01").mkdir()
            (kb_root / "50.01.01" / "transcript.json").write_text('{}')

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/categories')
                    data = response.get_json()

                    decimals = [c['decimal'] for c in data['categories']]
                    assert 'config' not in decimals
                    assert '50.01.01' in decimals

    def test_empty_kb_returns_empty_list(self):
        """Empty KB returns empty categories list."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/categories')
                    data = response.get_json()

                    assert response.status_code == 200
                    assert data['categories'] == []


class TestGetTranscripts:
    """Tests for /api/transcripts/<decimal> endpoint."""

    def test_returns_transcripts_for_decimal(self):
        """Returns list of transcripts in a category."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)

            # Create test transcript
            (kb_root / "50.01.01").mkdir()
            transcript_data = {
                "id": "50.01.01-260130-test",
                "title": "Test Transcript",
                "decimal": "50.01.01",
                "metadata": {"transcribed_at": "2026-01-30T10:00:00", "word_count": 500},
                "source": {"type": "video"},
                "analysis": {"summary": {}, "key_points": {}}
            }
            (kb_root / "50.01.01" / "test.json").write_text(json.dumps(transcript_data))

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/transcripts/50.01.01')
                    data = response.get_json()

                    assert response.status_code == 200
                    assert len(data['transcripts']) == 1
                    assert data['transcripts'][0]['id'] == "50.01.01-260130-test"
                    assert data['transcripts'][0]['title'] == "Test Transcript"
                    assert 'summary' in data['transcripts'][0]['analysis_types']
                    assert 'key_points' in data['transcripts'][0]['analysis_types']

    def test_invalid_decimal_format(self):
        """Invalid decimal format returns 400."""
        from kb.serve import app

        with app.test_client() as client:
            response = client.get('/api/transcripts/invalid')
            assert response.status_code == 400

            response = client.get('/api/transcripts/50.01')
            assert response.status_code == 400

    def test_nonexistent_decimal(self):
        """Nonexistent decimal returns 404."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/transcripts/99.99.99')
                    assert response.status_code == 404


class TestGetTranscript:
    """Tests for /api/transcript/<id> endpoint."""

    def test_returns_full_transcript(self):
        """Returns full transcript with analyses."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)

            # Create test transcript
            (kb_root / "50.01.01").mkdir()
            transcript_data = {
                "id": "50.01.01-260130-test",
                "title": "Test Transcript",
                "decimal": "50.01.01",
                "transcript": "This is the transcript text.",
                "metadata": {"transcribed_at": "2026-01-30T10:00:00", "word_count": 5},
                "source": {"type": "video", "path": "/path/to/video.mp4"},
                "tags": ["tag1", "tag2"],
                "analysis": {
                    "summary": {
                        "summary": "This is a summary.",
                        "_analyzed_at": "2026-01-30T11:00:00",
                        "_model": "gpt-4"
                    }
                }
            }
            (kb_root / "50.01.01" / "test.json").write_text(json.dumps(transcript_data))

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/transcript/50.01.01-260130-test')
                    data = response.get_json()

                    assert response.status_code == 200
                    assert data['id'] == "50.01.01-260130-test"
                    assert data['title'] == "Test Transcript"
                    assert data['transcript'] == "This is the transcript text."
                    assert len(data['analyses']) == 1
                    assert data['analyses'][0]['name'] == 'summary'
                    assert data['analyses'][0]['content'] == 'This is a summary.'
                    assert 'tag1' in data['tags']

    def test_invalid_transcript_id(self):
        """Invalid transcript ID format returns 400."""
        from kb.serve import app

        with app.test_client() as client:
            response = client.get('/api/transcript/invalid<script>')
            assert response.status_code == 400

    def test_nonexistent_transcript(self):
        """Nonexistent transcript returns 404."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)
            (kb_root / "50.01.01").mkdir()

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/transcript/nonexistent-id')
                    assert response.status_code == 404


class TestSearch:
    """Tests for /api/search endpoint."""

    def test_search_by_title(self):
        """Search finds transcripts by title."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)

            # Create test transcripts
            (kb_root / "50.01.01").mkdir()
            (kb_root / "50.01.01" / "meeting.json").write_text(json.dumps({
                "id": "50.01.01-260130-meeting",
                "title": "Weekly Team Meeting",
                "decimal": "50.01.01",
                "transcript": "Some content here.",
                "metadata": {"transcribed_at": "2026-01-30T10:00:00"},
                "source": {"type": "meeting"},
                "tags": []
            }))

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/search?q=weekly')
                    data = response.get_json()

                    assert response.status_code == 200
                    assert len(data['results']) == 1
                    assert data['results'][0]['title'] == "Weekly Team Meeting"
                    assert data['results'][0]['match_type'] == 'title'

    def test_search_by_transcript_content(self):
        """Search finds transcripts by content."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)

            (kb_root / "50.01.01").mkdir()
            (kb_root / "50.01.01" / "session.json").write_text(json.dumps({
                "id": "50.01.01-260130-session",
                "title": "Training Session",
                "decimal": "50.01.01",
                "transcript": "Today we discussed machine learning algorithms.",
                "metadata": {"transcribed_at": "2026-01-30T10:00:00"},
                "source": {"type": "video"},
                "tags": []
            }))

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/search?q=machine')
                    data = response.get_json()

                    assert response.status_code == 200
                    assert len(data['results']) == 1
                    assert data['results'][0]['match_type'] == 'transcript'
                    assert 'machine' in data['results'][0]['snippet'].lower()

    def test_search_by_tag(self):
        """Search finds transcripts by tag."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)

            (kb_root / "50.01.01").mkdir()
            (kb_root / "50.01.01" / "tagged.json").write_text(json.dumps({
                "id": "50.01.01-260130-tagged",
                "title": "Some Document",
                "decimal": "50.01.01",
                "transcript": "Content here.",
                "metadata": {"transcribed_at": "2026-01-30T10:00:00"},
                "source": {"type": "video"},
                "tags": ["important", "review"]
            }))

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/search?q=important')
                    data = response.get_json()

                    assert response.status_code == 200
                    assert len(data['results']) == 1
                    assert data['results'][0]['match_type'] == 'tag'

    def test_search_query_too_short(self):
        """Search with query < 2 chars returns 400."""
        from kb.serve import app

        with app.test_client() as client:
            response = client.get('/api/search?q=a')
            assert response.status_code == 400

            response = client.get('/api/search?q=')
            assert response.status_code == 400

    def test_search_no_results(self):
        """Search with no matches returns empty list."""
        from kb.serve import app

        with tempfile.TemporaryDirectory() as tmpdir:
            kb_root = Path(tmpdir)
            (kb_root / "50.01.01").mkdir()

            with patch('kb.serve.KB_ROOT', kb_root):
                with app.test_client() as client:
                    response = client.get('/api/search?q=nonexistent')
                    data = response.get_json()

                    assert response.status_code == 200
                    assert len(data['results']) == 0


class TestBrowseRoute:
    """Tests for /browse route."""

    def test_browse_returns_html(self):
        """Browse route returns HTML template."""
        from kb.serve import app

        with app.test_client() as client:
            response = client.get('/browse')
            assert response.status_code == 200
            assert b'<!DOCTYPE html>' in response.data
            assert b'kb-browse' in response.data
