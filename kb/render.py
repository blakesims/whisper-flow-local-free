"""
KB Rendering Pipeline — HTML carousel → PDF + Mermaid diagrams.

Converts carousel slide data + Jinja2 templates into:
- Multi-page PDF (one page per slide at 1080x1350px)
- Individual slide PNGs (for posting queue thumbnails)
- Mermaid diagram SVGs (embedded inline in carousel slides)

Usage:
    from kb.render import render_carousel, render_mermaid, render_pipeline

    # Render mermaid diagram to SVG
    svg_content = render_mermaid("graph LR\\n  A-->B", "/tmp/output")

    # Render carousel slides to PDF
    pdf_path = render_carousel(slides, "brand-purple", "/tmp/output")

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
import time
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

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
    slide_number: Optional[int] = None,
) -> Optional[str]:
    """
    Render mermaid code to SVG using mmdc CLI.

    Args:
        mermaid_code: Mermaid diagram code (e.g. "graph LR\\n  A-->B")
        output_path: Directory to write the output SVG
        mmdc_path: Path to mmdc binary (auto-detected if None)
        background: Background color (default: transparent)
        theme: Mermaid theme (dark, default, forest, neutral)
        width: Output width in pixels

    Returns:
        SVG content string (ready for inline embedding), or None if rendering failed.
    """
    if mmdc_path is None:
        mmdc_path = _find_mmdc()

    if mmdc_path is None:
        logger.warning("mmdc not found. Skipping mermaid rendering.")
        return None

    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"mermaid-{slide_number}.svg" if slide_number else "mermaid.svg"
    output_file = output_dir / filename

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
            svg_content = output_file.read_text(encoding="utf-8")
            logger.info("Mermaid SVG rendered: %s (%d bytes)", output_file, len(svg_content))
            return svg_content

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


def render_mermaid_via_llm(
    mermaid_code: str,
    template_name: str = "brand-purple",
    config: Optional[dict] = None,
    model: str = "gemini-2.5-flash",
    max_retries: int = 2,
) -> Optional[str]:
    """
    Convert mermaid diagram code to branded SVG using Gemini LLM.

    Instead of calling the mmdc CLI (which produces rigid/generic output),
    this sends the mermaid code to Gemini with brand styling instructions
    and a few-shot example, returning hand-crafted-style SVG.

    Args:
        mermaid_code: Mermaid diagram code (e.g. "graph TD\\n  A-->B")
        template_name: Template name from config.json for brand colors
        config: Carousel config dict (loaded from config.json if None)
        model: Gemini model to use (flash is fine for conversion tasks)
        max_retries: Number of retries on transient failures

    Returns:
        SVG content string (ready for inline embedding), or None if generation failed.
    """
    try:
        from google import genai
        from google.genai import types, errors
    except ImportError:
        logger.warning("google-genai not installed. Cannot render mermaid via LLM.")
        return None

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("No Gemini API key found. Cannot render mermaid via LLM.")
        return None

    if config is None:
        config = load_carousel_config()

    template_config = config.get("templates", {}).get(template_name, {})
    colors = template_config.get("colors", {})
    fonts = template_config.get("fonts", {})

    # Build the prompt with brand colors and a few-shot SVG example
    prompt = f"""Convert this Mermaid diagram code into a branded SVG diagram.

MERMAID CODE:
```
{mermaid_code}
```

BRAND STYLE REQUIREMENTS:
- viewBox: use "0 0 760 H" where H = (number_of_nodes * 120) + 40. For 5 nodes that's "0 0 760 640".
- Add preserveAspectRatio="xMinYMid meet" on the <svg> element (no fixed width/height attributes)
- IMPORTANT: Space nodes generously. Each node rect is 65px tall. Place them ~120px apart (y-step). Leave 20px top margin.
- Node rectangles: rounded corners rx="10", fill="rgba(139,92,246,0.12)", stroke="{colors.get('accent', '#8B5CF6')}", stroke-width="2"
- Node text: font-family="{fonts.get('heading', 'Plus Jakarta Sans, sans-serif')}", font-size="17", font-weight="700", fill="{colors.get('text_primary', '#FFFFFF')}", text-anchor="middle"
- Annotation labels beside each node: font-size="15", fill="{colors.get('accent_light', '#A78BFA')}" for the title, font-size="13", fill="rgba(196,181,227,0.6)" for the description
- Arrow connectors between nodes: stroke="{colors.get('accent', '#8B5CF6')}", stroke-width="2", with a triangular arrowhead marker
- Define arrow marker in <defs>: <marker id="arrow-purple" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{colors.get('accent', '#8B5CF6')}"/></marker>
- Background: transparent (no background rect)
- For graph TD/TB (top-down): stack nodes vertically with ~30px gap, arrows pointing down, annotations to the right
- For graph LR (left-right): arrange nodes horizontally, arrows pointing right, annotations below
- Each annotation should describe what that step does — infer from the node labels and any edge labels

