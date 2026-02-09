### **Core Issues & Fixes**

#### **1. JSON Schema Enforcement (Gemini API Strictness)**
The research indicates that while `response_schema` (or `response_json_schema`) enforces the *structure* (keys, types), it **does not inherently enforce non-empty strings** or semantic constraints like "must be a bullet point" unless explicitly designed to do so.
*   **Problem:** The current schema likely uses `{"type": "string"}` for fields like `title`. Gemini is technically compliant by returning `""` (empty string).
*   **Fix:**
    *   **Enforce Non-Empty Strings:** Use the schema keywords `minLength: 1` or specific `pattern` (regex) if the SDK version allows (support varies by backend version, see below).
    *   **Strict Mode (Validation):** If the schema validation on Gemini's side is loose (ignoring `minLength` as noted in some GitHub issues for Vertex AI), the application code **must** implement a post-validation retry loop. The "validation + retry" pattern is standard practice.
    *   **Bullet Point Enforcement:** The schema for `content` is currently a single string. It should ideally be an **array of strings** (`"type": "array", "items": {"type": "string"}`). This forces the model to break content into distinct items, eliminating the need for the model to "draw" bullet characters (`-` or `•`) and allowing the template to render them consistently as `<ul><li>`.

#### **2. Prompt Engineering Compliance**
Gemini (especially Flash/Pro variants) can be "lazy" or hallucinate formats if not constrained heavily.
*   **Problem:** The model ignores negative constraints ("DO NOT copy") and formatting rules ("start with - ").
*   **Fix:**
    *   **Positive Constraints:** Instead of "Don't use paragraphs", use "Return an array of 3-4 strings".
    *   **Few-Shot Examples:** The current one-shot example is insufficient. Providing 3 diverse examples (including edge cases) significantly improves compliance.
    *   **Pre-fill/Priming:** (Advanced) If the API allows, pre-filling the response start (e.g., `{"slides": [`) can guide the model, though standard JSON mode usually handles this.

#### **3. Mermaid Theming & Layout**
The default mermaid rendering is generic and visually distinct from the "brand" look.
*   **Problem:** `mmdc` uses a default theme. `graph LR` creates short, wide diagrams.
*   **Fix:**
    *   **Theming:** The `mmdc` CLI (and Mermaid.js) supports a `themeVariables` configuration object (JSON) or a `%%{init: {...}}%%` directive inside the mermaid code itself. The prompt should instruct the LLM to include this directive with brand colors (e.g., `%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#8B5CF6'}}}%%`), OR the `mmdc` command in `kb/publish.py` should inject a config file matching the brand.
    *   **Orientation:** The prompt must explicitly request `graph TD` (Top-Down) for vertical diagrams to better utilize slide space.

#### **4. Markdown Parsing (Template Layer)**
The `markdown_to_html` function is too fragile.
*   **Problem:** It relies on specific characters (`- `) that the LLM often gets wrong (`•` or `*`).
*   **Fix:**
    *   **Robustness:** Update `markdown_to_html` to regex-match multiple bullet styles (`^[\-\*•]\s+`) and normalize them.
    *   **Schema Change:** If we switch the JSON schema to return an *array* of strings for content, this parsing logic becomes obsolete/much simpler (just iterate the array in Jinja2).

### **Actionable Recommendations for Phase 1**

