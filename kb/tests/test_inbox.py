"""Tests for inbox processing module."""

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestGetInboxConfig:
    """Test inbox configuration loading."""

    def test_default_config(self):
        """Test default configuration values."""
        from kb.inbox import get_inbox_config

        with patch('kb.inbox._config', {}):
            config = get_inbox_config()

            assert "path" in config
            assert "archive_path" in config
            assert "decimal_defaults" in config
            assert str(config["path"]).endswith(".kb/inbox")
            assert str(config["archive_path"]).endswith(".kb/archive")

    def test_custom_paths(self):
        """Test custom paths from config."""
        from kb.inbox import get_inbox_config

        custom_config = {
            "inbox": {
                "path": "/custom/inbox",
                "archive_path": "/custom/archive",
            }
        }

        with patch('kb.inbox._config', custom_config):
            config = get_inbox_config()

            assert config["path"] == Path("/custom/inbox")
            assert config["archive_path"] == Path("/custom/archive")

    def test_null_archive_path(self):
        """Test that null archive_path means delete after processing."""
        from kb.inbox import get_inbox_config

        custom_config = {
            "inbox": {
                "path": "~/.kb/inbox",
                "archive_path": None,
            }
        }

        with patch('kb.inbox._config', custom_config):
            config = get_inbox_config()

            assert config["archive_path"] is None

    def test_decimal_defaults(self):
        """Test loading decimal defaults."""
        from kb.inbox import get_inbox_config

        custom_config = {
            "inbox": {
                "decimal_defaults": {
                    "50.01.01": {"analyses": ["summary", "skool_post"]},
                    "50.03": {"analyses": ["summary", "guide"]},
                }
            }
        }

        with patch('kb.inbox._config', custom_config):
            config = get_inbox_config()

            assert "50.01.01" in config["decimal_defaults"]
            assert config["decimal_defaults"]["50.01.01"]["analyses"] == ["summary", "skool_post"]


class TestScanInbox:
    """Test inbox scanning."""

    def test_scan_empty_inbox(self):
        """Test scanning empty or non-existent inbox."""
        from kb.inbox import scan_inbox

        with tempfile.TemporaryDirectory() as tmpdir:
            inbox_path = Path(tmpdir) / "inbox"
            # Doesn't exist yet
            files = scan_inbox(inbox_path)
            assert files == []

            # Exists but empty
            inbox_path.mkdir()
            files = scan_inbox(inbox_path)
            assert files == []

    def test_scan_with_files(self):
        """Test scanning inbox with media files."""
        from kb.inbox import scan_inbox

        with tempfile.TemporaryDirectory() as tmpdir:
            inbox_path = Path(tmpdir) / "inbox"
            inbox_path.mkdir()

            # Create decimal directories
            dec_dir = inbox_path / "50.01.01"
            dec_dir.mkdir()

            # Create test files
            (dec_dir / "test-video.mp4").touch()
            (dec_dir / "test-audio.mp3").touch()
            (dec_dir / "not-media.txt").touch()  # Should be skipped

            files = scan_inbox(inbox_path)

            assert len(files) == 2
            assert all(f["decimal"] == "50.01.01" for f in files)
            filenames = [f["filename"] for f in files]
            assert "test-video.mp4" in filenames
            assert "test-audio.mp3" in filenames
            assert "not-media.txt" not in filenames

    def test_scan_multiple_decimals(self):
        """Test scanning inbox with multiple decimal directories."""
        from kb.inbox import scan_inbox

        with tempfile.TemporaryDirectory() as tmpdir:
            inbox_path = Path(tmpdir) / "inbox"
            inbox_path.mkdir()

            # Create multiple decimal directories
            (inbox_path / "50.01.01").mkdir()
            (inbox_path / "50.03.02").mkdir()
            (inbox_path / "not-a-decimal").mkdir()  # Should be skipped

            (inbox_path / "50.01.01" / "video1.mp4").touch()
            (inbox_path / "50.03.02" / "video2.mp4").touch()
            (inbox_path / "not-a-decimal" / "video3.mp4").touch()

            files = scan_inbox(inbox_path)

            assert len(files) == 2
            decimals = [f["decimal"] for f in files]
            assert "50.01.01" in decimals
            assert "50.03.02" in decimals


