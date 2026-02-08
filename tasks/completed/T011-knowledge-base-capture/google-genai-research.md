# Google GenAI Python SDK Reference

**SDK**: `google-genai` (NOT `google-generativeai` which is deprecated)
**Status**: General Availability (GA) as of May 2025
**Latest Version**: 1.59.0 (January 2026)

> **Important**: The old `google-generativeai` library reached End-of-Life on November 30, 2025. Always use `google-genai`.

---

## 1. Installation

```bash
pip install google-genai

# With async support (faster performance)
pip install google-genai[aiohttp]

# Using uv
uv pip install google-genai
```

---

## 2. Client Initialization

### Basic Import

```python
from google import genai
from google.genai import types
```

### Gemini Developer API (AI Studio)

```python
# Explicit API key
client = genai.Client(api_key='YOUR_GEMINI_API_KEY')

# Using environment variable (recommended)
# Set: export GEMINI_API_KEY='your-api-key'
# Or:  export GOOGLE_API_KEY='your-api-key'
client = genai.Client()
```

### Vertex AI

```python
client = genai.Client(
    vertexai=True,
    project='your-project-id',
    location='us-central1'
)

# Or via environment variables:
# export GOOGLE_GENAI_USE_VERTEXAI=true
# export GOOGLE_CLOUD_PROJECT='your-project-id'
# export GOOGLE_CLOUD_LOCATION='us-central1'
client = genai.Client()
```

### Context Manager (Recommended)

```python
# Sync client - automatically closes connection
with genai.Client() as client:
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents='Hello'
    )

# Async client
async with genai.Client().aio as client:
    response = await client.models.generate_content(
        model='gemini-2.5-flash',
        contents='Hello'
    )
```

### Manual Cleanup

```python
client = genai.Client()
# ... use client ...
client.close()  # Sync
# await client.aio.aclose()  # Async
```

---

## 3. Basic Generation

### Simple Text Generation

```python
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Why is the sky blue?'
)
print(response.text)
```

### With Configuration

```python
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Write a haiku about coding',
    config=types.GenerateContentConfig(
        system_instruction='You are a creative poet',
        temperature=0.7,
        top_p=0.95,
        top_k=40,
        max_output_tokens=500,
    ),
)
```

### Using Dictionary Config

```python
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Explain quantum computing',
    config={
        'temperature': 0.3,
        'max_output_tokens': 1000,
    },
)
```

### Streaming

```python
# Sync streaming
for chunk in client.models.generate_content_stream(
    model='gemini-2.5-flash',
    contents='Tell me a story'
):
    print(chunk.text, end='')

# Async streaming
async for chunk in await client.aio.models.generate_content_stream(
    model='gemini-2.5-flash',
    contents='Tell me a story'
):
    print(chunk.text, end='')
```

### Async Generation

```python
response = await client.aio.models.generate_content(
    model='gemini-2.5-flash',
    contents='Explain async programming'
)
print(response.text)
```

---

## 4. Structured Output / JSON Schema

### Method 1: Pydantic Model (Recommended)

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class Ingredient(BaseModel):
    name: str = Field(description="Name of the ingredient")
    quantity: str = Field(description="Amount with units")

class Recipe(BaseModel):
    recipe_name: str = Field(description="Name of the recipe")
    prep_time_minutes: Optional[int] = None
    ingredients: List[Ingredient]
    instructions: List[str]

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Give me a recipe for chocolate chip cookies',
    config=types.GenerateContentConfig(
        response_mime_type='application/json',
        response_schema=Recipe,
    ),
)

# Parse the response
recipe = Recipe.model_validate_json(response.text)
print(recipe.recipe_name)
print(recipe.ingredients)
```

### Method 2: JSON Schema Dict

```python
user_schema = {
    'type': 'object',
    'properties': {
        'username': {'type': 'string'},
        'age': {'type': 'integer'},
        'email': {'type': 'string'},
    },
    'required': ['username', 'age'],
}

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Generate a random user profile',
    config={
        'response_mime_type': 'application/json',
        'response_json_schema': user_schema,
    },
)
```

### Method 3: Using model_json_schema()

```python
class Feedback(BaseModel):
    sentiment: Literal["positive", "neutral", "negative"]
    summary: str
    key_points: List[str]

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Analyze this review: "Great product, fast shipping!"',
    config={
        'response_mime_type': 'application/json',
        'response_json_schema': Feedback.model_json_schema(),
    },
)