EXAMPLE OUTPUT (for a 4-node top-down flow — note 120px y-step between nodes):
<svg viewBox="0 0 760 520" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMinYMid meet">
  <defs>
    <marker id="arrow-purple" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#8B5CF6"/>
    </marker>
  </defs>

  <rect x="20" y="20" width="170" height="65" rx="10" fill="rgba(139,92,246,0.12)" stroke="#8B5CF6" stroke-width="2"/>
  <text x="105" y="60" text-anchor="middle" font-family="Plus Jakarta Sans, sans-serif" font-size="17" font-weight="700" fill="#FFFFFF">Transcribe</text>

  <rect x="20" y="140" width="170" height="65" rx="10" fill="rgba(139,92,246,0.12)" stroke="#8B5CF6" stroke-width="2"/>
  <text x="105" y="180" text-anchor="middle" font-family="Plus Jakarta Sans, sans-serif" font-size="17" font-weight="700" fill="#FFFFFF">LLM Analysis</text>

  <rect x="20" y="260" width="170" height="65" rx="10" fill="rgba(139,92,246,0.12)" stroke="#8B5CF6" stroke-width="2"/>
  <text x="105" y="300" text-anchor="middle" font-family="Plus Jakarta Sans, sans-serif" font-size="17" font-weight="700" fill="#FFFFFF">Classify</text>

  <rect x="20" y="380" width="170" height="65" rx="10" fill="rgba(139,92,246,0.12)" stroke="#8B5CF6" stroke-width="2"/>
  <text x="105" y="420" text-anchor="middle" font-family="Plus Jakarta Sans, sans-serif" font-size="17" font-weight="700" fill="#FFFFFF">Generate</text>

  <text x="225" y="48" font-family="Plus Jakarta Sans, sans-serif" font-size="15" fill="#A78BFA">Whisper API</text>
  <text x="225" y="68" font-family="Plus Jakarta Sans, sans-serif" font-size="13" fill="rgba(196,181,227,0.6)">audio -> text transcript</text>

  <text x="225" y="168" font-family="Plus Jakarta Sans, sans-serif" font-size="15" fill="#A78BFA">Claude / GPT</text>
  <text x="225" y="188" font-family="Plus Jakarta Sans, sans-serif" font-size="13" fill="rgba(196,181,227,0.6)">extract topics + insights</text>

  <text x="225" y="288" font-family="Plus Jakarta Sans, sans-serif" font-size="15" fill="#A78BFA">Content Scorer</text>
  <text x="225" y="308" font-family="Plus Jakarta Sans, sans-serif" font-size="13" fill="rgba(196,181,227,0.6)">format + template selection</text>

  <text x="225" y="408" font-family="Plus Jakarta Sans, sans-serif" font-size="15" fill="#A78BFA">Jinja2 + Playwright</text>
  <text x="225" y="428" font-family="Plus Jakarta Sans, sans-serif" font-size="13" fill="rgba(196,181,227,0.6)">HTML -> PDF carousel</text>

  <line x1="105" y1="85" x2="105" y2="140" stroke="#8B5CF6" stroke-width="2" marker-end="url(#arrow-purple)"/>
  <line x1="105" y1="205" x2="105" y2="260" stroke="#8B5CF6" stroke-width="2" marker-end="url(#arrow-purple)"/>
  <line x1="105" y1="325" x2="105" y2="380" stroke="#8B5CF6" stroke-width="2" marker-end="url(#arrow-purple)"/>
</svg>

