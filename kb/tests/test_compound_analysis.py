"""Tests for compound analysis (dependency resolution) feature."""

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestTemplateSubstitution:
    """Test template variable substitution."""

    def test_substitute_single_var(self):
        """Test substituting a single variable."""
        # Import here to avoid module-level import issues
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        # Mock the config loading to avoid file dependencies
        with patch('kb.analyze._config', {'defaults': {'gemini_model': 'test'}}):
            with patch('kb.analyze._paths', {'kb_output': Path('/tmp'), 'config_dir': Path('/tmp/config')}):
                # We need to reload the module functions after patching
                from kb.analyze import substitute_template_vars

                prompt = "Here is the summary: {{summary}}"
                context = {"summary": "This is a test summary."}
                result = substitute_template_vars(prompt, context)

                assert result == "Here is the summary: This is a test summary."

    def test_substitute_multiple_vars(self):
        """Test substituting multiple variables."""
        from kb.analyze import substitute_template_vars

        prompt = "Summary: {{summary}}\n\nKey Points: {{key_points}}"
        context = {
            "summary": "Overview of the session",
            "key_points": "- Point 1\n- Point 2"
        }
        result = substitute_template_vars(prompt, context)

        assert "Overview of the session" in result
        assert "- Point 1\n- Point 2" in result

    def test_unmatched_var_preserved(self):
        """Test that unmatched variables are preserved."""
        from kb.analyze import substitute_template_vars

        prompt = "Known: {{known}}, Unknown: {{unknown}}"
        context = {"known": "value"}
        result = substitute_template_vars(prompt, context)

        assert result == "Known: value, Unknown: {{unknown}}"


class TestFormatPrerequisiteOutput:
    """Test formatting of prerequisite analysis outputs."""

    def test_format_simple_string(self):
        """Test formatting a simple string result."""
        from kb.analyze import format_prerequisite_output

        result = {"summary": "This is the summary", "_model": "gemini-2.0"}
        formatted = format_prerequisite_output(result)

        assert formatted == "This is the summary"
        assert "_model" not in formatted

    def test_format_list_output(self):
        """Test formatting a list output (like key_points)."""
        from kb.analyze import format_prerequisite_output

        result = {
            "key_points": [
                {"quote": "First quote", "insight": "First insight"},
                {"quote": "Second quote", "insight": "Second insight"}
            ],
            "_model": "gemini-2.0"
        }
        formatted = format_prerequisite_output(result)

        assert "First quote" in formatted
        assert "First insight" in formatted
        assert "Second quote" in formatted
        assert "_model" not in formatted

    def test_format_empty_result(self):
        """Test formatting empty result."""
        from kb.analyze import format_prerequisite_output

        assert format_prerequisite_output({}) == ""
        assert format_prerequisite_output(None) == ""


class TestLoadAnalysisTypeWithRequires:
    """Test loading analysis types with requires field."""

    def test_load_type_with_requires(self):
        """Test that requires field is parsed correctly."""
        from kb.analyze import load_analysis_type

        # Create a temporary analysis type file
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_types_dir = Path(tmpdir) / "analysis_types"
            analysis_types_dir.mkdir()

            # Create a compound analysis type
            compound_type = {
                "name": "test_compound",
                "description": "A test compound analysis",
                "requires": ["summary", "key_points"],
                "prompt": "Based on {{summary}} and {{key_points}}...",
                "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}}
            }
            with open(analysis_types_dir / "test_compound.json", "w") as f:
                json.dump(compound_type, f)

            # Patch the ANALYSIS_TYPES_DIR
            with patch('kb.analyze.ANALYSIS_TYPES_DIR', analysis_types_dir):
                loaded = load_analysis_type("test_compound")

                assert loaded["name"] == "test_compound"
                assert loaded["requires"] == ["summary", "key_points"]
                assert "{{summary}}" in loaded["prompt"]

    def test_load_type_without_requires(self):
        """Test that types without requires field work (defaults to empty list)."""
        from kb.analyze import load_analysis_type

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_types_dir = Path(tmpdir) / "analysis_types"
            analysis_types_dir.mkdir()

            simple_type = {
                "name": "simple",
                "description": "A simple analysis",
                "prompt": "Analyze this...",
                "output_schema": {"type": "object"}
            }
            with open(analysis_types_dir / "simple.json", "w") as f:
                json.dump(simple_type, f)

            with patch('kb.analyze.ANALYSIS_TYPES_DIR', analysis_types_dir):
                loaded = load_analysis_type("simple")

                assert loaded["name"] == "simple"
                assert loaded.get("requires", []) == []


