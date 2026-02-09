"""
Tests for conditional template rendering in kb/analyze.py.

Tests the render_conditional_template() function which handles:
- {{#if var}}content{{/if}} blocks
- {{#if var}}content{{else}}fallback{{/if}} blocks
- Integration with {{variable}} substitution
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from kb.analyze import render_conditional_template, substitute_template_vars


class TestSubstituteTemplateVars:
    """Tests for the basic variable substitution (existing functionality)."""

    def test_simple_substitution(self):
        """Basic variable replacement."""
        prompt = "Hello {{name}}!"
        context = {"name": "World"}
        result = substitute_template_vars(prompt, context)
        assert result == "Hello World!"

    def test_multiple_variables(self):
        """Multiple variables in one template."""
        prompt = "{{greeting}} {{name}}, welcome to {{place}}."
        context = {"greeting": "Hi", "name": "Blake", "place": "KB"}
        result = substitute_template_vars(prompt, context)
        assert result == "Hi Blake, welcome to KB."

    def test_missing_variable_unchanged(self):
        """Missing variables are left as-is."""
        prompt = "Hello {{name}}! Your code is {{unknown}}."
        context = {"name": "Blake"}
        result = substitute_template_vars(prompt, context)
        assert result == "Hello Blake! Your code is {{unknown}}."


class TestRenderConditionalTemplate:
    """Tests for conditional template rendering."""

    def test_simple_if_true(self):
        """{{#if var}}content{{/if}} renders content when var exists."""
        prompt = "Start {{#if summary}}Has summary{{/if}} End"
        context = {"summary": "Some summary text"}
        result = render_conditional_template(prompt, context)
        assert result == "Start Has summary End"

    def test_simple_if_false(self):
        """{{#if var}}content{{/if}} renders nothing when var missing."""
        prompt = "Start {{#if summary}}Has summary{{/if}} End"
        context = {}
        result = render_conditional_template(prompt, context)
        assert result == "Start  End"

    def test_if_else_true(self):
        """{{#if var}}content{{else}}fallback{{/if}} uses content when var exists."""
        prompt = "{{#if key_points}}{{key_points}}{{else}}{{transcript}}{{/if}}"
        context = {"key_points": "- Point 1\n- Point 2", "transcript": "Raw text"}
        result = render_conditional_template(prompt, context)
        assert result == "- Point 1\n- Point 2"

    def test_if_else_false(self):
        """{{#if var}}content{{else}}fallback{{/if}} uses fallback when var missing."""
        prompt = "{{#if key_points}}{{key_points}}{{else}}{{transcript}}{{/if}}"
        context = {"transcript": "Raw transcript text here"}
        result = render_conditional_template(prompt, context)
        assert result == "Raw transcript text here"

    def test_falsy_value_empty_string(self):
        """Empty string is falsy, should use else branch."""
        prompt = "{{#if summary}}{{summary}}{{else}}No summary{{/if}}"
        context = {"summary": ""}
        result = render_conditional_template(prompt, context)
        assert result == "No summary"

    def test_falsy_value_none(self):
        """None is falsy, should use else branch."""
        prompt = "{{#if summary}}{{summary}}{{else}}No summary{{/if}}"
        context = {"summary": None}
        result = render_conditional_template(prompt, context)
        assert result == "No summary"

    def test_multiline_content(self):
        """Conditional blocks can span multiple lines."""
        prompt = """{{#if key_points}}Key Points:
{{key_points}}

Full transcript:
{{/if}}{{transcript}}"""
        context = {
            "key_points": "- Insight 1\n- Insight 2",
            "transcript": "The full transcript text."
        }
        result = render_conditional_template(prompt, context)
        expected = """Key Points:
- Insight 1
- Insight 2

Full transcript:
The full transcript text."""
        assert result == expected

    def test_multiline_without_optional(self):
        """Multiline template without the optional variable."""
        prompt = """{{#if key_points}}Key Points:
{{key_points}}

Full transcript:
{{/if}}{{transcript}}"""
        context = {"transcript": "Just the transcript."}
        result = render_conditional_template(prompt, context)
        assert result == "Just the transcript."

    def test_multiple_conditionals(self):
        """Multiple conditional blocks in one template."""
        prompt = "{{#if a}}A{{/if}} {{#if b}}B{{/if}} {{#if c}}C{{/if}}"
        context = {"a": "yes", "c": "yes"}
        result = render_conditional_template(prompt, context)
        assert result == "A  C"

    def test_nested_variables_in_conditional(self):
        """Variables inside conditional blocks are substituted."""
        prompt = "{{#if has_data}}Name: {{name}}, Value: {{value}}{{/if}}"
        context = {"has_data": True, "name": "Test", "value": "123"}
        result = render_conditional_template(prompt, context)
        assert result == "Name: Test, Value: 123"

    def test_nested_conditionals_not_supported(self):
        """Document that nested conditionals are NOT supported.

        The regex-based approach matches the first {{/if}} it finds,
        which breaks nested structures. Use sequential conditionals instead.

        Example of what NOT to do:
            {{#if a}}outer {{#if b}}inner{{/if}} end{{/if}}

        Instead, use sequential blocks:
            {{#if a}}outer {{/if}}{{#if b}}inner{{/if}}{{#if a}} end{{/if}}
        """
        # This demonstrates the limitation - nested conditionals produce unexpected results
        prompt = "{{#if a}}outer {{#if b}}inner{{/if}} end{{/if}}"
        context = {"a": "yes", "b": "yes"}
        result = render_conditional_template(prompt, context)

        # The result is NOT "outer inner end" as one might expect
        # Instead, the first {{/if}} closes the outer block prematurely
        assert result != "outer inner end"
        # The actual result has leftover markup
        assert "{{" in result or "}}" in result or result == "outer inner end"

    def test_real_world_linkedin_example(self):
        """Test case based on actual linkedin_post usage."""
        prompt = """INPUT CONTENT:

{{transcript}}

Write a post that shares the most actionable insight."""
        context = {"transcript": "Today I learned about conditional templates."}
        result = render_conditional_template(prompt, context)
        expected = """INPUT CONTENT:

Today I learned about conditional templates.

Write a post that shares the most actionable insight."""
        assert result == expected

    def test_real_world_skool_example(self):
        """Test case based on actual skool_post usage with key_points."""
        prompt = """INPUT CONTENT:

{{#if key_points}}Key Moments (with timestamps):
{{key_points}}

Full Transcript:
{{/if}}{{transcript}}

Write a Skool post.{{#if key_points}} Use the key moments.{{/if}}"""

        # With key_points
        context_with = {
            "key_points": "00:05:30 - Important insight\n00:12:45 - Key learning",
            "transcript": "Full transcript here."
        }
        result_with = render_conditional_template(prompt, context_with)
        assert "Key Moments (with timestamps):" in result_with
        assert "00:05:30" in result_with
        assert "Use the key moments." in result_with
        assert "Full transcript here." in result_with

        # Without key_points
        context_without = {"transcript": "Just the transcript."}
        result_without = render_conditional_template(prompt, context_without)
        assert "Key Moments" not in result_without
        assert "Use the key moments" not in result_without
        assert "Just the transcript." in result_without


class TestResolveOptionalInputs:
    """Tests for resolve_optional_inputs() function."""

    def test_always_includes_transcript(self):
        """Transcript is always included in the context."""
        from kb.analyze import resolve_optional_inputs

        analysis_def = {"optional_inputs": []}
        existing_analysis = {}
        transcript = "Hello world"

        result = resolve_optional_inputs(analysis_def, existing_analysis, transcript)
        assert result["transcript"] == "Hello world"

    def test_includes_available_optional(self):
        """Optional inputs are included when available."""
        from kb.analyze import resolve_optional_inputs

        analysis_def = {"optional_inputs": ["key_points", "summary"]}
        existing_analysis = {
            "key_points": {"key_points": [{"quote": "test", "insight": "learn"}]}
        }
        transcript = "Transcript text"

        result = resolve_optional_inputs(analysis_def, existing_analysis, transcript)
        assert "transcript" in result
        assert "key_points" in result
        assert "summary" not in result  # Not in existing_analysis

    def test_skips_missing_optional(self):
        """Optional inputs not in existing analysis are skipped."""
        from kb.analyze import resolve_optional_inputs

        analysis_def = {"optional_inputs": ["key_points"]}
        existing_analysis = {}  # No key_points
        transcript = "Transcript"

        result = resolve_optional_inputs(analysis_def, existing_analysis, transcript)
        assert "transcript" in result
        assert "key_points" not in result

    def test_empty_optional_inputs(self):
        """Empty optional_inputs list works correctly."""
        from kb.analyze import resolve_optional_inputs

        analysis_def = {"optional_inputs": []}
        existing_analysis = {"key_points": {"data": "exists"}}
        transcript = "Text"

        result = resolve_optional_inputs(analysis_def, existing_analysis, transcript)
        assert result == {"transcript": "Text"}

    def test_no_optional_inputs_field(self):
        """Analysis def without optional_inputs field works."""
        from kb.analyze import resolve_optional_inputs

        analysis_def = {}  # No optional_inputs key
        existing_analysis = {}
        transcript = "Text"

        result = resolve_optional_inputs(analysis_def, existing_analysis, transcript)
        assert result == {"transcript": "Text"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