RULES:
- Output ONLY the raw SVG. No markdown fences, no explanation, no surrounding text.
- The SVG must be valid and self-contained.
- Use the exact brand colors specified above.
- Infer meaningful annotation text for each node based on the mermaid diagram context.
- Auto-size node widths to fit the text (min 150px, max 220px).
- Keep the layout clean and well-spaced.
"""

    client = genai.Client(api_key=api_key)
    gen_config = types.GenerateContentConfig(
        temperature=0.2,
    )

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=gen_config,
            )

            svg_text = response.text.strip()

            # Strip markdown fences if the model wrapped it anyway
            if svg_text.startswith("```"):
                # Remove opening fence (```svg or ```)
                svg_text = re.sub(r"^```\w*\n?", "", svg_text)
                # Remove closing fence
                svg_text = re.sub(r"\n?```$", "", svg_text)
                svg_text = svg_text.strip()

            # Validate it looks like SVG
            if not svg_text.startswith("<svg") and "<svg" in svg_text:
                # Extract just the SVG element
                match = re.search(r"(<svg[\s\S]*?</svg>)", svg_text)
                if match:
                    svg_text = match.group(1)

            if not svg_text.startswith("<svg"):
                logger.warning(
                    "LLM mermaid response does not look like SVG (attempt %d): %.100s...",
                    attempt + 1,
                    svg_text,
                )
                if attempt < max_retries - 1:
                    continue
                return None

            logger.info(
                "Mermaid SVG generated via LLM (%d bytes, model=%s)",
                len(svg_text),
                model,
            )
            return svg_text

        except errors.ClientError as e:
            if e.code == 429:  # Rate limited
                wait_time = 2 ** attempt
                logger.warning("Rate limited, waiting %ds...", wait_time)
                time.sleep(wait_time)
                continue
            logger.warning("Gemini client error rendering mermaid: %s", e)
            return None
        except errors.ServerError as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            logger.warning("Gemini server error rendering mermaid: %s", e)
            return None
        except Exception as e:
            logger.warning("Unexpected error rendering mermaid via LLM: %s", e)
            return None

    return None


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


def _apply_emphasis(text: str) -> str:
    """Convert **word** markers to accent-colored spans in escaped text.

    Expects text that has already been HTML-escaped (so no raw < or >).
    Returns a string with <span class="accent-word"> replacements.
    """
    return re.sub(r'\*\*(.+?)\*\*', r'<span class="accent-word">\1</span>', text)


def markdown_to_html(text: str) -> Markup:
    """
    Convert markdown-style content string to HTML.

    Parses line-by-line:
    - Lines starting with '- ' or '* ' become <ul><li> bullet points
    - Lines starting with 'N. ' (e.g. '1. ', '2. ') become <ol><li> numbered lists
    - Plain text lines become <p> paragraphs with <br> for line breaks within a block
    - **word** patterns are converted to accent-colored <span> elements

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
            item_text = _apply_emphasis(str(escape(stripped[2:])))
            if current_type != "ul":
                flush()
                current_type = "ul"
            current_items.append(item_text)
        # Check for ordered list: 'N. '
        elif re.match(r"^\d+\.\s", stripped):
            item_text = _apply_emphasis(str(escape(re.sub(r"^\d+\.\s", "", stripped))))
            if current_type != "ol":
                flush()
                current_type = "ol"
            current_items.append(item_text)
        else:
            # Plain text
            if current_type != "p":
                flush()
                current_type = "p"
            current_items.append(_apply_emphasis(str(escape(stripped))))

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
    def highlight_words(text):
        """Convert **word** to <span class="accent-word">word</span>."""
        safe = str(escape(text))
        return Markup(_apply_emphasis(safe))

    env.filters["markdown_to_html"] = markdown_to_html
    env.filters["highlight_words"] = highlight_words
    template = env.get_template(template_file)

    html = template.render(
        slides=slides,
        width=dimensions["width"],
        height=dimensions["height"],
        colors=template_config["colors"],
        fonts=template_config["fonts"],
        font_sizes=template_config.get("font_sizes", {}),
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

        # Wait for web fonts to fully load
        await page.wait_for_function("document.fonts.ready.then(() => true)")
        await page.wait_for_timeout(500)

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

        # Wait for web fonts to fully load
        page.wait_for_function("document.fonts.ready.then(() => true)")
        page.wait_for_timeout(500)

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
        page.wait_for_function("document.fonts.ready.then(() => true)")
        page.wait_for_timeout(500)

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
            - mermaid_svg: str or None (raw SVG content)
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
    # Prefer LLM-generated branded SVG; fall back to mmdc CLI
    mermaid_svg = None
    if has_mermaid:
        # Select mmdc theme from template config (fallback to dark)
        template_config = config.get("templates", {}).get(template_name, {})
        mermaid_theme = template_config.get("mermaid_theme", "dark")

        for slide in slides:
            if slide.get("type") == "mermaid" and slide.get("content"):
                slide_num = slide.get("slide_number")

                # Try LLM-generated branded SVG first
                svg_content = render_mermaid_via_llm(
                    slide["content"],
                    template_name=template_name,
                    config=config,
                )

                if svg_content:
                    logger.info(
                        "Mermaid slide %s rendered via LLM", slide_num
                    )
                else:
                    # Fallback to mmdc CLI
                    logger.info(
                        "LLM mermaid failed for slide %s, falling back to mmdc",
                        slide_num,
                    )
                    mermaid_out_dir = os.path.join(output_dir, "mermaid")
                    svg_content = render_mermaid(
                        slide["content"],
                        mermaid_out_dir,
                        theme=mermaid_theme,
                        slide_number=slide_num,
                    )

                if svg_content:
                    # Embed SVG inline via Markup() — trusted source (LLM or mmdc output)
                    slide["mermaid_svg"] = Markup(svg_content)
                    mermaid_svg = svg_content
                else:
                    errors.append(
                        f"Mermaid render failed for slide {slide_num}. "
                        "Slide will show raw code instead."
                    )
                    logger.warning(
                        "Mermaid render failed for slide %s (both LLM and mmdc)",
                        slide_num,
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
            "mermaid_svg": mermaid_svg,
            "html": None,
            "errors": errors + [f"Carousel render failed: {e}"],
        }

    # Step 3: Save HTML to disk for inspection
    html_content = carousel_result["html"]
    if html_content:
        html_path = os.path.join(output_dir, "carousel.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info("HTML saved: %s", html_path)

    return {
        "pdf_path": carousel_result["pdf_path"],
        "thumbnail_paths": carousel_result["thumbnail_paths"],
        "mermaid_svg": mermaid_svg,
        "html": html_content,
        "errors": errors,
    }
