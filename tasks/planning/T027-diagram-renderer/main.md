# T027: Diagram Renderer — Replace Mermaid with JSON→SVG

## Meta
- **Status:** PLANNING
- **Created:** 2026-02-10
- **Priority:** 3

## Task

Replace the current two-step mermaid diagram pipeline (LLM generates mermaid code → LLM converts to SVG) with a deterministic JSON description → SVG renderer.

**Why:** Mermaid is a lossy intermediate format. The LLM generates mermaid syntax, then another LLM call converts it to SVG. Two points of failure, inconsistent output, and no control over styling. A JSON schema describing diagram structure (nodes, edges, labels) fed into a deterministic SVG renderer gives consistent, brandable output every time.

**Approach (agreed with Blake):** Option B — JSON diagram description + deterministic SVG renderer.

## Scope
- **In:** New diagram JSON schema, deterministic SVG renderer (Python), template integration, carousel_slides prompt update
- **Out:** Keeping mermaid as fallback (clean break), mmdc CLI dependency

## Dependencies
- T026 (Carousel Quality) — should be complete first