# Validate response
feedback = Feedback.model_validate_json(response.text)
```

### Enum Support

```python
class Classification(BaseModel):
    category: Literal["bug", "feature", "question", "documentation"]
    priority: Literal["low", "medium", "high", "critical"]
    description: str

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Classify: "The app crashes when I click save"',
    config=types.GenerateContentConfig(
        response_mime_type='application/json',
        response_schema=Classification,
    ),
)
```

### Lists of Objects

```python
class Person(BaseModel):
    name: str
    role: str

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='List 3 famous scientists',
    config=types.GenerateContentConfig(
        response_mime_type='application/json',
        response_schema=list[Person],  # List of Pydantic models
    ),
)
```

### Streaming with Structured Output

```python
response_stream = client.models.generate_content_stream(
    model='gemini-2.5-flash',
    contents=prompt,
    config={
        'response_mime_type': 'application/json',
        'response_json_schema': Recipe.model_json_schema(),
    },
)

full_response = ""
for chunk in response_stream:
    full_response += chunk.text

# Parse after streaming completes
recipe = Recipe.model_validate_json(full_response)
```

---

## 5. Model Names

### Current Production Models (January 2026)

| Model | ID | Context | Output | Best For |
|-------|-----|---------|--------|----------|
| **Gemini 2.5 Flash** | `gemini-2.5-flash` | 1M | 65K | Price-performance balance |
| **Gemini 2.5 Flash-Lite** | `gemini-2.5-flash-lite` | 1M | 65K | Cost-efficiency, high throughput |
| **Gemini 2.5 Pro** | `gemini-2.5-pro` | 1M | 65K | Complex reasoning |

### Preview Models (Gemini 3 Series)

| Model | ID | Notes |
|-------|-----|-------|
| Gemini 3 Pro | `gemini-3-pro-preview` | Best multimodal understanding |
| Gemini 3 Flash | `gemini-3-flash-preview` | Speed + intelligence balance |
| Gemini 3 Pro Image | `gemini-3-pro-image-preview` | Image generation |

### Deprecated Models

- `gemini-2.0-flash` / `gemini-2.0-flash-lite` - Retiring **March 3, 2026**
- All Gemini 1.0 and 1.5 models - Already retired (return 404)

### Model Selection

```python
# Get model info
model_info = client.models.get(model='gemini-2.5-flash')
print(model_info)

# List available models
for model in client.models.list():
    print(model.name)
```

---

## 6. Error Handling

### Exception Hierarchy

```python
from google.genai import errors

# Base class
errors.APIError          # General API errors (has .code, .message, .status)
  errors.ClientError     # HTTP 4xx errors (400-499)
  errors.ServerError     # HTTP 5xx errors (500-599)

# Specialized exceptions
errors.UnknownFunctionCallArgumentError  # Function call arg conversion failed
errors.UnsupportedFunctionError          # Function not supported
errors.FunctionInvocationError           # Function invocation failed
errors.UnknownApiResponseError           # Response not parseable as JSON
```

### Basic Error Handling

```python
from google.genai import errors

try:
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents='Hello'
    )
except errors.ClientError as e:
    # 4xx errors (bad request, auth, not found, rate limit)
    print(f"Client error {e.code}: {e.message}")
except errors.ServerError as e:
    # 5xx errors (server issues)
    print(f"Server error {e.code}: {e.message}")
except errors.APIError as e:
    # Any other API error
    print(f"API error {e.code}: {e.message}")
```

### Comprehensive Error Handling

```python
from google.genai import errors
import time

