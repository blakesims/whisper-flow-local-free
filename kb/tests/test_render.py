"""
Tests for Phase 3: Rendering Pipeline (HTML -> PDF + Mermaid).

Tests:
- HTML generation from template + slide data
- Mermaid rendering (mock mmdc CLI)
- PDF generation (mock Playwright)
- Slide thumbnail generation (mock Playwright)
- Full render_pipeline orchestration
- Error handling (missing template, failed mermaid, etc.)
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from kb.render import (
    _find_mmdc,
    load_carousel_config,
    render_html_from_slides,
    render_mermaid,
    render_html_to_pdf,
    render_slide_thumbnails,
    render_carousel,
    render_pipeline,
    CAROUSEL_TEMPLATES_DIR,
    CAROUSEL_CONFIG_PATH,
)


# ===== Sample Data =====

SAMPLE_SLIDES = [
    {"slide_number": 1, "type": "hook", "content": "I automated my entire posting workflow.", "words": 6},
    {"slide_number": 2, "type": "content", "content": "Most creators spend 2 hours per post.", "words": 8},
    {"slide_number": 3, "type": "content", "content": "Step 1: Voice note into transcription.", "words": 6},
    {"slide_number": 4, "type": "mermaid", "content": "graph LR\n  A-->B-->C", "words": 5, "mermaid_image_path": None},
    {"slide_number": 5, "type": "content", "content": "Step 2: LLM writes the post.", "words": 6},
    {"slide_number": 6, "type": "cta", "content": "What takes you the most time?", "words": 7},
]

SAMPLE_SLIDES_DATA = {
    "slides": SAMPLE_SLIDES,
    "total_slides": 6,
    "has_mermaid": True,
}

SAMPLE_SLIDES_NO_MERMAID = {
    "slides": [
        {"slide_number": 1, "type": "hook", "content": "Hook text", "words": 2},
        {"slide_number": 2, "type": "content", "content": "Content text", "words": 2},
        {"slide_number": 3, "type": "cta", "content": "CTA text", "words": 2},
    ],
    "total_slides": 3,
    "has_mermaid": False,
}


# ===== Config Tests =====

class TestLoadCarouselConfig:
    """Tests for loading carousel configuration."""

    def test_config_file_exists(self):
        assert CAROUSEL_CONFIG_PATH.exists(), f"Config not found at {CAROUSEL_CONFIG_PATH}"

    def test_config_loads_valid_json(self):
        config = load_carousel_config()
        assert isinstance(config, dict)

    def test_config_has_dimensions(self):
        config = load_carousel_config()
        assert "dimensions" in config
        assert config["dimensions"]["width"] == 1080
        assert config["dimensions"]["height"] == 1350

    def test_config_has_templates(self):
        config = load_carousel_config()
        assert "templates" in config
        assert "brand-purple" in config["templates"]
        assert "modern-editorial" in config["templates"]
        assert "tech-minimal" in config["templates"]

    def test_config_has_defaults(self):
        config = load_carousel_config()
        assert "defaults" in config
        assert config["defaults"]["template"] == "brand-purple"

    def test_config_has_brand(self):
        config = load_carousel_config()
        assert "brand" in config
        assert "author_name" in config["brand"]


# ===== HTML Generation Tests =====

class TestRenderHtmlFromSlides:
    """Tests for Jinja2 HTML rendering."""

    def test_renders_brand_purple_template(self):
        html = render_html_from_slides(SAMPLE_SLIDES, "brand-purple")
        assert "<!DOCTYPE html>" in html
        assert "1080" in html

    def test_renders_modern_editorial_template(self):
        html = render_html_from_slides(SAMPLE_SLIDES, "modern-editorial")
        assert "<!DOCTYPE html>" in html

    def test_renders_tech_minimal_template(self):
        html = render_html_from_slides(SAMPLE_SLIDES, "tech-minimal")
        assert "<!DOCTYPE html>" in html

    def test_renders_all_slides(self):
        html = render_html_from_slides(SAMPLE_SLIDES, "brand-purple")
        for slide in SAMPLE_SLIDES:
            assert f'id="slide-{slide["slide_number"]}"' in html

    def test_hook_slide_content(self):
        html = render_html_from_slides(SAMPLE_SLIDES, "brand-purple")
        assert "I automated my entire posting workflow." in html
        assert "title-page-main-title" in html

    def test_content_slide_renders(self):
        html = render_html_from_slides(SAMPLE_SLIDES, "brand-purple")
        # Content slides should have slide content
        assert "Most creators spend 2 hours per post." in html

    def test_mermaid_slide_without_image(self):
        html = render_html_from_slides(SAMPLE_SLIDES, "brand-purple")
        # Without mermaid_image_path, should show raw code
        assert "graph LR" in html

    def test_mermaid_slide_with_image(self):
        slides = [dict(s) for s in SAMPLE_SLIDES]
        slides[3]["mermaid_image_path"] = "data:image/png;base64,abc123"
        html = render_html_from_slides(slides, "brand-purple")
        assert 'src="data:image/png;base64,abc123"' in html

    def test_cta_slide_content(self):
        html = render_html_from_slides(SAMPLE_SLIDES, "brand-purple")
        assert "cta-heading" in html
        assert "What takes you the most time?" in html

    def test_brand_in_header(self):
        html = render_html_from_slides(SAMPLE_SLIDES, "brand-purple")
        assert "Blake Sims" in html

    def test_page_breaks_between_slides(self):
        html = render_html_from_slides(SAMPLE_SLIDES, "brand-purple")
        assert "page-break-after: always" in html

    def test_invalid_template_name_raises(self):
        with pytest.raises(KeyError, match="nonexistent"):
            render_html_from_slides(SAMPLE_SLIDES, "nonexistent")

    def test_uses_autoescape(self):
        """Verify autoescape is active: HTML in content is escaped."""
        slides = [{"slide_number": 1, "type": "hook", "content": "<script>alert('xss')</script>", "words": 1}]
        html = render_html_from_slides(slides, "brand-purple")
        # Script tags in content should be escaped
        assert "&lt;script&gt;" in html

    def test_custom_config_override(self):
        config = load_carousel_config()
        config["dimensions"]["width"] = 800
        config["dimensions"]["height"] = 600
        html = render_html_from_slides(SAMPLE_SLIDES[:1], "brand-purple", config=config)
        assert "800px" in html
        assert "600px" in html

    def test_empty_slides_list(self):
        html = render_html_from_slides([], "brand-purple")
        assert "<!DOCTYPE html>" in html
        # Should not have any slide divs
        assert 'id="slide-' not in html


# ===== Mermaid Rendering Tests =====

class TestRenderMermaid:
    """Tests for mmdc mermaid rendering."""

    def test_returns_none_when_mmdc_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_mermaid(
                "graph LR\n  A-->B",
                tmpdir,
                mmdc_path="/nonexistent/mmdc",
            )
            assert result is None

    @patch("kb.render.subprocess.run")
    def test_successful_render(self, mock_run):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock mmdc success: create the output file
            def side_effect(*args, **kwargs):
                output_file = Path(tmpdir) / "mermaid.png"
                output_file.write_bytes(b"fake png data")
                return MagicMock(returncode=0, stderr="")

            mock_run.side_effect = side_effect

            result = render_mermaid(
                "graph LR\n  A-->B",
                tmpdir,
                mmdc_path="/usr/bin/true",
            )
            assert result is not None
            assert result.endswith("mermaid.png")

    @patch("kb.render.subprocess.run")
    def test_failed_render_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="Syntax error")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_mermaid(
                "invalid mermaid code",
                tmpdir,
                mmdc_path="/usr/bin/true",
            )
            assert result is None

    @patch("kb.render.subprocess.run")
    def test_timeout_returns_none(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="mmdc", timeout=30)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_mermaid(
                "graph LR\n  A-->B",
                tmpdir,
                mmdc_path="/usr/bin/true",
            )
            assert result is None

    @patch("kb.render.subprocess.run")
    def test_creates_output_directory(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "nested", "dir")
            render_mermaid(
                "graph LR\n  A-->B",
                nested,
                mmdc_path="/usr/bin/true",
            )
            assert os.path.isdir(nested)

    @patch("kb.render.subprocess.run")
    def test_passes_correct_args_to_mmdc(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            render_mermaid(
                "graph LR\n  A-->B",
                tmpdir,
                mmdc_path="/fake/mmdc",
                background="#000",
                theme="forest",
                width=500,
            )

            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert cmd[0] == "/fake/mmdc"
            assert "-b" in cmd
            assert "#000" in cmd
            assert "-t" in cmd
            assert "forest" in cmd
            assert "-w" in cmd
            assert "500" in cmd

    def test_auto_detects_mmdc(self):
        """_find_mmdc should return a path if mmdc exists."""
        result = _find_mmdc()
        # On the server, mmdc should be found at ~/.npm-global/bin/mmdc
        # Don't fail if not found — just test it returns str or None
        assert result is None or isinstance(result, str)


# ===== PDF Rendering Tests (Mocked Playwright) =====

def _mock_playwright_context():
    """Helper to create a mock Playwright context manager."""
    mock_page = MagicMock()
    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_context = MagicMock()
    mock_context.chromium.launch.return_value = mock_browser

    mock_pw = MagicMock()
    mock_pw.__enter__ = MagicMock(return_value=mock_context)
    mock_pw.__exit__ = MagicMock(return_value=False)

    return mock_pw, mock_browser, mock_page


class TestRenderHtmlToPdf:
    """Tests for Playwright PDF rendering (mocked)."""

    @patch("playwright.sync_api.sync_playwright")
    def test_creates_output_directory(self, mock_pw_cls):
        mock_pw, mock_browser, mock_page = _mock_playwright_context()
        mock_pw_cls.return_value = mock_pw

        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "nested", "carousel.pdf")
            render_html_to_pdf("<html>test</html>", output)
            assert os.path.isdir(os.path.join(tmpdir, "nested"))

    @patch("playwright.sync_api.sync_playwright")
    def test_calls_pdf_with_correct_dimensions(self, mock_pw_cls):
        mock_pw, mock_browser, mock_page = _mock_playwright_context()
        mock_pw_cls.return_value = mock_pw

        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "carousel.pdf")
            render_html_to_pdf("<html>test</html>", output, width=1080, height=1350)

            mock_page.pdf.assert_called_once()
            call_kwargs = mock_page.pdf.call_args[1]
            assert call_kwargs["width"] == "1080px"
            assert call_kwargs["height"] == "1350px"
            assert call_kwargs["print_background"] is True

    @patch("playwright.sync_api.sync_playwright")
    def test_sets_content_and_waits(self, mock_pw_cls):
        mock_pw, mock_browser, mock_page = _mock_playwright_context()
        mock_pw_cls.return_value = mock_pw

        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "carousel.pdf")
            render_html_to_pdf("<html>hello</html>", output)

            mock_page.set_content.assert_called_once_with(
                "<html>hello</html>", wait_until="networkidle"
            )
            mock_page.wait_for_timeout.assert_called_once_with(1000)

    @patch("playwright.sync_api.sync_playwright")
    def test_closes_browser(self, mock_pw_cls):
        mock_pw, mock_browser, mock_page = _mock_playwright_context()
        mock_pw_cls.return_value = mock_pw

        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "carousel.pdf")
            render_html_to_pdf("<html>test</html>", output)
            mock_browser.close.assert_called_once()


# ===== Slide Thumbnail Tests (Mocked Playwright) =====

class TestRenderSlideThumbnails:
    """Tests for slide thumbnail PNG generation (mocked)."""

    @patch("playwright.sync_api.sync_playwright")
    def test_creates_png_per_slide(self, mock_pw_cls):
        mock_pw, mock_browser, mock_page = _mock_playwright_context()
        mock_pw_cls.return_value = mock_pw

        # Mock slide elements
        mock_el = MagicMock()
        mock_page.query_selector.return_value = mock_el

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = render_slide_thumbnails("<html>test</html>", tmpdir, 3)
            assert len(paths) == 3
            assert all("slide-" in p for p in paths)

    @patch("playwright.sync_api.sync_playwright")
    def test_skips_missing_slides(self, mock_pw_cls):
        mock_pw, mock_browser, mock_page = _mock_playwright_context()
        mock_pw_cls.return_value = mock_pw

        # First slide found, second not found
        mock_el = MagicMock()
        mock_page.query_selector.side_effect = [mock_el, None, mock_el]

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = render_slide_thumbnails("<html>test</html>", tmpdir, 3)
            assert len(paths) == 2


# ===== Carousel Render Tests =====

class TestRenderCarousel:
    """Tests for the full carousel render function."""

    @patch("kb.render.render_slide_thumbnails")
    @patch("kb.render.render_html_to_pdf")
    def test_returns_result_dict(self, mock_pdf, mock_thumbs):
        mock_pdf.return_value = "/tmp/carousel.pdf"
        mock_thumbs.return_value = ["/tmp/slide-1.png", "/tmp/slide-2.png"]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_carousel(SAMPLE_SLIDES, "brand-purple", tmpdir)

            assert "pdf_path" in result
            assert "thumbnail_paths" in result
            assert "html" in result
            assert result["pdf_path"] == "/tmp/carousel.pdf"
            assert len(result["thumbnail_paths"]) == 2

    @patch("kb.render.render_slide_thumbnails")
    @patch("kb.render.render_html_to_pdf")
    def test_generates_html(self, mock_pdf, mock_thumbs):
        mock_pdf.return_value = "/tmp/carousel.pdf"
        mock_thumbs.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_carousel(SAMPLE_SLIDES, "brand-purple", tmpdir)
            assert "<!DOCTYPE html>" in result["html"]

    @patch("kb.render.render_slide_thumbnails")
    @patch("kb.render.render_html_to_pdf")
    def test_skips_thumbnails_when_disabled(self, mock_pdf, mock_thumbs):
        mock_pdf.return_value = "/tmp/carousel.pdf"

        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_carousel(
                SAMPLE_SLIDES, "brand-purple", tmpdir,
                generate_thumbnails=False,
            )
            mock_thumbs.assert_not_called()
            assert result["thumbnail_paths"] == []


# ===== Pipeline Tests =====

class TestRenderPipeline:
    """Tests for the full rendering pipeline orchestration."""

    @patch("kb.render.render_carousel")
    @patch("kb.render.render_mermaid")
    def test_full_pipeline_with_mermaid(self, mock_mermaid, mock_carousel):
        mock_mermaid.return_value = "/tmp/mermaid.png"
        mock_carousel.return_value = {
            "pdf_path": "/tmp/carousel.pdf",
            "thumbnail_paths": ["/tmp/slide-1.png"],
            "html": "<html>rendered</html>",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_pipeline(SAMPLE_SLIDES_DATA, tmpdir)

            assert result["pdf_path"] == "/tmp/carousel.pdf"
            assert result["mermaid_path"] == "/tmp/mermaid.png"
            assert len(result["errors"]) == 0

    @patch("kb.render.render_carousel")
    @patch("kb.render.render_mermaid")
    def test_pipeline_without_mermaid(self, mock_mermaid, mock_carousel):
        mock_carousel.return_value = {
            "pdf_path": "/tmp/carousel.pdf",
            "thumbnail_paths": [],
            "html": "<html>rendered</html>",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_pipeline(SAMPLE_SLIDES_NO_MERMAID, tmpdir)

            mock_mermaid.assert_not_called()
            assert result["mermaid_path"] is None
            assert len(result["errors"]) == 0

    @patch("kb.render.render_carousel")
    @patch("kb.render.render_mermaid")
    def test_pipeline_mermaid_failure_logs_warning(self, mock_mermaid, mock_carousel):
        """Failed mermaid should not block carousel — just log warning."""
        mock_mermaid.return_value = None  # Mermaid failed
        mock_carousel.return_value = {
            "pdf_path": "/tmp/carousel.pdf",
            "thumbnail_paths": [],
            "html": "<html>rendered</html>",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_pipeline(SAMPLE_SLIDES_DATA, tmpdir)

            assert result["pdf_path"] == "/tmp/carousel.pdf"
            assert result["mermaid_path"] is None
            assert len(result["errors"]) == 1
            assert "Mermaid render failed" in result["errors"][0]

    @patch("kb.render.render_carousel")
    @patch("kb.render.render_mermaid")
    def test_pipeline_carousel_failure(self, mock_mermaid, mock_carousel):
        """Carousel render failure returns error result."""
        mock_mermaid.return_value = "/tmp/mermaid.png"
        mock_carousel.side_effect = RuntimeError("Playwright crashed")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_pipeline(SAMPLE_SLIDES_DATA, tmpdir)

            assert result["pdf_path"] is None
            assert "Carousel render failed" in result["errors"][-1]

    @patch("kb.render.render_carousel")
    def test_pipeline_uses_default_template(self, mock_carousel):
        mock_carousel.return_value = {
            "pdf_path": "/tmp/carousel.pdf",
            "thumbnail_paths": [],
            "html": "<html>test</html>",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            render_pipeline(SAMPLE_SLIDES_NO_MERMAID, tmpdir)

            call_kwargs = mock_carousel.call_args[1]
            assert call_kwargs["template_name"] == "brand-purple"

    @patch("kb.render.render_carousel")
    def test_pipeline_custom_template(self, mock_carousel):
        mock_carousel.return_value = {
            "pdf_path": "/tmp/carousel.pdf",
            "thumbnail_paths": [],
            "html": "<html>test</html>",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            render_pipeline(
                SAMPLE_SLIDES_NO_MERMAID, tmpdir,
                template_name="tech-minimal",
            )

            call_kwargs = mock_carousel.call_args[1]
            assert call_kwargs["template_name"] == "tech-minimal"

    @patch("kb.render.render_carousel")
    @patch("kb.render.render_mermaid")
    def test_pipeline_embeds_mermaid_path_in_slide(self, mock_mermaid, mock_carousel):
        """Verify mermaid image path gets set on the slide data."""
        mock_mermaid.return_value = "/tmp/mermaid/mermaid.png"
        mock_carousel.return_value = {
            "pdf_path": "/tmp/carousel.pdf",
            "thumbnail_paths": [],
            "html": "<html>test</html>",
        }

        # Deep copy slides data so we can check mutations
        import copy
        slides_data = copy.deepcopy(SAMPLE_SLIDES_DATA)

        with tempfile.TemporaryDirectory() as tmpdir:
            render_pipeline(slides_data, tmpdir)

            # Check that the mermaid slide had its image path set
            mermaid_slide = slides_data["slides"][3]
            assert mermaid_slide["mermaid_image_path"] == "/tmp/mermaid/mermaid.png"


# ===== Publish CLI Tests =====

class TestPublishCli:
    """Tests for kb publish module."""

    def test_publish_module_imports(self):
        from kb.publish import find_renderables, render_one, main
        assert callable(find_renderables)
        assert callable(render_one)
        assert callable(main)

    def test_publish_registered_in_commands(self):
        from kb.__main__ import COMMANDS
        assert "publish" in COMMANDS
        assert COMMANDS["publish"]["module"] == "kb.publish"

    def test_find_renderables_empty_dir(self):
        from kb.publish import find_renderables
        # Should not crash on dirs without carousel_slides
        renderables = find_renderables(decimal_filter="99.99.99")
        assert isinstance(renderables, list)
        assert len(renderables) == 0

    @patch("kb.render.render_carousel")
    @patch("kb.render.render_mermaid")
    def test_render_one_dry_run(self, mock_mermaid, mock_carousel):
        from kb.publish import render_one

        renderable = {
            "title": "Test Post",
            "visuals_dir": "/tmp/test/visuals",
            "slides_data": SAMPLE_SLIDES_DATA,
        }

        result = render_one(renderable, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["slides"] == 6
        assert result["has_mermaid"] is True
        mock_carousel.assert_not_called()
        mock_mermaid.assert_not_called()
