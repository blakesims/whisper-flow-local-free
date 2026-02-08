"""
Tests for Carousel Templates — T024 Phase 1+2: Template system + content slides.

Tests:
- Analysis type config loading (visual_format, carousel_slides)
- Config.json schema validation (brand, header, templates)
- Jinja2 template rendering for brand-purple, modern-editorial, tech-minimal
- Profile photo base64 loading
- Template parameterization (no hardcoded text)
- Title page scaling based on content length
- Markdown-to-HTML parsing (bullets, numbered lists, plain text)
- Timeline/progress indicators on all templates
- header.show_on_all_slides config honored by all templates
- CTA slide styling
"""

import pytest
import json
import os
import sys
import base64
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from jinja2 import Environment, FileSystemLoader, select_autoescape
from kb.render import markdown_to_html

# Paths
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_CONFIG_DIR = os.path.join(REPO_ROOT, "kb", "config", "analysis_types")
CAROUSEL_DIR = os.path.join(REPO_ROOT, "kb", "carousel_templates")


def _make_env():
    """Create Jinja2 environment matching production settings."""
    env = Environment(
        loader=FileSystemLoader(CAROUSEL_DIR),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["markdown_to_html"] = markdown_to_html
    return env


# ===== Sample Data =====

SAMPLE_SLIDES = [
    {"slide_number": 1, "type": "hook", "content": "I automated my entire posting workflow.", "words": 6, "subtitle": "From transcription to publishing in 30 seconds"},
    {"slide_number": 2, "type": "content", "content": "- Use Whisper API to convert audio recordings to text\n- Process meeting recordings, voice memos, and podcasts\n- Store transcripts in structured JSON for downstream processing", "words": 22, "title": "Set Up Transcription"},
    {"slide_number": 3, "type": "content", "content": "- Feed transcript chunks to Claude for topic extraction\n- Generate structured summaries with key insights\n- Identify quotable moments and actionable takeaways", "words": 20, "title": "Run LLM Analysis"},
    {"slide_number": 4, "type": "content", "content": "- Score each content piece for visual potential\n- Classify format: carousel, single image, text post\n- Auto-select the right template based on content type", "words": 20, "title": "Visual Classification"},
    {"slide_number": 5, "type": "mermaid", "content": "graph LR\n    A[Voice Note] --> B[Whisper]\n    B --> C[LLM Analysis]\n    C --> D[Visual Gen]\n    D --> E[PDF Carousel]", "words": 12, "mermaid_image_path": None, "title": "The Full Pipeline"},
    {"slide_number": 6, "type": "cta", "content": "Want to build your own AI content pipeline?", "words": 9, "subtitle": "Follow along as I automate everything from transcription to publishing."},
]


# ===== Config Tests =====

class TestVisualFormatConfig:
    """Tests for visual_format.json analysis type config."""

    def test_config_exists(self):
        path = os.path.join(KB_CONFIG_DIR, "visual_format.json")
        assert os.path.exists(path), f"visual_format.json not found at {path}"

    def test_config_valid_json(self):
        path = os.path.join(KB_CONFIG_DIR, "visual_format.json")
        with open(path) as f:
            config = json.load(f)
        assert isinstance(config, dict)

    def test_config_has_required_fields(self):
        path = os.path.join(KB_CONFIG_DIR, "visual_format.json")
        with open(path) as f:
            config = json.load(f)
        assert config["name"] == "visual_format"
        assert "requires" in config
        assert "linkedin_v2" in config["requires"]
        assert "prompt" in config
        assert "output_schema" in config

    def test_output_schema_has_format_field(self):
        path = os.path.join(KB_CONFIG_DIR, "visual_format.json")
        with open(path) as f:
            config = json.load(f)
        schema = config["output_schema"]
        assert "format" in schema["properties"]
        assert set(schema["properties"]["format"]["enum"]) == {"CAROUSEL", "TEXT_ONLY"}

    def test_output_schema_has_include_mermaid(self):
        path = os.path.join(KB_CONFIG_DIR, "visual_format.json")
        with open(path) as f:
            config = json.load(f)
        schema = config["output_schema"]
        assert "include_mermaid" in schema["properties"]
        assert schema["properties"]["include_mermaid"]["type"] == "boolean"

    def test_required_fields_in_schema(self):
        path = os.path.join(KB_CONFIG_DIR, "visual_format.json")
        with open(path) as f:
            config = json.load(f)
        required = config["output_schema"]["required"]
        assert "format" in required
        assert "include_mermaid" in required
        assert "reasoning" in required
        assert "confidence" in required

    def test_prompt_mentions_carousel_and_text_only(self):
        path = os.path.join(KB_CONFIG_DIR, "visual_format.json")
        with open(path) as f:
            config = json.load(f)
        prompt = config["prompt"]
        assert "CAROUSEL" in prompt
        assert "TEXT_ONLY" in prompt
        assert "include_mermaid" in prompt


class TestCarouselSlidesConfig:
    """Tests for carousel_slides.json analysis type config."""

    def test_config_exists(self):
        path = os.path.join(KB_CONFIG_DIR, "carousel_slides.json")
        assert os.path.exists(path), f"carousel_slides.json not found at {path}"

    def test_config_valid_json(self):
        path = os.path.join(KB_CONFIG_DIR, "carousel_slides.json")
        with open(path) as f:
            config = json.load(f)
        assert isinstance(config, dict)

    def test_config_requires_linkedin_v2(self):
        path = os.path.join(KB_CONFIG_DIR, "carousel_slides.json")
        with open(path) as f:
            config = json.load(f)
        assert config["requires"] == ["linkedin_v2"]

    def test_output_schema_has_slides_array(self):
        path = os.path.join(KB_CONFIG_DIR, "carousel_slides.json")
        with open(path) as f:
            config = json.load(f)
        schema = config["output_schema"]
        assert "slides" in schema["properties"]
        assert schema["properties"]["slides"]["type"] == "array"

    def test_slide_item_schema(self):
        path = os.path.join(KB_CONFIG_DIR, "carousel_slides.json")
        with open(path) as f:
            config = json.load(f)
        item_schema = config["output_schema"]["properties"]["slides"]["items"]
        required = item_schema["required"]
        assert "slide_number" in required
        assert "type" in required
        assert "content" in required
        assert "words" in required

    def test_slide_types(self):
        path = os.path.join(KB_CONFIG_DIR, "carousel_slides.json")
        with open(path) as f:
            config = json.load(f)
        item_schema = config["output_schema"]["properties"]["slides"]["items"]
        slide_types = item_schema["properties"]["type"]["enum"]
        assert "hook" in slide_types
        assert "content" in slide_types
        assert "mermaid" in slide_types
        assert "cta" in slide_types

    def test_prompt_mentions_slide_count_range(self):
        path = os.path.join(KB_CONFIG_DIR, "carousel_slides.json")
        with open(path) as f:
            config = json.load(f)
        prompt = config["prompt"]
        assert "6" in prompt and "10" in prompt
        assert "10-30 words" in prompt or ("10" in prompt and "30" in prompt)

    def test_prompt_has_markdown_formatting_instruction(self):
        """Phase 2 M2: LLM prompt must instruct markdown formatting."""
        path = os.path.join(KB_CONFIG_DIR, "carousel_slides.json")
        with open(path) as f:
            config = json.load(f)
        prompt = config["prompt"]
        assert "- " in prompt and "bullet" in prompt.lower()
        assert "1. " in prompt and "numbered" in prompt.lower()


# ===== Config.json Schema Tests =====

class TestCarouselConfig:
    """Tests for carousel_templates/config.json schema — T024 Phase 1."""

    @pytest.fixture
    def config(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            return json.load(f)

    def test_config_exists(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        assert os.path.exists(path)

    def test_config_valid_json(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            config = json.load(f)
        assert isinstance(config, dict)

    def test_dimensions(self, config):
        dims = config["dimensions"]
        assert dims["width"] == 1080
        assert dims["height"] == 1350

    def test_has_brand_purple_template(self, config):
        assert "brand-purple" in config["templates"]
        assert config["templates"]["brand-purple"]["file"] == "brand-purple.html"

    def test_has_modern_editorial_template(self, config):
        assert "modern-editorial" in config["templates"]
        assert config["templates"]["modern-editorial"]["file"] == "modern-editorial.html"

    def test_has_tech_minimal_template(self, config):
        assert "tech-minimal" in config["templates"]
        assert config["templates"]["tech-minimal"]["file"] == "tech-minimal.html"

    def test_default_template_is_brand_purple(self, config):
        assert config["defaults"]["template"] == "brand-purple"

    def test_brand_has_author_name(self, config):
        assert "author_name" in config["brand"]
        assert config["brand"]["author_name"] == "Blake Sims"

    def test_brand_has_community_name(self, config):
        assert "community_name" in config["brand"]
        assert config["brand"]["community_name"] == "Claude Code Architects"

    def test_brand_has_profile_photo_path(self, config):
        assert "profile_photo_path" in config["brand"]

    def test_brand_has_handle(self, config):
        assert "handle" in config["brand"]

    def test_header_config(self, config):
        assert "header" in config
        header = config["header"]
        assert header["show_on_all_slides"] is True
        assert header["author_position"] == "left"
        assert header["community_position"] == "right"

    def test_slide_range(self, config):
        slide_range = config["defaults"]["slide_range"]
        assert slide_range["min"] == 6
        assert slide_range["max"] == 10

    def test_template_colors_configurable(self, config):
        """Verify all templates have essential color keys."""
        expected_color_keys = {"background", "text_primary", "text_secondary", "accent"}
        for template_name in ["brand-purple", "modern-editorial", "tech-minimal"]:
            colors = config["templates"][template_name]["colors"]
            for key in expected_color_keys:
                assert key in colors, f"Missing color key '{key}' in template '{template_name}'"

    def test_template_fonts_configurable(self, config):
        """Verify all templates have essential font keys."""
        expected_font_keys = {"heading", "body", "mono"}
        for template_name in ["brand-purple", "modern-editorial", "tech-minimal"]:
            fonts = config["templates"][template_name]["fonts"]
            for key in expected_font_keys:
                assert key in fonts, f"Missing font key '{key}' in template '{template_name}'"

    def test_templates_have_google_fonts_url(self, config):
        """Each template should have a Google Fonts URL for Playwright rendering."""
        for template_name in ["brand-purple", "modern-editorial", "tech-minimal"]:
            fonts = config["templates"][template_name]["fonts"]
            assert "google_fonts_url" in fonts, f"Missing google_fonts_url in template '{template_name}'"
            assert fonts["google_fonts_url"].startswith("https://fonts.googleapis.com/")

    def test_old_templates_removed(self, config):
        """Old dark-purple and light templates should not be in config."""
        assert "dark-purple" not in config["templates"]
        assert "light" not in config["templates"]


# ===== Markdown-to-HTML Filter Tests =====

class TestMarkdownToHtml:
    """Tests for the markdown_to_html Jinja2 filter in render.py."""

    def test_empty_string(self):
        assert str(markdown_to_html("")) == ""

    def test_bullet_list(self):
        text = "- First item\n- Second item\n- Third item"
        result = str(markdown_to_html(text))
        assert "<ul>" in result
        assert "<li>First item</li>" in result
        assert "<li>Second item</li>" in result
        assert "<li>Third item</li>" in result
        assert "</ul>" in result

    def test_bullet_list_star_syntax(self):
        text = "* Item A\n* Item B"
        result = str(markdown_to_html(text))
        assert "<ul>" in result
        assert "<li>Item A</li>" in result
        assert "<li>Item B</li>" in result

    def test_numbered_list(self):
        text = "1. First step\n2. Second step\n3. Third step"
        result = str(markdown_to_html(text))
        assert "<ol>" in result
        assert "<li>First step</li>" in result
        assert "<li>Second step</li>" in result
        assert "<li>Third step</li>" in result
        assert "</ol>" in result

    def test_plain_text_with_line_breaks(self):
        text = "Line one\nLine two\nLine three"
        result = str(markdown_to_html(text))
        assert "<p>" in result
        assert "<br>" in result
        assert "Line one" in result
        assert "Line two" in result

    def test_mixed_content(self):
        """Bullets followed by plain text should produce separate elements."""
        text = "- Bullet one\n- Bullet two\n\nSome plain text here"
        result = str(markdown_to_html(text))
        assert "<ul>" in result
        assert "<li>Bullet one</li>" in result
        assert "<p>Some plain text here</p>" in result

    def test_no_raw_dash_prefix_in_output(self):
        """The '- ' prefix should be stripped, not rendered."""
        text = "- Item with content"
        result = str(markdown_to_html(text))
        assert "<li>Item with content</li>" in result
        assert "- Item" not in result

    def test_no_raw_number_prefix_in_output(self):
        """The '1. ' prefix should be stripped, not rendered."""
        text = "1. Step one"
        result = str(markdown_to_html(text))
        assert "<li>Step one</li>" in result
        assert "1. Step" not in result

    def test_returns_markup_type(self):
        """Should return Markup (safe) type, not plain string."""
        from markupsafe import Markup
        result = markdown_to_html("- test")
        assert isinstance(result, Markup)

    def test_blank_lines_separate_groups(self):
        """Blank lines should separate adjacent list groups."""
        text = "- A\n- B\n\n1. One\n2. Two"
        result = str(markdown_to_html(text))
        assert "<ul>" in result
        assert "<ol>" in result
        assert result.index("</ul>") < result.index("<ol>")


# ===== Template Rendering Tests =====

class TestBrandPurpleTemplate:
    """Tests for brand-purple.html Jinja2 template rendering."""

    @pytest.fixture
    def env(self):
        return _make_env()

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    @pytest.fixture
    def template_context(self, config):
        template_config = config["templates"]["brand-purple"]
        return {
            "slides": SAMPLE_SLIDES,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
            "header": config["header"],
            "profile_photo_data": None,
        }

    def test_template_loads(self, env):
        template = env.get_template("brand-purple.html")
        assert template is not None

    def test_template_renders(self, env, template_context):
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert len(html) > 0

    def test_renders_all_slides(self, env, template_context):
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        for slide in SAMPLE_SLIDES:
            assert f'id="slide-{slide["slide_number"]}"' in html

    def test_renders_header_with_author_name(self, env, template_context):
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "Blake Sims" in html

    def test_renders_header_with_community_name(self, env, template_context):
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "Claude Code Architects" in html

    def test_renders_hook_as_title_page(self, env, template_context):
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert SAMPLE_SLIDES[0]["content"] in html
        assert "title-page-main-title" in html

    def test_renders_profile_photo_placeholder(self, env, template_context):
        """When no profile photo, should render initials."""
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "BS" in html  # Initials for Blake Sims

    def test_renders_profile_photo_when_data_provided(self, env, template_context):
        """When profile photo data provided, should render img tag."""
        template_context["profile_photo_data"] = "data:image/png;base64,iVBORw0KGgo="
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "data:image/png;base64,iVBORw0KGgo=" in html

    def test_title_page_scales_font(self, env, template_context):
        """Title page should use different CSS classes based on content length."""
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        # "I automated my entire posting workflow." is ~42 chars -> title-medium
        assert "title-medium" in html

    def test_title_page_short_title(self, env, template_context):
        """Short titles should get title-short class."""
        template_context["slides"] = [
            {"slide_number": 1, "type": "hook", "content": "Build an AI Pipeline", "words": 4},
        ]
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "title-short" in html

    def test_title_page_long_title(self, env, template_context):
        """Long titles should get title-long class."""
        template_context["slides"] = [
            {"slide_number": 1, "type": "hook", "content": "A Very Long Title That Goes On And On For Quite A While And Needs A Smaller Font", "words": 15},
        ]
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "title-long" in html

    def test_renders_cta_slide(self, env, template_context):
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert SAMPLE_SLIDES[-1]["content"] in html
        assert "cta-heading" in html

    def test_renders_mermaid_slide(self, env, template_context):
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        # With no mermaid_image_path, should render code
        assert "graph LR" in html

    def test_renders_handle(self, env, template_context):
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "@blakesims" in html

    def test_page_breaks_between_slides(self, env, template_context):
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert html.count("page-break-after: always") == len(SAMPLE_SLIDES) - 1

    def test_no_hardcoded_names(self, env, template_context):
        """Template should use variables, not hardcoded names."""
        template_context["brand"]["author_name"] = "Jane Doe"
        template_context["brand"]["community_name"] = "Test Community"
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "Jane Doe" in html
        assert "Test Community" in html
        # Should NOT contain the old hardcoded values
        assert "Blake Sims" not in html

    def test_timeline_indicator_present(self, env, template_context):
        """Content slides should have numbered circle timeline."""
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "tl-dot" in html
        assert "tl-step" in html
        assert "tl-dot active" in html or 'class="tl-dot active"' in html

    def test_timeline_fills_progressively(self, env, template_context):
        """First content slide should show step 1 active, others not."""
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        # Should contain both filled and active states
        assert "tl-step active" in html or 'class="tl-step active"' in html
        assert "tl-step filled" in html or "tl-dot filled" in html

    def test_content_renders_as_bullets(self, env, template_context):
        """Markdown bullets should render as <ul><li> elements."""
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "<ul>" in html
        assert "<li>" in html
        # Raw '- ' prefix should not appear in rendered output
        assert "- Use Whisper" not in html
        assert "Use Whisper" in html

    def test_numbered_list_content(self, env, template_context):
        """Numbered list content should render as <ol><li>."""
        template_context["slides"] = [
            {"slide_number": 1, "type": "hook", "content": "Test", "words": 1},
            {"slide_number": 2, "type": "content", "content": "1. First step\n2. Second step\n3. Third step", "words": 9, "title": "Steps"},
            {"slide_number": 3, "type": "cta", "content": "Done", "words": 1},
        ]
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "<ol>" in html
        assert "<li>First step</li>" in html

    def test_plain_text_content(self, env, template_context):
        """Plain text should render as <p> with <br>."""
        template_context["slides"] = [
            {"slide_number": 1, "type": "hook", "content": "Test", "words": 1},
            {"slide_number": 2, "type": "content", "content": "Line one\nLine two\nLine three", "words": 6, "title": "Info"},
            {"slide_number": 3, "type": "cta", "content": "Done", "words": 1},
        ]
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        assert "<p>" in html
        assert "<br>" in html

    def test_header_show_on_all_slides_respected(self, env, template_context):
        """When show_on_all_slides is false, content slides should hide header."""
        template_context["header"]["show_on_all_slides"] = False
        template = env.get_template("brand-purple.html")
        html = template.render(**template_context)
        # Count actual header div elements (not CSS class definitions)
        # With show_on_all_slides=False, only the hook slide should have header div
        header_div_count = html.count('<div class="header">')
        assert header_div_count == 1  # Only the hook slide


class TestModernEditorialTemplate:
    """Tests for modern-editorial.html Jinja2 template rendering."""

    @pytest.fixture
    def env(self):
        return _make_env()

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    @pytest.fixture
    def template_context(self, config):
        template_config = config["templates"]["modern-editorial"]
        return {
            "slides": SAMPLE_SLIDES,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
            "header": config["header"],
            "profile_photo_data": None,
        }

    def test_template_loads(self, env):
        template = env.get_template("modern-editorial.html")
        assert template is not None

    def test_template_renders(self, env, template_context):
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        assert len(html) > 0

    def test_renders_all_slides(self, env, template_context):
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        for slide in SAMPLE_SLIDES:
            assert f'id="slide-{slide["slide_number"]}"' in html

    def test_renders_editorial_indicators(self, env, template_context):
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        assert "editorial-big-number" in html
        assert "editorial-pip" in html

    def test_editorial_big_number_format(self, env, template_context):
        """Editorial numbers should be zero-padded (01, 02, 03)."""
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        assert "01" in html  # First content slide

    def test_editorial_pip_progress(self, env, template_context):
        """Pip bar should show filled, active, and unfilled states."""
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        assert "editorial-pip filled" in html or "editorial-pip active" in html

    def test_renders_header(self, env, template_context):
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        assert "Blake Sims" in html
        assert "Claude Code Architects" in html

    def test_renders_profile_placeholder(self, env, template_context):
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        assert "BS" in html  # Initials

    def test_page_breaks(self, env, template_context):
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        assert html.count("page-break-after: always") == len(SAMPLE_SLIDES) - 1

    def test_content_renders_as_bullets(self, env, template_context):
        """Markdown bullets should render as HTML list."""
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        assert "<ul>" in html
        assert "<li>" in html
        assert "Use Whisper" in html

    def test_header_show_on_all_slides_respected(self, env, template_context):
        """When show_on_all_slides is false, content/mermaid/cta should hide header."""
        template_context["header"]["show_on_all_slides"] = False
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        # Count actual header div elements (not CSS class definitions)
        header_div_count = html.count('<div class="header">')
        assert header_div_count == 1  # Only the hook slide

    def test_cta_slide_styling(self, env, template_context):
        """CTA slide should have call-to-action elements."""
        template = env.get_template("modern-editorial.html")
        html = template.render(**template_context)
        assert "cta-heading" in html
        assert "cta-button" in html


class TestTechMinimalTemplate:
    """Tests for tech-minimal.html Jinja2 template rendering."""

    @pytest.fixture
    def env(self):
        return _make_env()

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    @pytest.fixture
    def template_context(self, config):
        template_config = config["templates"]["tech-minimal"]
        return {
            "slides": SAMPLE_SLIDES,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
            "header": config["header"],
            "profile_photo_data": None,
        }

    def test_template_loads(self, env):
        template = env.get_template("tech-minimal.html")
        assert template is not None

    def test_template_renders(self, env, template_context):
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert len(html) > 0

    def test_renders_all_slides(self, env, template_context):
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        for slide in SAMPLE_SLIDES:
            assert f'id="slide-{slide["slide_number"]}"' in html

    def test_renders_terminal_bar(self, env, template_context):
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert "terminal-bar" in html
        assert "terminal-dot" in html

    def test_renders_breadcrumb_progress(self, env, template_context):
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert "breadcrumb" in html
        assert "bc-step" in html

    def test_breadcrumb_active_state(self, env, template_context):
        """Breadcrumb should have active and filled states."""
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert "bc-step active" in html or 'class="bc-step active"' in html

    def test_renders_step_bar(self, env, template_context):
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert "step-bar" in html
        assert "step-bar-segment" in html

    def test_step_bar_colored_segments(self, env, template_context):
        """Step bar should have filled and active segments."""
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert "step-bar-segment active" in html or 'class="step-bar-segment active"' in html

    def test_renders_header(self, env, template_context):
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert "Blake Sims" in html
        assert "Claude Code Architects" in html

    def test_renders_profile_placeholder(self, env, template_context):
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert "BS" in html

    def test_page_breaks(self, env, template_context):
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert html.count("page-break-after: always") == len(SAMPLE_SLIDES) - 1

    def test_content_renders_as_bullets(self, env, template_context):
        """Markdown bullets should render as HTML list."""
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert "<ul>" in html
        assert "<li>" in html
        assert "Use Whisper" in html

    def test_header_show_on_all_slides_respected(self, env, template_context):
        """When show_on_all_slides is false, content/mermaid/cta should hide header."""
        template_context["header"]["show_on_all_slides"] = False
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        # Count actual header div elements (not CSS class definitions)
        header_div_count = html.count('<div class="header">')
        assert header_div_count == 1  # Only the hook slide

    def test_cta_slide_styling(self, env, template_context):
        """CTA slide should have call-to-action elements."""
        template = env.get_template("tech-minimal.html")
        html = template.render(**template_context)
        assert "cta-heading" in html
        assert "cta-button" in html


class TestProfilePhotoLoading:
    """Tests for profile photo base64 loading in render.py."""

    def test_load_missing_photo_returns_none(self):
        from kb.render import load_profile_photo_base64
        config = {
            "brand": {"profile_photo_path": "nonexistent-photo.png"}
        }
        result = load_profile_photo_base64(config)
        assert result is None

    def test_load_no_path_returns_none(self):
        from kb.render import load_profile_photo_base64
        config = {"brand": {}}
        result = load_profile_photo_base64(config)
        assert result is None

    def test_load_real_png(self):
        """Create a temp PNG and verify base64 loading."""
        from kb.render import load_profile_photo_base64, CAROUSEL_TEMPLATES_DIR

        # Create a minimal 1x1 PNG in the carousel templates dir
        # PNG header for a 1x1 transparent pixel
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        test_photo_path = os.path.join(CAROUSEL_TEMPLATES_DIR, "_test_profile.png")
        try:
            with open(test_photo_path, "wb") as f:
                f.write(png_data)

            config = {
                "brand": {"profile_photo_path": "_test_profile.png"}
            }
            result = load_profile_photo_base64(config)
            assert result is not None
            assert result.startswith("data:image/png;base64,")
        finally:
            if os.path.exists(test_photo_path):
                os.unlink(test_photo_path)


class TestTemplateMermaidWithImage:
    """Tests for mermaid slide with an actual image path."""

    @pytest.fixture
    def env(self):
        return _make_env()

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    def test_mermaid_with_image_path(self, env, config):
        """When mermaid_image_path is set, render an img tag."""
        slides = [
            {"slide_number": 1, "type": "hook", "content": "Test hook", "words": 2},
            {"slide_number": 2, "type": "mermaid", "content": "graph LR\n  A-->B", "words": 2,
             "mermaid_image_path": "data:image/png;base64,abc123", "title": "Diagram"},
            {"slide_number": 3, "type": "cta", "content": "Test CTA", "words": 2},
        ]
        template_config = config["templates"]["brand-purple"]
        context = {
            "slides": slides,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
            "header": config["header"],
            "profile_photo_data": None,
        }
        template = env.get_template("brand-purple.html")
        html = template.render(**context)
        assert 'data:image/png;base64,abc123' in html

    def test_mermaid_without_image_path(self, env, config):
        """When mermaid_image_path is None, render code as text."""
        slides = [
            {"slide_number": 1, "type": "hook", "content": "Test hook", "words": 2},
            {"slide_number": 2, "type": "mermaid", "content": "graph LR\n  A-->B", "words": 2,
             "mermaid_image_path": None},
            {"slide_number": 3, "type": "cta", "content": "Test CTA", "words": 2},
        ]
        template_config = config["templates"]["brand-purple"]
        context = {
            "slides": slides,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
            "header": config["header"],
            "profile_photo_data": None,
        }
        template = env.get_template("brand-purple.html")
        html = template.render(**context)
        assert "graph LR" in html


class TestMinimalSlideSet:
    """Test with minimum slide count (6 slides)."""

    @pytest.fixture
    def env(self):
        return _make_env()

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    def test_six_slides(self, env, config):
        slides = [
            {"slide_number": i + 1, "type": t, "content": f"- Slide {i+1} content", "words": 3}
            for i, t in enumerate(["hook", "content", "content", "content", "content", "cta"])
        ]
        for template_name in ["brand-purple", "modern-editorial", "tech-minimal"]:
            template_config = config["templates"][template_name]
            context = {
                "slides": slides,
                "width": config["dimensions"]["width"],
                "height": config["dimensions"]["height"],
                "colors": template_config["colors"],
                "fonts": template_config["fonts"],
                "brand": config["brand"],
                "header": config["header"],
                "profile_photo_data": None,
            }
            template = env.get_template(template_config["file"])
            html = template.render(**context)
            assert html.count("page-break-after: always") == 5, f"Template {template_name} should have 5 page breaks"
            for i in range(1, 7):
                assert f'id="slide-{i}"' in html, f"Template {template_name} missing slide-{i}"


class TestAllTemplatesContentTypes:
    """Cross-template tests for all content types rendering correctly."""

    @pytest.fixture
    def env(self):
        return _make_env()

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    @pytest.fixture(params=["brand-purple", "modern-editorial", "tech-minimal"])
    def template_name(self, request):
        return request.param

    def _render(self, env, config, template_name, slides):
        template_config = config["templates"][template_name]
        context = {
            "slides": slides,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
            "header": config["header"],
            "profile_photo_data": None,
        }
        template = env.get_template(template_config["file"])
        return template.render(**context)

    def test_bullet_content(self, env, config, template_name):
        slides = [
            {"slide_number": 1, "type": "hook", "content": "Test", "words": 1},
            {"slide_number": 2, "type": "content", "content": "- Alpha\n- Beta\n- Gamma", "words": 3, "title": "Bullets"},
            {"slide_number": 3, "type": "cta", "content": "End", "words": 1},
        ]
        html = self._render(env, config, template_name, slides)
        assert "<ul>" in html, f"{template_name}: missing <ul> for bullets"
        assert "<li>Alpha</li>" in html, f"{template_name}: missing bullet item"

    def test_numbered_content(self, env, config, template_name):
        slides = [
            {"slide_number": 1, "type": "hook", "content": "Test", "words": 1},
            {"slide_number": 2, "type": "content", "content": "1. First\n2. Second\n3. Third", "words": 3, "title": "Steps"},
            {"slide_number": 3, "type": "cta", "content": "End", "words": 1},
        ]
        html = self._render(env, config, template_name, slides)
        assert "<ol>" in html, f"{template_name}: missing <ol> for numbered list"
        assert "<li>First</li>" in html, f"{template_name}: missing numbered item"

    def test_plain_text_content(self, env, config, template_name):
        slides = [
            {"slide_number": 1, "type": "hook", "content": "Test", "words": 1},
            {"slide_number": 2, "type": "content", "content": "Some plain text\nWith a second line", "words": 7, "title": "Info"},
            {"slide_number": 3, "type": "cta", "content": "End", "words": 1},
        ]
        html = self._render(env, config, template_name, slides)
        assert "<p>" in html, f"{template_name}: missing <p> for plain text"
        assert "Some plain text" in html, f"{template_name}: missing text content"

    def test_hook_slide_present(self, env, config, template_name):
        slides = [
            {"slide_number": 1, "type": "hook", "content": "Hook title here", "words": 3},
            {"slide_number": 2, "type": "cta", "content": "End", "words": 1},
        ]
        html = self._render(env, config, template_name, slides)
        assert "Hook title here" in html

    def test_cta_slide_present(self, env, config, template_name):
        slides = [
            {"slide_number": 1, "type": "hook", "content": "Start", "words": 1},
            {"slide_number": 2, "type": "cta", "content": "Follow me for more", "words": 4, "subtitle": "More good stuff"},
        ]
        html = self._render(env, config, template_name, slides)
        assert "Follow me for more" in html
        assert "cta-heading" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
