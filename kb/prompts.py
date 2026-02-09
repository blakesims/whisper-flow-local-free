"""
Prompt template rendering utilities.

Pure functions for formatting prerequisite outputs, substituting template
variables, rendering conditional blocks, and resolving optional inputs.
Used by kb/analyze.py and kb/judge.py for LLM prompt construction.

All functions are stdlib-only (re, json) with no side effects or IO.
"""

import re
import json

__all__ = [
    "format_prerequisite_output",
    "substitute_template_vars",
    "render_conditional_template",
    "resolve_optional_inputs",
]


def format_prerequisite_output(analysis_result: dict) -> str:
    """
    Format an analysis result for injection into a compound prompt.

    Handles various output structures by extracting the main content.
    Returns a clean string representation.
    """
    if not analysis_result:
        return ""

    # Filter out metadata keys (those starting with _)
    content = {k: v for k, v in analysis_result.items() if not k.startswith("_")}

    # If there's a single key with a string value, return that directly
    if len(content) == 1:
        value = list(content.values())[0]
        if isinstance(value, str):
            return value
        elif isinstance(value, list):
            # Format list items nicely (e.g., key_points)
            formatted_items = []
            for item in value:
                if isinstance(item, dict):
                    # Format dict items (e.g., {"quote": "...", "insight": "..."})
                    parts = [f"- {v}" if k in ("quote", "insight") else f"  {k}: {v}"
                             for k, v in item.items()]
                    formatted_items.append("\n".join(parts))
                else:
                    formatted_items.append(f"- {item}")
            return "\n\n".join(formatted_items)

    # If there's a 'post' key (e.g. linkedin_v2), extract just the post text
    if 'post' in content and isinstance(content['post'], str):
        return content['post']

    # Multiple keys - return JSON representation
    return json.dumps(content, indent=2, ensure_ascii=False)


def substitute_template_vars(prompt: str, context: dict) -> str:
    """
    Replace {{variable}} placeholders in a prompt with context values.

    Args:
        prompt: The prompt template with {{variable}} placeholders
        context: Dict mapping variable names to their formatted values

    Returns:
        The prompt with placeholders substituted
    """
    def replacer(match):
        var_name = match.group(1)
        if var_name in context:
            return context[var_name]
        # Leave unmatched placeholders as-is (for debugging)
        return match.group(0)

    return re.sub(r'\{\{(\w+)\}\}', replacer, prompt)


def render_conditional_template(prompt: str, context: dict) -> str:
    """
    Render Handlebars-style conditional blocks in a prompt template.

    Supports:
    - {{#if var}}content{{/if}} - renders content when var exists and is truthy
    - {{#if var}}content{{else}}fallback{{/if}} - renders fallback when var missing/falsy

    After processing conditionals, also substitutes {{variable}} placeholders.

    Note: Nested {{#if}} blocks are NOT supported. The regex matches the first
    {{/if}} it finds, which breaks nesting. For complex logic, use multiple
    sequential conditionals instead of nesting them.

    Args:
        prompt: The prompt template with conditional blocks
        context: Dict mapping variable names to their values

    Returns:
        The prompt with conditionals resolved and variables substituted

    Example:
        >>> render_conditional_template(
        ...     "{{#if key_points}}{{key_points}}{{else}}{{transcript}}{{/if}}",
        ...     {"transcript": "Hello world"}
        ... )
        'Hello world'
    """
    # Pattern for {{#if var}}...{{/if}} with optional {{else}}
    # Note: Non-greedy matching means nested {{#if}} blocks are NOT supported.
    # The regex matches the first {{/if}} it finds, breaking nested structures.
    if_pattern = re.compile(
        r'\{\{#if\s+(\w+)\}\}'   # {{#if varname}}
        r'(.*?)'                  # content (non-greedy)
        r'(?:\{\{else\}\}(.*?))?' # optional {{else}}fallback
        r'\{\{/if\}\}',           # {{/if}}
        re.DOTALL                 # Allow . to match newlines
    )

    def if_replacer(match):
        var_name = match.group(1)
        if_content = match.group(2)
        else_content = match.group(3) or ""

        # Check if variable exists and is truthy
        value = context.get(var_name)
        if value:
            return if_content
        else:
            return else_content

    # Process all conditional blocks
    result = if_pattern.sub(if_replacer, prompt)

    # Now substitute any remaining {{variable}} placeholders
    result = substitute_template_vars(result, context)

    return result


def resolve_optional_inputs(
    analysis_def: dict,
    existing_analysis: dict,
    transcript_text: str
) -> dict:
    """
    Resolve optional inputs for an analysis type.

    Optional inputs are included in the context if they exist in the transcript's
    existing analysis, but don't trigger auto-run if missing. This allows analysis
    types to gracefully handle varying input availability.

    Always includes 'transcript' as a fallback for when optional inputs aren't available.

    Args:
        analysis_def: The analysis type definition (with optional_inputs field)
        existing_analysis: Dict of existing analysis results for this transcript
        transcript_text: The raw transcript text (always included as fallback)

    Returns:
        Dict of {input_name: formatted_value} for available optional inputs.
        Always includes 'transcript' key.

    Example:
        analysis_def = {"optional_inputs": ["key_points", "summary"]}
        existing = {"key_points": {"key_points": [...]}}
        result = resolve_optional_inputs(analysis_def, existing, "raw text...")
        # Returns {"transcript": "raw text...", "key_points": "formatted..."}
        # (summary not included because it wasn't in existing)
    """
    context = {
        "transcript": transcript_text
    }

    optional_inputs = analysis_def.get("optional_inputs", [])

    for opt_input in optional_inputs:
        if opt_input in existing_analysis:
            # Format the optional input for injection into the prompt
            context[opt_input] = format_prerequisite_output(existing_analysis[opt_input])

    return context
