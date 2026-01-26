#!/usr/bin/env python3
"""
KB Dashboard - Generate HTML overview of KB configuration.

Usage:
    kb dashboard          # Generate and open HTML dashboard
    kb dashboard --output # Just print path, don't open
"""

import json
import os
import sys
import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb.__main__ import load_config, get_paths, DEFAULTS, CONFIG_FILE
from kb.core import load_registry, KB_ROOT, CONFIG_DIR


def get_analysis_types() -> list[dict]:
    """Load all analysis type definitions."""
    analysis_dir = CONFIG_DIR / "analysis_types"
    analyses = []

    if analysis_dir.exists():
        for f in sorted(analysis_dir.glob("*.json")):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    analyses.append({
                        "name": data.get("name", f.stem),
                        "description": data.get("description", ""),
                        "prompt": data.get("prompt", ""),
                        "file": str(f),
                    })
            except Exception as e:
                analyses.append({
                    "name": f.stem,
                    "description": f"Error loading: {e}",
                    "prompt": "",
                    "file": str(f),
                })

    return analyses


def generate_html() -> str:
    """Generate the dashboard HTML."""
    config = load_config()
    registry = load_registry()
    analyses = get_analysis_types()

    decimals = registry.get("decimals", {})
    tags = registry.get("tags", [])
    presets = config.get("presets", {})
    zoom_config = config.get("zoom", {})
    defaults = config.get("defaults", {})

    # Count stats
    transcribed_files = len(registry.get("transcribed_files", []))
    transcribed_zoom = len(registry.get("transcribed_zoom_meetings", []))

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KB Dashboard</title>
    <style>
        :root {{
            --bg-primary: #1a1b26;
            --bg-secondary: #24283b;
            --bg-card: #1f2335;
            --text-primary: #c0caf5;
            --text-secondary: #565f89;
            --text-muted: #414868;
            --accent-cyan: #7dcfff;
            --accent-blue: #7aa2f7;
            --accent-green: #9ece6a;
            --accent-yellow: #e0af68;
            --accent-magenta: #bb9af7;
            --accent-red: #f7768e;
            --border: #3b4261;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 2rem;
            max-width: 1400px;
            margin: 0 auto;
        }}

        h1 {{
            color: var(--accent-cyan);
            font-size: 1.8rem;
            margin-bottom: 0.5rem;
            font-weight: 600;
        }}

        .subtitle {{
            color: var(--text-secondary);
            margin-bottom: 2rem;
            font-size: 0.9rem;
        }}

        .stats {{
            display: flex;
            gap: 1rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
        }}

        .stat {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem 1.5rem;
            min-width: 140px;
        }}

        .stat-value {{
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--accent-blue);
        }}

        .stat-label {{
            color: var(--text-secondary);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .section {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin-bottom: 1.5rem;
            overflow: hidden;
        }}

        .section-header {{
            background: var(--bg-secondary);
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }}

        .section-header:hover {{
            background: #2a2f45;
        }}

        .section-title {{
            color: var(--accent-cyan);
            font-size: 1rem;
            font-weight: 600;
        }}

        .section-badge {{
            background: var(--bg-primary);
            color: var(--text-secondary);
            padding: 0.25rem 0.75rem;
            border-radius: 12px;
            font-size: 0.75rem;
        }}

        .section-content {{
            padding: 1.5rem;
        }}

        .flow-diagram {{
            display: flex;
            align-items: flex-start;
            gap: 2rem;
            overflow-x: auto;
            padding: 1rem 0;
        }}

        .flow-column {{
            min-width: 200px;
        }}

        .flow-column-title {{
            color: var(--text-secondary);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.75rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }}

        .flow-item {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
            margin-bottom: 0.5rem;
            font-size: 0.85rem;
        }}

        .flow-item.source {{
            border-left: 3px solid var(--accent-green);
        }}

        .flow-item.preset {{
            border-left: 3px solid var(--accent-blue);
        }}

        .flow-item.decimal {{
            border-left: 3px solid var(--accent-yellow);
        }}

        .flow-item.analysis {{
            border-left: 3px solid var(--accent-magenta);
        }}

        .flow-arrow {{
            color: var(--text-muted);
            font-size: 1.5rem;
            align-self: center;
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1rem;
        }}

        .card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 1rem;
        }}

        .card-title {{
            color: var(--accent-green);
            font-weight: 600;
            margin-bottom: 0.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .card-subtitle {{
            color: var(--text-secondary);
            font-size: 0.8rem;
            margin-bottom: 0.75rem;
        }}

        .card-detail {{
            font-size: 0.85rem;
            margin-bottom: 0.25rem;
        }}

        .card-detail-label {{
            color: var(--text-secondary);
        }}

        .tag {{
            display: inline-block;
            background: var(--bg-primary);
            color: var(--accent-cyan);
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            margin: 0.15rem;
        }}

        .tag.source {{
            color: var(--accent-green);
        }}

        .decimal-code {{
            color: var(--accent-yellow);
            font-weight: 600;
        }}

        .prompt-preview {{
            background: var(--bg-primary);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 0.75rem;
            font-size: 0.8rem;
            color: var(--text-secondary);
            max-height: 100px;
            overflow-y: auto;
            white-space: pre-wrap;
            margin-top: 0.5rem;
        }}

        .prompt-full {{
            display: none;
            background: var(--bg-primary);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 1rem;
            font-size: 0.8rem;
            color: var(--text-primary);
            white-space: pre-wrap;
            margin-top: 0.5rem;
            max-height: 300px;
            overflow-y: auto;
        }}

        .expand-btn {{
            background: var(--bg-primary);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.75rem;
        }}

        .expand-btn:hover {{
            background: var(--bg-secondary);
            color: var(--text-primary);
        }}

        .config-path {{
            color: var(--text-muted);
            font-size: 0.75rem;
            margin-top: 0.5rem;
        }}

        .ignore-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}

        .ignore-item {{
            background: var(--bg-primary);
            border: 1px solid var(--accent-red);
            color: var(--accent-red);
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.85rem;
        }}

        .two-col {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
        }}

        @media (max-width: 800px) {{
            .two-col {{
                grid-template-columns: 1fr;
            }}
        }}

        .defaults-table {{
            width: 100%;
        }}

        .defaults-table td {{
            padding: 0.5rem 0;
            border-bottom: 1px solid var(--border);
        }}

        .defaults-table td:first-child {{
            color: var(--text-secondary);
            width: 40%;
        }}

        footer {{
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
            color: var(--text-muted);
            font-size: 0.8rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <h1>KB Dashboard</h1>
    <p class="subtitle">Knowledge Base Configuration Overview</p>

    <div class="stats">
        <div class="stat">
            <div class="stat-value">{len(decimals)}</div>
            <div class="stat-label">Categories</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(presets)}</div>
            <div class="stat-label">Presets</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(analyses)}</div>
            <div class="stat-label">Analyses</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(tags)}</div>
            <div class="stat-label">Tags</div>
        </div>
        <div class="stat">
            <div class="stat-value">{transcribed_files + transcribed_zoom}</div>
            <div class="stat-label">Transcribed</div>
        </div>
    </div>

    <!-- Workflow Flow Diagram - Interactive Graph -->
    <div class="section">
        <div class="section-header">
            <span class="section-title">Workflow Overview</span>
            <span class="section-badge">hover to explore connections</span>
        </div>
        <div class="section-content">
            <div id="workflow-graph" style="height: 400px; border: 1px solid var(--border); border-radius: 6px;"></div>
            <div id="hover-info" style="margin-top: 1rem; padding: 0.75rem; background: var(--bg-secondary); border-radius: 6px; min-height: 60px;">
                <span style="color: var(--text-muted);">Hover over a node to see its connections</span>
            </div>
        </div>
    </div>

    <!-- vis.js Network -->
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <script>
        {generate_graph_data(presets, decimals, analyses)}
    </script>

    <!-- Presets -->
    <div class="section">
        <div class="section-header" onclick="toggleSection('presets')">
            <span class="section-title">Presets</span>
            <span class="section-badge">{len(presets)} configured</span>
        </div>
        <div class="section-content" id="presets">
            <div class="grid">
                {generate_preset_cards(presets, decimals)}
            </div>
            <p class="config-path">Config: ~/.config/kb/config.yaml</p>
        </div>
    </div>

    <!-- Decimal Categories -->
    <div class="section">
        <div class="section-header" onclick="toggleSection('decimals')">
            <span class="section-title">Decimal Categories</span>
            <span class="section-badge">{len(decimals)} categories</span>
        </div>
        <div class="section-content" id="decimals">
            <div class="grid">
                {generate_decimal_cards(decimals)}
            </div>
            <p class="config-path">Config: {KB_ROOT}/config/registry.json</p>
        </div>
    </div>

    <!-- Analysis Types -->
    <div class="section">
        <div class="section-header" onclick="toggleSection('analyses')">
            <span class="section-title">Analysis Types</span>
            <span class="section-badge">{len(analyses)} types</span>
        </div>
        <div class="section-content" id="analyses">
            <div class="grid">
                {generate_analysis_cards(analyses)}
            </div>
            <p class="config-path">Config: {CONFIG_DIR}/analysis_types/*.json</p>
        </div>
    </div>

    <!-- Two Column: Tags & Zoom Config -->
    <div class="two-col">
        <div class="section">
            <div class="section-header">
                <span class="section-title">Tags</span>
                <span class="section-badge">{len(tags)} available</span>
            </div>
            <div class="section-content">
                <div>
                    {generate_tags(tags)}
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-header">
                <span class="section-title">Zoom Configuration</span>
            </div>
            <div class="section-content">
                <p style="color: var(--text-secondary); margin-bottom: 0.75rem; font-size: 0.85rem;">Ignored Participants</p>
                <div class="ignore-list">
                    {generate_ignore_list(zoom_config.get('ignore_participants', []))}
                </div>
            </div>
        </div>
    </div>

    <!-- Defaults -->
    <div class="section">
        <div class="section-header">
            <span class="section-title">Defaults</span>
        </div>
        <div class="section-content">
            <table class="defaults-table">
                <tr><td>Whisper Model</td><td>{defaults.get('whisper_model', 'medium')}</td></tr>
                <tr><td>Gemini Model</td><td>{defaults.get('gemini_model', 'gemini-2.0-flash')}</td></tr>
                <tr><td>Default Decimal</td><td>{defaults.get('decimal', '50.01.01')}</td></tr>
                <tr><td>KB Output</td><td>{KB_ROOT}</td></tr>
                <tr><td>Config File</td><td>{CONFIG_FILE}</td></tr>
            </table>
        </div>
    </div>

    <footer>
        Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · KB Dashboard Preview
    </footer>

    <script>
        function toggleSection(id) {{
            const el = document.getElementById(id);
            el.style.display = el.style.display === 'none' ? 'block' : el.style.display;
        }}

        function togglePrompt(id) {{
            const preview = document.getElementById('preview-' + id);
            const full = document.getElementById('full-' + id);
            const btn = document.getElementById('btn-' + id);

            if (full.style.display === 'none' || full.style.display === '') {{
                full.style.display = 'block';
                preview.style.display = 'none';
                btn.textContent = 'Collapse';
            }} else {{
                full.style.display = 'none';
                preview.style.display = 'block';
                btn.textContent = 'Expand';
            }}
        }}
    </script>
</body>
</html>
'''
    return html


def generate_preset_flow_items(presets: dict) -> str:
    """Generate flow items for presets."""
    items = []
    for key, preset in presets.items():
        label = preset.get('label', key)
        if len(label) > 20:
            label = label[:18] + '...'
        items.append(f'<div class="flow-item preset">{label}</div>')
    return '\n'.join(items)


def generate_decimal_flow_items(decimals: dict) -> str:
    """Generate flow items for decimals."""
    items = []
    for code, info in sorted(decimals.items()):
        name = info.get('name', code)
        if len(name) > 18:
            name = name[:16] + '...'
        items.append(f'<div class="flow-item decimal">{code}</div>')
    return '\n'.join(items)


def generate_analysis_flow_items(analyses: list) -> str:
    """Generate flow items for analyses."""
    items = []
    for analysis in analyses:
        items.append(f'<div class="flow-item analysis">{analysis["name"]}</div>')
    return '\n'.join(items)


def generate_preset_cards(presets: dict, decimals: dict) -> str:
    """Generate preset cards."""
    cards = []
    for key, preset in presets.items():
        sources = preset.get('sources', [])
        source_tags = ''.join(f'<span class="tag source">{s}</span>' for s in sources)

        decimal = preset.get('decimal', '')
        decimal_name = decimals.get(decimal, {}).get('name', '')

        tags = preset.get('tags', [])
        tag_html = ''.join(f'<span class="tag">{t}</span>' for t in tags) if tags else '<span style="color: var(--text-muted);">none</span>'

        cards.append(f'''
            <div class="card">
                <div class="card-title">
                    {preset.get('label', key)}
                </div>
                <div class="card-subtitle">{source_tags}</div>
                <div class="card-detail">
                    <span class="card-detail-label">Decimal:</span>
                    <span class="decimal-code">{decimal}</span>
                    <span style="color: var(--text-muted);">({decimal_name})</span>
                </div>
                <div class="card-detail">
                    <span class="card-detail-label">Title:</span>
                    <code style="color: var(--accent-cyan);">{preset.get('title_template', '')}</code>
                </div>
                <div class="card-detail">
                    <span class="card-detail-label">Tags:</span> {tag_html}
                </div>
            </div>
        ''')
    return '\n'.join(cards)


def generate_decimal_cards(decimals: dict) -> str:
    """Generate decimal category cards."""
    cards = []
    for code, info in sorted(decimals.items()):
        analyses = info.get('default_analyses', [])
        analysis_tags = ''.join(f'<span class="tag">{a}</span>' for a in analyses) if analyses else '<span style="color: var(--text-muted);">none</span>'

        cards.append(f'''
            <div class="card">
                <div class="card-title">
                    <span class="decimal-code">{code}</span>
                </div>
                <div class="card-subtitle">{info.get('name', '')}</div>
                <div class="card-detail" style="color: var(--text-secondary); font-size: 0.8rem; margin-bottom: 0.5rem;">
                    {info.get('description', '')}
                </div>
                <div class="card-detail">
                    <span class="card-detail-label">Default Analyses:</span><br>
                    {analysis_tags}
                </div>
            </div>
        ''')
    return '\n'.join(cards)


def generate_analysis_cards(analyses: list) -> str:
    """Generate analysis type cards."""
    cards = []
    for i, analysis in enumerate(analyses):
        prompt = analysis.get('prompt', '')
        preview = prompt[:150] + '...' if len(prompt) > 150 else prompt

        cards.append(f'''
            <div class="card">
                <div class="card-title">
                    {analysis['name']}
                    <button class="expand-btn" id="btn-{i}" onclick="togglePrompt({i})">Expand</button>
                </div>
                <div class="card-subtitle">{analysis.get('description', '')}</div>
                <div class="prompt-preview" id="preview-{i}">{preview}</div>
                <div class="prompt-full" id="full-{i}">{prompt}</div>
            </div>
        ''')
    return '\n'.join(cards)


def generate_tags(tags: list) -> str:
    """Generate tag display."""
    return ''.join(f'<span class="tag">{t}</span>' for t in sorted(tags))


def generate_ignore_list(ignore_list: list) -> str:
    """Generate ignore list display."""
    if not ignore_list:
        return '<span style="color: var(--text-muted);">none configured</span>'
    return ''.join(f'<span class="ignore-item">{item}</span>' for item in ignore_list)


def generate_graph_data(presets: dict, decimals: dict, analyses: list) -> str:
    """Generate vis.js network graph JavaScript."""
    import json

    nodes = []
    edges = []
    node_id = 0
    id_map = {}  # Track node IDs

    # Colors matching Tokyo Night theme
    colors = {
        'source': '#9ece6a',      # green
        'preset': '#7aa2f7',      # blue
        'decimal': '#e0af68',     # yellow
        'analysis': '#bb9af7',    # magenta
    }

    # Sources (level 0)
    sources = ['file', 'cap', 'volume', 'zoom', 'paste']
    for i, source in enumerate(sources):
        node_id += 1
        id_map[f'source_{source}'] = node_id
        nodes.append({
            'id': node_id,
            'label': source,
            'group': 'source',
            'level': 0,
            'title': f'Source: {source}',
            'color': {'background': colors['source'], 'border': colors['source']},
        })

    # Presets (level 1)
    for key, preset in presets.items():
        node_id += 1
        id_map[f'preset_{key}'] = node_id
        label = preset.get('label', key)
        if len(label) > 20:
            label = label[:18] + '...'
        nodes.append({
            'id': node_id,
            'label': label,
            'group': 'preset',
            'level': 1,
            'title': f"Preset: {preset.get('label', key)}\\nDecimal: {preset.get('decimal', '')}\\nTemplate: {preset.get('title_template', '')}",
            'color': {'background': colors['preset'], 'border': colors['preset']},
        })

        # Edges: source → preset
        for source in preset.get('sources', []):
            source_id = id_map.get(f'source_{source}')
            if source_id:
                edges.append({
                    'from': source_id,
                    'to': node_id,
                    'color': {'color': '#3b4261', 'highlight': colors['source']},
                })

    # Decimals (level 2)
    for code, info in sorted(decimals.items()):
        node_id += 1
        id_map[f'decimal_{code}'] = node_id
        nodes.append({
            'id': node_id,
            'label': code,
            'group': 'decimal',
            'level': 2,
            'title': f"Category: {code}\\n{info.get('name', '')}\\n{info.get('description', '')}",
            'color': {'background': colors['decimal'], 'border': colors['decimal']},
        })

    # Edges: preset → decimal
    for key, preset in presets.items():
        preset_id = id_map.get(f'preset_{key}')
        decimal_code = preset.get('decimal', '')
        decimal_id = id_map.get(f'decimal_{decimal_code}')
        if preset_id and decimal_id:
            edges.append({
                'from': preset_id,
                'to': decimal_id,
                'color': {'color': '#3b4261', 'highlight': colors['preset']},
            })

    # Analyses (level 3)
    for analysis in analyses:
        node_id += 1
        id_map[f'analysis_{analysis["name"]}'] = node_id
        nodes.append({
            'id': node_id,
            'label': analysis['name'],
            'group': 'analysis',
            'level': 3,
            'title': f"Analysis: {analysis['name']}\\n{analysis.get('description', '')}",
            'color': {'background': colors['analysis'], 'border': colors['analysis']},
        })

    # Edges: decimal → analysis (based on default_analyses)
    for code, info in decimals.items():
        decimal_id = id_map.get(f'decimal_{code}')
        for analysis_name in info.get('default_analyses', []):
            analysis_id = id_map.get(f'analysis_{analysis_name}')
            if decimal_id and analysis_id:
                edges.append({
                    'from': decimal_id,
                    'to': analysis_id,
                    'color': {'color': '#3b4261', 'highlight': colors['decimal']},
                })

    # Build the JavaScript
    js = f'''
        const nodes = new vis.DataSet({json.dumps(nodes)});
        const edges = new vis.DataSet({json.dumps(edges)});

        const container = document.getElementById('workflow-graph');
        const data = {{ nodes: nodes, edges: edges }};

        const options = {{
            layout: {{
                hierarchical: {{
                    direction: 'LR',
                    sortMethod: 'directed',
                    levelSeparation: 200,
                    nodeSpacing: 80,
                    treeSpacing: 100,
                }}
            }},
            nodes: {{
                shape: 'box',
                borderWidth: 2,
                font: {{
                    color: '#c0caf5',
                    face: 'SF Mono, Fira Code, Consolas, monospace',
                    size: 12,
                }},
                margin: 10,
                shadow: true,
            }},
            edges: {{
                arrows: 'to',
                smooth: {{
                    type: 'cubicBezier',
                    forceDirection: 'horizontal',
                }},
                width: 2,
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 100,
            }},
            physics: false,
        }};

        const network = new vis.Network(container, data, options);

        // Hover info panel
        const hoverInfo = document.getElementById('hover-info');

        network.on('hoverNode', function(params) {{
            const nodeId = params.node;
            const node = nodes.get(nodeId);

            // Find connected nodes
            const connectedEdges = edges.get({{
                filter: e => e.from === nodeId || e.to === nodeId
            }});

            const connectedNodeIds = new Set();
            connectedEdges.forEach(e => {{
                connectedNodeIds.add(e.from);
                connectedNodeIds.add(e.to);
            }});

            const connectedNodes = nodes.get(Array.from(connectedNodeIds));

            // Group by level
            const byLevel = {{}};
            connectedNodes.forEach(n => {{
                const level = n.level;
                if (!byLevel[level]) byLevel[level] = [];
                byLevel[level].push(n.label);
            }});

            const levelNames = ['Sources', 'Presets', 'Categories', 'Analyses'];
            let html = `<strong style="color: ${{node.color.background}}">${{node.label}}</strong><br>`;
            html += '<span style="color: var(--text-secondary); font-size: 0.85rem;">Connected: ';

            const parts = [];
            for (let i = 0; i < 4; i++) {{
                if (byLevel[i] && byLevel[i].length > 0) {{
                    const filtered = byLevel[i].filter(l => l !== node.label);
                    if (filtered.length > 0) {{
                        parts.push(`${{levelNames[i]}}: ${{filtered.join(', ')}}`);
                    }}
                }}
            }}
            html += parts.join(' → ') || 'none';
            html += '</span>';

            hoverInfo.innerHTML = html;

            // Highlight connected edges
            const allEdges = edges.get();
            allEdges.forEach(e => {{
                if (e.from === nodeId || e.to === nodeId) {{
                    edges.update({{id: e.id, width: 4, color: {{color: node.color.background}}}});
                }}
            }});
        }});

        network.on('blurNode', function() {{
            hoverInfo.innerHTML = '<span style="color: var(--text-muted);">Hover over a node to see its connections</span>';

            // Reset edge styles
            const allEdges = edges.get();
            allEdges.forEach(e => {{
                edges.update({{id: e.id, width: 2, color: {{color: '#3b4261'}}}});
            }});
        }});
    '''

    return js


def main():
    """Generate and open the dashboard."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate KB configuration dashboard")
    parser.add_argument("--output", "-o", help="Output file path (default: temp file)")
    parser.add_argument("--no-open", action="store_true", help="Don't open in browser")
    args = parser.parse_args()

    html = generate_html()

    if args.output:
        output_path = Path(args.output)
    else:
        # Use temp file
        fd, path = tempfile.mkstemp(suffix='.html', prefix='kb-dashboard-')
        os.close(fd)
        output_path = Path(path)

    with open(output_path, 'w') as f:
        f.write(html)

    print(f"Dashboard generated: {output_path}")

    if not args.no_open:
        webbrowser.open(f"file://{output_path}")


if __name__ == "__main__":
    main()