1.  **Schema Refactor:** Change `content` from `string` to `array<string>`. This solves the bullet point formatting issue permanently.
2.  **Validation Layer:** Implement a Pydantic validator or simple python check that raises an error if `title` is empty, triggering a retry with a "correction prompt".
3.  **Prompt Update:**
    *   Add 3 few-shot examples.
    *   Force `graph TD` for mermaid.
    *   Remove "bullet point" formatting instructions (since we'll use an array).
4.  **Mermaid Config:** Create a `mermaid-theme.json` with brand colors and pass it to `mmdc` via `-C` flag or inject `%%{init}` header.

This concludes the deep research. The next step is implementation.

<answer>
# Research Report: Visual Carousel Generation Issues

## Core Issues Identified

### 1. Weak Schema Enforcement (Root of Empty Titles)
The primary failure is relying on `response_schema` to enforce *semantic* quality (non-empty strings) which it currently treats only as *structural* hints.
*   **Finding:** Gemini's JSON schema validation ensures the field *exists* but permits empty strings (`""`). The `required` field in JSON schema does not imply `minLength > 0`.
*   **Evidence:** GitHub issues and documentation confirm that while strict schema support is improving, models often default to empty strings when "lazy" or uncertain, effectively bypassing the intent of "required".
*   **Solution:**
    *   **Schema Update:** Add `minLength: 5` to the schema for the `title` field (if supported by the specific SDK/backend version).
    *   **Application-Layer Validation:** Essential "Validation + Retry" loop. The Python script must check for `len(title) < 2` and immediately reject the response, sending it back to the model with a specific error message.

### 2. "Prose vs. Bullets" Mismatch
The model consistently fails to format content as bullet points because it is being asked to format a single string with markdown characters (`- `), which is error-prone.
*   **Finding:** The "String with bullet markers" approach is fragile. Models often substitute markers (`•` vs `-`) or revert to paragraphs.
*   **Solution (Architectural Fix):** Change the `content` field in the schema from a `string` to an `array of strings`.
    *   *Current:* `"content": "- Point 1\n- Point 2"`
    *   *Proposed:* `"content": ["Point 1", "Point 2"]`
    *   This forces the model to structure the data item-by-item, effectively making "prose" impossible and removing the need for complex markdown parsing in the template.

### 3. Mermaid Visualization Gaps
The mermaid diagrams look "broken" because they lack brand styling and use the wrong orientation for the canvas.
*   **Finding:** The default `graph LR` (Left-to-Right) layout creates short, wide diagrams (70px height) that leave 90% of the slide empty. The default colors (dark/forest) clash with the "Brand Purple".
*   **Solution:**
    *   **Prompting:** Explicitly require `graph TD` (Top-Down) to fill the vertical slide space.
    *   **Theming:** Inject a standard `%%{init: ... }%%` block into the mermaid code via the prompt (or post-processing) that sets `themeVariables` to use the brand hex code `#8B5CF6`.

## Detailed Fix Plan

### Step 1: Schema Redesign (High Impact)
Refactor `kb/config/analysis_types/carousel_slides.json` to use stricter types.

```json
{
  "type": "object",
  "properties": {
    "slides": {
      "type": "array",
      "items": {
        "properties": {
          "title": { "type": "string" }, 
          "content": { 
            "type": "array", 
            "items": { "type": "string" },
            "description": "3-4 distinct bullet points. No bullet characters."
          }
          // ...
        }
      }
    }
  }
}
```

### Step 2: Application-Layer Validation (Reliability)
Update `kb/analyze.py` to include a validation loop.
1.  **Parse JSON.**
2.  **Check:** Are any titles empty? Is the content array length < 2?
3.  **Action:** If invalid, call the model again with the previous output + error message: *"You returned empty titles. Fix this immediately."*

### Step 3: Template Logic Update
Update `kb/render.py` and `brand-purple.html`.
*   Remove fragile regex parsing (`markdown_to_html`).
*   Simply iterate over the new list: `{% for item in slide.content %} <li>{{ item }}</li> {% endfor %}`.

### Step 4: Mermaid Branding
Update the prompt in `kb/config/analysis_types/carousel_slides.json` to mandate the styling header:
> "Start every mermaid diagram with: `%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#8B5CF6'}}}%%` and use `graph TD`."

## Conclusion
The issues are not bugs in the code but rather **fragilities in the LLM integration strategy**. Moving from "text-based formatting instructions" (e.g., "start lines with dashes") to "schema-based structural constraints" (e.g., "return an array") is the definitive fix.
</answer>