class TestRunAnalysisWithDeps:
    """Test the dependency resolution function."""

    def test_runs_prerequisites_when_missing(self):
        """Test that prerequisites are run when not present."""
        from kb.analyze import run_analysis_with_deps, load_analysis_type

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_types_dir = Path(tmpdir) / "analysis_types"
            analysis_types_dir.mkdir()

            # Create a simple summary type
            summary_type = {
                "name": "summary",
                "description": "Summary",
                "prompt": "Summarize this",
                "output_schema": {"type": "object", "properties": {"summary": {"type": "string"}}}
            }
            with open(analysis_types_dir / "summary.json", "w") as f:
                json.dump(summary_type, f)

            # Create a compound type that requires summary
            compound_type = {
                "name": "compound",
                "description": "Compound",
                "requires": ["summary"],
                "prompt": "Based on {{summary}}, create output",
                "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}}
            }
            with open(analysis_types_dir / "compound.json", "w") as f:
                json.dump(compound_type, f)

            with patch('kb.analyze.ANALYSIS_TYPES_DIR', analysis_types_dir):
                # Mock the analyze_transcript function
                mock_results = [
                    {"summary": "Test summary"},  # First call for summary
                    {"result": "Final result"}    # Second call for compound
                ]
                call_count = [0]

                def mock_analyze(*args, **kwargs):
                    result = mock_results[call_count[0]]
                    call_count[0] += 1
                    return result

                with patch('kb.analyze.analyze_transcript', side_effect=mock_analyze):
                    transcript_data = {
                        "transcript": "Test transcript text",
                        "title": "Test",
                        "analysis": {}  # No existing analysis
                    }

                    result, prereqs_run = run_analysis_with_deps(
                        transcript_data=transcript_data,
                        analysis_type="compound",
                        model="test-model",
                        existing_analysis={}
                    )

                    # Should have run the summary prerequisite
                    assert "summary" in prereqs_run
                    assert result == {"result": "Final result"}

    def test_skips_existing_prerequisites(self):
        """Test that existing prerequisites are not re-run."""
        from kb.analyze import run_analysis_with_deps

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_types_dir = Path(tmpdir) / "analysis_types"
            analysis_types_dir.mkdir()

            # Create a compound type that requires summary
            compound_type = {
                "name": "compound",
                "description": "Compound",
                "requires": ["summary"],
                "prompt": "Based on {{summary}}, create output",
                "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}}
            }
            with open(analysis_types_dir / "compound.json", "w") as f:
                json.dump(compound_type, f)

            with patch('kb.analyze.ANALYSIS_TYPES_DIR', analysis_types_dir):
                # Mock analyze_transcript - should only be called once (for compound)
                with patch('kb.analyze.analyze_transcript', return_value={"result": "Final"}) as mock:
                    transcript_data = {
                        "transcript": "Test transcript",
                        "title": "Test",
                        "analysis": {}
                    }

                    # Existing analysis already has summary
                    existing = {
                        "summary": {"summary": "Existing summary", "_model": "test"}
                    }

                    result, prereqs_run = run_analysis_with_deps(
                        transcript_data=transcript_data,
                        analysis_type="compound",
                        model="test-model",
                        existing_analysis=existing
                    )

                    # Summary should NOT have been run (it exists)
                    assert prereqs_run == []
                    # analyze_transcript should only be called once
                    assert mock.call_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