class TestGetAnalysesForDecimal:
    """Test analysis type resolution for decimals."""

    def test_exact_match(self):
        """Test exact decimal match."""
        from kb.inbox import get_analyses_for_decimal

        config = {
            "decimal_defaults": {
                "50.01.01": {"analyses": ["summary", "skool_post"]},
            }
        }

        result = get_analyses_for_decimal("50.01.01", config)
        assert result == ["summary", "skool_post"]

    def test_prefix_match(self):
        """Test prefix matching for decimals."""
        from kb.inbox import get_analyses_for_decimal

        config = {
            "decimal_defaults": {
                "50.01": {"analyses": ["summary", "key_points"]},
            }
        }

        # Should match 50.01.01 via prefix
        result = get_analyses_for_decimal("50.01.01", config)
        assert result == ["summary", "key_points"]

    def test_default_fallback(self):
        """Test fallback to summary when no match."""
        from kb.inbox import get_analyses_for_decimal

        config = {"decimal_defaults": {}}

        result = get_analyses_for_decimal("50.99.99", config)
        assert result == ["summary"]


class TestGenerateTitleFromFilename:
    """Test title generation from filenames."""

    def test_simple_filename(self):
        """Test simple filename conversion."""
        from kb.inbox import generate_title_from_filename

        assert generate_title_from_filename("skool-call.mp4") == "Skool Call"
        assert generate_title_from_filename("alpha_session.mp4") == "Alpha Session"

    def test_with_date_prefix(self):
        """Test removal of date prefixes."""
        from kb.inbox import generate_title_from_filename

        assert generate_title_from_filename("2026-01-30-alpha-session.mp4") == "Alpha Session"
        assert generate_title_from_filename("260130-quick-call.mp4") == "Quick Call"

    def test_empty_result(self):
        """Test fallback for empty result."""
        from kb.inbox import generate_title_from_filename

        assert generate_title_from_filename("2026-01-30.mp4") == "Untitled"


class TestEnsureInboxDirs:
    """Test inbox directory creation."""

    def test_creates_directories(self):
        """Test that decimal directories are created."""
        from kb.inbox import ensure_inbox_dirs

        with tempfile.TemporaryDirectory() as tmpdir:
            inbox_path = Path(tmpdir) / "inbox"

            registry = {
                "decimals": {
                    "50.01.01": {"label": "Test 1"},
                    "50.03.02": {"label": "Test 2"},
                },
                "tags": [],
            }

            with patch('kb.inbox.load_registry', return_value=registry):
                created = ensure_inbox_dirs(inbox_path)

            assert inbox_path.exists()
            assert (inbox_path / "50.01.01").exists()
            assert (inbox_path / "50.03.02").exists()
            assert len(created) == 2


class TestProcessFile:
    """Test individual file processing."""

    def test_unknown_decimal_fails(self):
        """Test that unknown decimals cause failure."""
        from kb.inbox import process_file

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.mp4"
            file_path.touch()

            file_info = {
                "path": file_path,
                "decimal": "99.99.99",
                "filename": "test.mp4",
            }

            registry = {"decimals": {}}

            with patch('kb.inbox.load_registry', return_value=registry):
                result = process_file(file_info, {})

            assert not result["success"]
            assert "Unknown decimal" in result["error"]

    def test_dry_run_no_changes(self):
        """Test that dry run doesn't process files."""
        from kb.inbox import process_file

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.mp4"
            file_path.touch()

            file_info = {
                "path": file_path,
                "decimal": "50.01.01",
                "filename": "test.mp4",
            }

            registry = {"decimals": {"50.01.01": {"label": "Test"}}}

            with patch('kb.inbox.load_registry', return_value=registry):
                result = process_file(file_info, {}, dry_run=True)

            assert result["success"]
            assert file_path.exists()  # File should still exist


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
