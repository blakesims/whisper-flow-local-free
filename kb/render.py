"""
KB Rendering Pipeline — HTML carousel → PDF + Mermaid diagrams.

Converts carousel slide data + Jinja2 templates into:
- Multi-page PDF (one page per slide at 1080x1350px)
- Individual slide PNGs (for posting queue thumbnails)
- Mermaid diagram PNGs (embedded in carousel slides)

Usage:
    from kb.render import render_carousel, render_mermaid, render_pipeline

    # Render mermaid diagram to PNG
    png_path = render_mermaid("graph LR\\n  A-->B", "/tmp/output")

    # Render carousel slides to PDF
    pdf_path = render_carousel(slides, "dark-purple", "/tmp/output")

    # Full pipeline: mermaid + carousel → PDF + thumbnails
    result = render_pipeline(decimal, analysis_results, config)
"""

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

logger = logging.getLogger(__name__)

# Paths
CAROUSEL_TEMPLATES_DIR = Path(__file__).parent / "carousel_templates"
CAROUSEL_CONFIG_PATH = CAROUSEL_TEMPLATES_DIR / "config.json"

# mmdc binary — check common locations
MMDC_PATHS = [
    os.path.expanduser("~/.npm-global/bin/mmdc"),
    "/usr/local/bin/mmdc",
    shutil.which("mmdc") or "",
]


def _find_mmdc() -> Optional[str]:
    """Find the mmdc (mermaid CLI) binary."""
    for path in MMDC_PATHS:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def load_carousel_config() -> dict:
    """Load carousel template configuration from config.json."""
    if not CAROUSEL_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Carousel config not found: {CAROUSEL_CONFIG_PATH}"
        )
    with open(CAROUSEL_CONFIG_PATH) as f:
        return json.load(f)


