"""
Tests for Phase 2: Visual Classifier configs + Carousel Templates.

Tests:
- Analysis type config loading (visual_format, carousel_slides)
- Jinja2 template rendering with sample slide data
- Config.json structure validation
- Template dimensions and slide type handling
"""

import pytest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from jinja2 import Environment, FileSystemLoader

# Paths
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_CONFIG_DIR = os.path.join(REPO_ROOT, "kb", "config", "analysis_types")
CAROUSEL_DIR = os.path.join(REPO_ROOT, "kb", "carousel_templates")


# ===== Sample Data =====

SAMPLE_SLIDES = [
    {"slide_number": 1, "type": "hook", "content": "I automated my entire posting workflow.", "words": 6},
    {"slide_number": 2, "type": "content", "content": "Most creators spend 2 hours per post formatting, finding images, and uploading. I built a pipeline that does it in 30 seconds.", "words": 22},
    {"slide_number": 3, "type": "content", "content": "Step 1: Voice note into transcription. Whisper runs locally, no API costs, instant results.", "words": 14},
    {"slide_number": 4, "type": "content", "content": "Step 2: LLM analyzes transcript and writes the post using proven content formulas.", "words": 14},
    {"slide_number": 5, "type": "mermaid", "content": "graph LR\n    A[Voice Note] --> B[Whisper]\n    B --> C[LLM Analysis]\n    C --> D[Visual Gen]\n    D --> E[PDF Carousel]", "words": 12, "mermaid_image_path": None},
    {"slide_number": 6, "type": "content", "content": "Step 3: Visual classifier decides carousel or text-only. Carousel gets 5-10x more reach.", "words": 15},
    {"slide_number": 7, "type": "content", "content": "Step 4: HTML templates render to PDF. Each slide is one idea, 10-30 words. Clean, readable.", "words": 16},
    {"slide_number": 8, "type": "cta", "content": "What part of your content workflow takes the most time?", "words": 11},
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


# ===== Template Config Tests =====

class TestCarouselConfig:
    """Tests for carousel_templates/config.json."""

    def test_config_exists(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        assert os.path.exists(path)

    def test_config_valid_json(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            config = json.load(f)
        assert isinstance(config, dict)

    def test_dimensions(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            config = json.load(f)
        dims = config["dimensions"]
        assert dims["width"] == 1080
        assert dims["height"] == 1350

    def test_has_dark_purple_template(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            config = json.load(f)
        assert "dark-purple" in config["templates"]
        assert config["templates"]["dark-purple"]["file"] == "dark-purple.html"

    def test_has_light_template(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            config = json.load(f)
        assert "light" in config["templates"]
        assert config["templates"]["light"]["file"] == "light.html"

    def test_dark_purple_primary_color(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            config = json.load(f)
        colors = config["templates"]["dark-purple"]["colors"]
        assert colors["background"] == "#2D1B69"

    def test_brand_settings(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            config = json.load(f)
        assert "brand" in config
        assert "name" in config["brand"]

    def test_default_template(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            config = json.load(f)
        assert config["defaults"]["template"] == "dark-purple"

    def test_slide_range(self):
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            config = json.load(f)
        slide_range = config["defaults"]["slide_range"]
        assert slide_range["min"] == 6
        assert slide_range["max"] == 10

    def test_template_colors_configurable(self):
        """Verify both templates have configurable color keys."""
        path = os.path.join(CAROUSEL_DIR, "config.json")
        with open(path) as f:
            config = json.load(f)
        expected_color_keys = {"background", "text_primary", "text_secondary", "accent"}
        for template_name in ["dark-purple", "light"]:
            colors = config["templates"][template_name]["colors"]
            for key in expected_color_keys:
                assert key in colors, f"Missing color key '{key}' in template '{template_name}'"


# ===== Template Rendering Tests =====

class TestDarkPurpleTemplate:
    """Tests for dark-purple.html Jinja2 template rendering."""

    @pytest.fixture
    def env(self):
        return Environment(loader=FileSystemLoader(CAROUSEL_DIR))

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    @pytest.fixture
    def template_context(self, config):
        template_config = config["templates"]["dark-purple"]
        return {
            "slides": SAMPLE_SLIDES,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
        }

    def test_template_loads(self, env):
        template = env.get_template("dark-purple.html")
        assert template is not None

    def test_template_renders(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        assert len(html) > 0

    def test_renders_all_slides(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        for slide in SAMPLE_SLIDES:
            assert f'id="slide-{slide["slide_number"]}"' in html

    def test_renders_hook_slide(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        assert "slide-hook" in html
        assert SAMPLE_SLIDES[0]["content"] in html

    def test_renders_content_slides(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        assert "slide-content-type" in html

    def test_renders_mermaid_slide(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        assert "slide-mermaid" in html
        assert "Process Flow" in html

    def test_renders_cta_slide(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        assert "slide-cta" in html
        assert SAMPLE_SLIDES[-1]["content"] in html

    def test_renders_brand_name(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        assert template_context["brand"]["name"] in html

    def test_renders_slide_indicators(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        total = len(SAMPLE_SLIDES)
        assert f"1 / {total}" in html
        assert f"{total} / {total}" in html

    def test_renders_dimensions(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        assert "1080px" in html
        assert "1350px" in html

    def test_renders_colors(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        assert "#2D1B69" in html

    def test_page_breaks_between_slides(self, env, template_context):
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        # Should have N-1 page breaks for N slides
        assert html.count("page-break-after: always") == len(SAMPLE_SLIDES) - 1

    def test_content_number_rendering(self, env, template_context):
        """Content slides should have a large background number."""
        template = env.get_template("dark-purple.html")
        html = template.render(**template_context)
        assert 'class="content-number"' in html


class TestLightTemplate:
    """Tests for light.html Jinja2 template rendering."""

    @pytest.fixture
    def env(self):
        return Environment(loader=FileSystemLoader(CAROUSEL_DIR))

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    @pytest.fixture
    def template_context(self, config):
        template_config = config["templates"]["light"]
        return {
            "slides": SAMPLE_SLIDES,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
        }

    def test_template_loads(self, env):
        template = env.get_template("light.html")
        assert template is not None

    def test_template_renders(self, env, template_context):
        template = env.get_template("light.html")
        html = template.render(**template_context)
        assert len(html) > 0

    def test_renders_all_slides(self, env, template_context):
        template = env.get_template("light.html")
        html = template.render(**template_context)
        for slide in SAMPLE_SLIDES:
            assert f'id="slide-{slide["slide_number"]}"' in html

    def test_light_theme_colors(self, env, template_context):
        template = env.get_template("light.html")
        html = template.render(**template_context)
        assert "#FFFFFF" in html  # White background
        assert "#1A1A2E" in html  # Dark text

    def test_page_breaks_between_slides(self, env, template_context):
        template = env.get_template("light.html")
        html = template.render(**template_context)
        assert html.count("page-break-after: always") == len(SAMPLE_SLIDES) - 1


class TestTemplateMermaidWithImage:
    """Tests for mermaid slide with an actual image path."""

    @pytest.fixture
    def env(self):
        return Environment(loader=FileSystemLoader(CAROUSEL_DIR))

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    def test_mermaid_with_image_path(self, env, config):
        """When mermaid_image_path is set, render an img tag."""
        slides = [
            {"slide_number": 1, "type": "hook", "content": "Test hook", "words": 2},
            {"slide_number": 2, "type": "mermaid", "content": "graph LR\n  A-->B", "words": 2,
             "mermaid_image_path": "/tmp/mermaid.png"},
            {"slide_number": 3, "type": "cta", "content": "Test CTA", "words": 2},
        ]
        template_config = config["templates"]["dark-purple"]
        context = {
            "slides": slides,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
        }
        template = env.get_template("dark-purple.html")
        html = template.render(**context)
        assert '<img class="mermaid-img" src="/tmp/mermaid.png"' in html

    def test_mermaid_without_image_path(self, env, config):
        """When mermaid_image_path is None, render code as text."""
        slides = [
            {"slide_number": 1, "type": "hook", "content": "Test hook", "words": 2},
            {"slide_number": 2, "type": "mermaid", "content": "graph LR\n  A-->B", "words": 2,
             "mermaid_image_path": None},
            {"slide_number": 3, "type": "cta", "content": "Test CTA", "words": 2},
        ]
        template_config = config["templates"]["dark-purple"]
        context = {
            "slides": slides,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
        }
        template = env.get_template("dark-purple.html")
        html = template.render(**context)
        assert "graph LR" in html
        assert '<img class="mermaid-img"' not in html


class TestTemplateSummarySlide:
    """Tests for the summary slide type."""

    @pytest.fixture
    def env(self):
        return Environment(loader=FileSystemLoader(CAROUSEL_DIR))

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    def test_summary_slide_renders(self, env, config):
        slides = [
            {"slide_number": 1, "type": "hook", "content": "Test", "words": 1},
            {"slide_number": 2, "type": "summary", "content": "Key point 1. Key point 2. Key point 3.", "words": 9},
            {"slide_number": 3, "type": "cta", "content": "Follow for more", "words": 3},
        ]
        template_config = config["templates"]["dark-purple"]
        context = {
            "slides": slides,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
        }
        template = env.get_template("dark-purple.html")
        html = template.render(**context)
        assert "slide-summary" in html
        assert "Key Takeaways" in html


class TestMinimalSlideSet:
    """Test with minimum slide count (6 slides)."""

    @pytest.fixture
    def env(self):
        return Environment(loader=FileSystemLoader(CAROUSEL_DIR))

    @pytest.fixture
    def config(self):
        with open(os.path.join(CAROUSEL_DIR, "config.json")) as f:
            return json.load(f)

    def test_six_slides(self, env, config):
        slides = [
            {"slide_number": i + 1, "type": t, "content": f"Slide {i+1} content", "words": 3}
            for i, t in enumerate(["hook", "content", "content", "content", "content", "cta"])
        ]
        template_config = config["templates"]["dark-purple"]
        context = {
            "slides": slides,
            "width": config["dimensions"]["width"],
            "height": config["dimensions"]["height"],
            "colors": template_config["colors"],
            "fonts": template_config["fonts"],
            "brand": config["brand"],
        }
        template = env.get_template("dark-purple.html")
        html = template.render(**context)
        assert html.count("page-break-after: always") == 5  # 6 slides -> 5 breaks
        for i in range(1, 7):
            assert f'id="slide-{i}"' in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