def generate_with_retry(client, prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text

        except errors.ClientError as e:
            if e.code == 429:  # Rate limit
                wait_time = 2 ** attempt
                print(f"Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            elif e.code == 400:  # Bad request
                raise ValueError(f"Invalid request: {e.message}")
            elif e.code == 401:  # Unauthorized
                raise PermissionError(f"Auth failed: {e.message}")
            elif e.code == 404:  # Not found
                raise ValueError(f"Model not found: {e.message}")
            else:
                raise

        except errors.ServerError as e:
            # Retry on server errors
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise

    raise Exception("Max retries exceeded")
```

### Common HTTP Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 400 | Bad request / Invalid argument | Check request format |
| 401 | Unauthorized | Check API key |
| 403 | Forbidden | Check permissions |
| 404 | Not found | Check model name |
| 429 | Rate limited | Implement backoff |
| 500 | Server error | Retry with backoff |
| 503 | Service unavailable | Retry later |

---

## 7. Rate Limits & Best Practices

### Current Limits (December 2025)

**Free Tier:**
- Gemini 2.5 Pro: 5 RPM, 25 RPD
- Gemini 2.5 Flash: 15 RPM, 500 RPD
- Gemini 2.5 Flash-Lite: 30 RPM, 1,000 RPD

**Paid Tier 1:**
- Up to 1,000 RPM depending on model
- Higher token limits

> **Note**: December 2025 changes reduced quotas by 50-80%. If your app worked before and fails now, check your tier.

### Rate Limit Dimensions

- **RPM**: Requests per minute
- **TPM**: Tokens per minute
- **RPD**: Requests per day (resets midnight PT)
- **IPM**: Images per minute

### Best Practices

#### 1. Use Environment Variables

```python
import os

# Never hardcode API keys
# Set: export GEMINI_API_KEY='your-key'
client = genai.Client()  # Auto-picks up env var
```

#### 2. Implement Exponential Backoff

```python
import time
from google.genai import errors

def call_with_backoff(func, max_retries=5):
    for attempt in range(max_retries):
        try:
            return func()
        except errors.ClientError as e:
            if e.code == 429:
                wait = min(2 ** attempt, 60)
                time.sleep(wait)
            else:
                raise
    raise Exception("Max retries exceeded")
```

#### 3. Use Async for High Throughput

```python
import asyncio

async def process_batch(client, prompts):
    tasks = [
        client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        for prompt in prompts
    ]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

#### 4. Use Context Managers

```python
# Ensures proper cleanup
with genai.Client() as client:
    response = client.models.generate_content(...)
```

#### 5. Optimize Token Usage

```python
config = types.GenerateContentConfig(
    max_output_tokens=500,  # Limit output
    temperature=0,          # Deterministic = faster
)
```

#### 6. Circuit Breaker Pattern

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_time=60):
        self.failures = 0
        self.threshold = failure_threshold
        self.recovery_time = recovery_time
        self.last_failure = 0

    def can_proceed(self):
        if self.failures >= self.threshold:
            if time.time() - self.last_failure > self.recovery_time:
                self.failures = 0
                return True
            return False
        return True

    def record_failure(self):
        self.failures += 1
        self.last_failure = time.time()

    def record_success(self):
        self.failures = 0
```

---

## 8. Additional Features

### File Upload (Gemini Developer API)

```python
file = client.files.upload(file='document.pdf')
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=['Summarize this document', file]
)
```

### Function Calling

```python
def get_weather(location: str) -> str:
    """Get current weather for a location."""
    return f"Weather in {location}: Sunny, 72F"

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='What is the weather in Boston?',
    config=types.GenerateContentConfig(
        tools=[get_weather]
    ),
)
```

### System Instructions

```python
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='What should I have for dinner?',
    config=types.GenerateContentConfig(
        system_instruction='You are a helpful nutritionist. Always suggest healthy options.',
    ),
)
```

### Image Generation

```python
response = client.models.generate_content(
    model='gemini-2.5-flash-image',
    contents='A serene mountain landscape at sunset',
    config=types.GenerateContentConfig(
        response_modalities=['IMAGE'],
        image_config=types.ImageConfig(aspect_ratio='16:9'),
    ),
)

for part in response.parts:
    if part.inline_data:
        image = part.as_image()
        image.save('output.png')
```

---

## References

- [GitHub Repository](https://github.com/googleapis/python-genai)
- [Official Documentation](https://googleapis.github.io/python-genai/)
- [PyPI Package](https://pypi.org/project/google-genai/)
- [Gemini API Models](https://ai.google.dev/gemini-api/docs/models)
- [Structured Output Guide](https://ai.google.dev/gemini-api/docs/structured-output)
- [Rate Limits](https://ai.google.dev/gemini-api/docs/rate-limits)