def render_mermaid(
    mermaid_code: str,
    output_path: str,
    mmdc_path: Optional[str] = None,
    background: str = "transparent",
    theme: str = "dark",
    width: int = 860,
) -> Optional[str]:
    """
    Render mermaid code to PNG using mmdc CLI.

    Args:
        mermaid_code: Mermaid diagram code (e.g. "graph LR\\n  A-->B")
        output_path: Directory to write the output PNG
        mmdc_path: Path to mmdc binary (auto-detected if None)
        background: Background color (default: transparent)
        theme: Mermaid theme (dark, default, forest, neutral)
        width: Output width in pixels

    Returns:
        Path to generated PNG, or None if rendering failed.
    """
    if mmdc_path is None:
        mmdc_path = _find_mmdc()

    if mmdc_path is None:
        logger.warning("mmdc not found. Skipping mermaid rendering.")
        return None

    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "mermaid.png"

    # Write mermaid code to temp file
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".mmd", delete=False
        ) as tmp:
            tmp.write(mermaid_code)
            tmp_path = tmp.name

        cmd = [
            mmdc_path,
            "-i", tmp_path,
            "-o", str(output_file),
            "-b", background,
            "-t", theme,
            "-w", str(width),
            "--quiet",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.warning(
                "mmdc failed (exit %d): %s",
                result.returncode,
                result.stderr.strip(),
            )
            return None

        if output_file.exists() and output_file.stat().st_size > 0:
            logger.info("Mermaid rendered: %s", output_file)
            return str(output_file)

        logger.warning("mmdc produced no output file")
        return None

    except subprocess.TimeoutExpired:
        logger.warning("mmdc timed out after 30s")
        return None
    except Exception as e:
        logger.warning("mmdc error: %s", e)
        return None
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except (OSError, UnboundLocalError):
            pass


def load_profile_photo_base64(config: Optional[dict] = None) -> Optional[str]:
    """
    Load profile photo from configured path and return as base64 data URI.

    Falls back to None if the file doesn't exist (template should render
    a placeholder with initials instead).

    Args:
        config: Carousel config dict (loaded from config.json if None)

    Returns:
        Base64 data URI string (e.g. "data:image/png;base64,...") or None.
    """
    if config is None:
        config = load_carousel_config()

    brand = config.get("brand", {})
    photo_path_str = brand.get("profile_photo_path")
    if not photo_path_str:
        return None

    # Resolve relative to carousel_templates dir
    photo_path = CAROUSEL_TEMPLATES_DIR / photo_path_str
    if not photo_path.exists():
        logger.info(
            "Profile photo not found at %s — template will use placeholder.",
            photo_path,
        )
        return None

    try:
        with open(photo_path, "rb") as f:
            photo_bytes = f.read()

        # Detect MIME type from extension
        ext = photo_path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(ext, "image/png")

        encoded = base64.b64encode(photo_bytes).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
    except (IOError, OSError) as e:
        logger.warning("Could not read profile photo: %s", e)
        return None


def markdown_to_html(text: str) -> Markup:
    """
    Convert markdown-style content string to HTML.

    Parses line-by-line:
    - Lines starting with '- ' or '* ' become <ul><li> bullet points
    - Lines starting with 'N. ' (e.g. '1. ', '2. ') become <ol><li> numbered lists
    - Plain text lines become <p> paragraphs with <br> for line breaks within a block

    Adjacent lines of the same type are grouped into the same list element.
    Returns Markup (safe HTML) for direct injection into Jinja2 templates.

    Args:
        text: Content string with optional markdown formatting.

    Returns:
        Markup-wrapped HTML string.
    """
    if not text:
        return Markup("")

    lines = text.split("\n")
    html_parts = []
    current_type = None  # 'ul', 'ol', or 'p'
    current_items = []

    def flush():
        nonlocal current_type, current_items
        if not current_items:
            return
        if current_type == "ul":
            items = "".join(f"<li>{item}</li>" for item in current_items)
            html_parts.append(f"<ul>{items}</ul>")
        elif current_type == "ol":
            items = "".join(f"<li>{item}</li>" for item in current_items)
            html_parts.append(f"<ol>{items}</ol>")
        elif current_type == "p":
            html_parts.append(f"<p>{'<br>'.join(current_items)}</p>")
        current_type = None
        current_items = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue

        # Check for unordered list: '- ' or '* '
        if stripped.startswith("- ") or stripped.startswith("* "):
            item_text = stripped[2:]
            if current_type != "ul":
                flush()
                current_type = "ul"
            current_items.append(item_text)
        # Check for ordered list: 'N. '
        elif re.match(r"^\d+\.\s", stripped):
            item_text = re.sub(r"^\d+\.\s", "", stripped)
            if current_type != "ol":
                flush()
                current_type = "ol"
            current_items.append(item_text)
        else:
            # Plain text
            if current_type != "p":
                flush()
                current_type = "p"
            current_items.append(stripped)

    flush()
    return Markup("".join(html_parts))


def render_html_from_slides(
    slides: list[dict],
    template_name: str = "brand-purple",
    config: Optional[dict] = None,
) -> str:
    """
    Render carousel slides to HTML string using Jinja2 template.

    Args:
        slides: List of slide dicts with {slide_number, type, content, words, ...}
        template_name: Template name from config.json (e.g. "brand-purple",
                       "modern-editorial", "tech-minimal")
        config: Carousel config dict (loaded from config.json if None)

    Returns:
        Rendered HTML string.

    Raises:
        FileNotFoundError: If template file doesn't exist.
        KeyError: If template_name not found in config.
    """
    if config is None:
        config = load_carousel_config()

    templates = config.get("templates", {})
    if template_name not in templates:
        raise KeyError(
            f"Template '{template_name}' not found. "
            f"Available: {list(templates.keys())}"
        )

    template_config = templates[template_name]
    template_file = template_config["file"]
    dimensions = config.get("dimensions", {"width": 1080, "height": 1350})
    brand = config.get("brand", {})
    header = config.get("header", {
        "show_on_all_slides": True,
        "author_position": "left",
        "community_position": "right",
    })

    # Backward compatibility: brand.name -> brand.author_name
    if "author_name" not in brand and "name" in brand:
        brand["author_name"] = brand["name"]
    if "community_name" not in brand:
        brand["community_name"] = ""

    # Load profile photo as base64 data URI
    profile_photo_data = load_profile_photo_base64(config)

    # Verify template file exists
    template_path = CAROUSEL_TEMPLATES_DIR / template_file
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")

    env = Environment(
        loader=FileSystemLoader(str(CAROUSEL_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["markdown_to_html"] = markdown_to_html
    template = env.get_template(template_file)

    html = template.render(
        slides=slides,
        width=dimensions["width"],
        height=dimensions["height"],
        colors=template_config["colors"],
        fonts=template_config["fonts"],
        brand=brand,
        header=header,
        profile_photo_data=profile_photo_data,
    )

    return html


async def _render_html_to_pdf_async(
    html_content: str,
    output_path: str,
    width: int = 1080,
    height: int = 1350,
) -> str:
    """
    Render HTML to PDF using Playwright (async).

    Args:
        html_content: Full HTML string to render
        output_path: Path for the output PDF file
        width: Viewport width
        height: Viewport height

    Returns:
        Path to generated PDF.
    """
    from playwright.async_api import async_playwright

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": width, "height": height}
        )
        await page.set_content(html_content, wait_until="networkidle")

        # Wait for fonts to load
        await page.wait_for_timeout(1000)

        await page.pdf(
            path=str(output_file),
            width=f"{width}px",
            height=f"{height}px",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )

        await browser.close()

    logger.info("PDF rendered: %s", output_file)
    return str(output_file)


def render_html_to_pdf(
    html_content: str,
    output_path: str,
    width: int = 1080,
    height: int = 1350,
) -> str:
    """
    Render HTML to PDF using Playwright (sync wrapper).

    Args:
        html_content: Full HTML string to render
        output_path: Path for the output PDF file
        width: Viewport width
        height: Viewport height

    Returns:
        Path to generated PDF.
    """
    from playwright.sync_api import sync_playwright

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": height}
        )
        page.set_content(html_content, wait_until="networkidle")

        # Wait for fonts to load
        page.wait_for_timeout(1000)

        page.pdf(
            path=str(output_file),
            width=f"{width}px",
            height=f"{height}px",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )

        browser.close()

    logger.info("PDF rendered: %s", output_file)
    return str(output_file)


def render_slide_thumbnails(
    html_content: str,
    output_dir: str,
    slide_count: int,
    width: int = 1080,
    height: int = 1350,
) -> list[str]:
    """
    Render individual slide PNGs from carousel HTML.

    Uses Playwright to screenshot each slide element.

    Args:
        html_content: Full carousel HTML
        output_dir: Directory for output PNGs
        slide_count: Number of slides to capture
        width: Slide width
        height: Slide height

    Returns:
        List of paths to generated PNG files.
    """
    from playwright.sync_api import sync_playwright

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": height}
        )
        page.set_content(html_content, wait_until="networkidle")
        page.wait_for_timeout(1000)

        for i in range(1, slide_count + 1):
            slide_el = page.query_selector(f"#slide-{i}")
            if slide_el:
                png_path = out / f"slide-{i}.png"
                slide_el.screenshot(path=str(png_path))
                paths.append(str(png_path))
                logger.info("Thumbnail: %s", png_path)

        browser.close()

    return paths


def render_carousel(
    slides: list[dict],
    template_name: str = "brand-purple",
    output_dir: str = ".",
    config: Optional[dict] = None,
    generate_thumbnails: bool = True,
) -> dict:
    """
    Full carousel render: slides → HTML → PDF + thumbnails.

    Args:
        slides: List of slide dicts
        template_name: Template name from config.json
        output_dir: Directory for output files
        config: Carousel config (auto-loaded if None)
        generate_thumbnails: Whether to generate per-slide PNGs

    Returns:
        Dict with keys: pdf_path, thumbnail_paths, html (raw HTML string)
    """
    if config is None:
        config = load_carousel_config()

    dimensions = config.get("dimensions", {"width": 1080, "height": 1350})
    width = dimensions["width"]
    height = dimensions["height"]

    # Step 1: Render HTML
    html = render_html_from_slides(slides, template_name, config)

    # Step 2: HTML → PDF
    pdf_path = render_html_to_pdf(
        html,
        os.path.join(output_dir, "carousel.pdf"),
        width=width,
        height=height,
    )

    result = {
        "pdf_path": pdf_path,
        "thumbnail_paths": [],
        "html": html,
    }

    # Step 3: Generate thumbnails
    if generate_thumbnails:
        result["thumbnail_paths"] = render_slide_thumbnails(
            html, output_dir, len(slides), width=width, height=height
        )

    return result


def render_pipeline(
    slides_data: dict,
    output_dir: str,
    template_name: Optional[str] = None,
    config: Optional[dict] = None,
) -> dict:
    """
    Full rendering pipeline: process mermaid → render carousel → PDF + thumbnails.

    This is the main entry point for the rendering engine.

    Args:
        slides_data: Carousel slides JSON output from LLM. Expected structure:
            {
                "slides": [{slide_number, type, content, words, ...}],
                "total_slides": N,
                "has_mermaid": bool
            }
        output_dir: Directory for all output files
        template_name: Template name (defaults to config default)
        config: Carousel config (auto-loaded if None)

    Returns:
        Dict with:
            - pdf_path: str
            - thumbnail_paths: list[str]
            - mermaid_path: str or None
            - html: str
            - errors: list[str]
    """
    if config is None:
        config = load_carousel_config()

    if template_name is None:
        template_name = config.get("defaults", {}).get("template", "brand-purple")

    slides = slides_data.get("slides", [])
    has_mermaid = slides_data.get("has_mermaid", False)
    errors = []

    # Step 1: Render mermaid diagrams if needed
    mermaid_path = None
    if has_mermaid:
        for slide in slides:
            if slide.get("type") == "mermaid" and slide.get("content"):
                mermaid_out_dir = os.path.join(output_dir, "mermaid")
                mermaid_path = render_mermaid(
                    slide["content"],
                    mermaid_out_dir,
                )
                if mermaid_path:
                    # Convert local file path to base64 data URI for Playwright
                    # (Chromium security blocks local file:// paths in set_content)
                    try:
                        with open(mermaid_path, "rb") as img_f:
                            img_data = base64.b64encode(img_f.read()).decode("ascii")
                        slide["mermaid_image_path"] = f"data:image/png;base64,{img_data}"
                    except (IOError, OSError) as read_err:
                        logger.warning("Could not read mermaid PNG for base64: %s", read_err)
                        slide["mermaid_image_path"] = mermaid_path
                else:
                    errors.append(
                        f"Mermaid render failed for slide {slide.get('slide_number')}. "
                        "Slide will show raw code instead."
                    )
                    logger.warning(
                        "Mermaid render failed for slide %s",
                        slide.get("slide_number"),
                    )

    # Step 2: Render carousel
    try:
        carousel_result = render_carousel(
            slides,
            template_name=template_name,
            output_dir=output_dir,
            config=config,
            generate_thumbnails=True,
        )
    except Exception as e:
        logger.error("Carousel render failed: %s", e)
        return {
            "pdf_path": None,
            "thumbnail_paths": [],
            "mermaid_path": mermaid_path,
            "html": None,
            "errors": errors + [f"Carousel render failed: {e}"],
        }

    return {
        "pdf_path": carousel_result["pdf_path"],
        "thumbnail_paths": carousel_result["thumbnail_paths"],
        "mermaid_path": mermaid_path,
        "html": carousel_result["html"],
        "errors": errors,
    }
