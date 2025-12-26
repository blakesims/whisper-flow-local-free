#!/usr/bin/env python3
"""
Post-Processor Test Script

Tests different models and prompts against sample transcripts.
Usage:
    python scripts/test_post_processor.py
    python scripts/test_post_processor.py --model mlx-community/Qwen3-4B-4bit
    python scripts/test_post_processor.py --prompt /path/to/prompt.txt
    python scripts/test_post_processor.py --list-models
"""

import argparse
import time
import sys
from pathlib import Path

# Sample transcripts with various issues (filler words, repetition, lists)
SAMPLE_TRANSCRIPTS = [
    {
        "id": "filler_words",
        "input": "So, um, I was thinking, like, you know, we should probably, uh, fix this bug before, like, the release.",
        "expected_cleanup": "I was thinking we should probably fix this bug before the release.",
    },
    {
        "id": "repetition",
        "input": "I think, I think we need to, we need to focus on the main issue here.",
        "expected_cleanup": "I think we need to focus on the main issue here.",
    },
    {
        "id": "numbered_list",
        "input": "There are three things we need to do. One is update the database. Two is fix the API. Three is deploy to production.",
        "expected_cleanup": "There are three things we need to do:\n- Update the database\n- Fix the API\n- Deploy to production",
    },
    {
        "id": "complex_filler",
        "input": "I don't really know, I put my finger on what's going on here but I feel like, um, I feel like, I'm kind of paralyzed here because I'm not really sure how to proceed.",
        "expected_cleanup": "I don't really know, I can't put my finger on what's going on here, but I feel like I'm kind of paralyzed here because I'm not really sure how to proceed.",
    },
    {
        "id": "mixed_issues",
        "input": "Okay so like basically what I'm saying is, you know, first we need to like check the logs, second we need to um restart the server, and third we should like notify the team, you know what I mean?",
        "expected_cleanup": "What I'm saying is:\n- First, check the logs\n- Second, restart the server\n- Third, notify the team",
    },
    {
        "id": "minimal_cleanup",
        "input": "The meeting is scheduled for 3pm tomorrow in the main conference room.",
        "expected_cleanup": "The meeting is scheduled for 3pm tomorrow in the main conference room.",
    },
    {
        "id": "heavy_filler",
        "input": "Like, I literally, um, basically just, you know, kind of, sort of, actually want to, I mean, like, fix this thing.",
        "expected_cleanup": "I just want to fix this thing.",
    },
]

# Available models to test
AVAILABLE_MODELS = [
    "mlx-community/Llama-3.2-3B-Instruct-4bit",
    "mlx-community/Qwen3-4B-4bit",
    "mlx-community/gemma-2-2b-it-4bit",
    "mlx-community/Phi-3.5-mini-instruct-4bit",
]

DEFAULT_PROMPT = """You are a text editor. Clean up this transcribed speech by:
1. Remove filler words (um, uh, like, you know, kind of, sort of, I mean, basically, actually, literally)
2. Remove repeated words or phrases
3. Format any numbered items as bullet points using "-"
4. Fix grammar errors

Important: Output ONLY the cleaned text. No explanations, no markdown headers, no commentary.

Input: {text}

Output:"""


def load_prompt(prompt_path: str = None) -> str:
    """Load prompt from file or use default."""
    if prompt_path:
        path = Path(prompt_path)
        if path.exists():
            return path.read_text().strip()
        print(f"Warning: Prompt file not found: {prompt_path}")

    # Try loading from config
    config_prompt = Path.home() / "Library/Application Support/WhisperTranscribeUI/cleanup_prompt.txt"
    if config_prompt.exists():
        return config_prompt.read_text().strip()

    return DEFAULT_PROMPT


def format_prompt(template: str, text: str) -> str:
    """Format prompt template with input text, supporting multiple placeholder formats."""
    if "{{user_transcription_input}}" in template:
        return template.replace("{{user_transcription_input}}", text)
    elif "{user_transcription_input}" in template:
        return template.replace("{user_transcription_input}", text)
    else:
        return template.format(text=text)


def test_model(model_name: str, prompt_template: str, samples: list, verbose: bool = True):
    """Test a model against sample transcripts."""
    print(f"\n{'='*60}")
    print(f"Testing model: {model_name}")
    print(f"{'='*60}")

    try:
        from mlx_lm import load, generate
        from mlx_lm.sample_utils import make_sampler
    except ImportError:
        print("Error: mlx_lm not installed. Run: pip install mlx-lm")
        return None

    # Load model
    print(f"Loading model...")
    start = time.time()
    try:
        model, tokenizer = load(model_name)
    except Exception as e:
        print(f"Error loading model: {e}")
        return None
    load_time = time.time() - start
    print(f"Model loaded in {load_time:.1f}s")

    sampler = make_sampler(temp=0.1)
    results = []

    for sample in samples:
        print(f"\n--- Test: {sample['id']} ---")
        print(f"Input: {sample['input'][:80]}...")

        prompt = format_prompt(prompt_template, sample['input'])

        start = time.time()
        try:
            output = generate(
                model,
                tokenizer,
                prompt=prompt,
                max_tokens=min(len(sample['input'].split()) * 3, 500),
                sampler=sampler,
            )
            gen_time = time.time() - start

            output = output.strip()

            if verbose:
                print(f"Output: {output}")
                print(f"Time: {gen_time:.2f}s")

            results.append({
                "id": sample["id"],
                "input": sample["input"],
                "output": output,
                "expected": sample.get("expected_cleanup", ""),
                "time": gen_time,
                "success": len(output) > 0 and len(output) < len(sample["input"]) * 2,
            })

        except Exception as e:
            print(f"Error: {e}")
            results.append({
                "id": sample["id"],
                "error": str(e),
                "success": False,
            })

    # Summary
    print(f"\n{'='*60}")
    print(f"Summary for {model_name}")
    print(f"{'='*60}")
    successful = sum(1 for r in results if r.get("success", False))
    avg_time = sum(r.get("time", 0) for r in results) / len(results) if results else 0
    print(f"Success: {successful}/{len(results)}")
    print(f"Avg time: {avg_time:.2f}s")

    return results


def compare_models(models: list, prompt_template: str, samples: list):
    """Compare multiple models."""
    all_results = {}

    for model in models:
        results = test_model(model, prompt_template, samples, verbose=False)
        if results:
            all_results[model] = results

    # Print comparison table
    print(f"\n{'='*80}")
    print("MODEL COMPARISON")
    print(f"{'='*80}")

    print(f"\n{'Model':<45} {'Success':<10} {'Avg Time':<10}")
    print("-" * 65)

    for model, results in all_results.items():
        successful = sum(1 for r in results if r.get("success", False))
        avg_time = sum(r.get("time", 0) for r in results) / len(results)
        model_short = model.split("/")[-1][:40]
        print(f"{model_short:<45} {successful}/{len(results):<8} {avg_time:.2f}s")

    return all_results


def interactive_test(model_name: str, prompt_template: str):
    """Interactive mode - enter your own text to test."""
    print(f"\nInteractive mode with model: {model_name}")
    print("Enter text to clean up (empty line to quit):\n")

    try:
        from mlx_lm import load, generate
        from mlx_lm.sample_utils import make_sampler
    except ImportError:
        print("Error: mlx_lm not installed")
        return

    print("Loading model...")
    model, tokenizer = load(model_name)
    sampler = make_sampler(temp=0.1)
    print("Ready!\n")

    while True:
        try:
            text = input("Input: ").strip()
            if not text:
                break

            prompt = format_prompt(prompt_template, text)
            start = time.time()
            output = generate(
                model,
                tokenizer,
                prompt=prompt,
                max_tokens=min(len(text.split()) * 3, 500),
                sampler=sampler,
            )
            elapsed = time.time() - start

            print(f"Output: {output.strip()}")
            print(f"({elapsed:.2f}s)\n")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}\n")


def main():
    parser = argparse.ArgumentParser(description="Test post-processor models and prompts")
    parser.add_argument("--model", "-m", help="Model to test (default: Llama-3.2-3B)")
    parser.add_argument("--prompt", "-p", help="Path to prompt file")
    parser.add_argument("--compare", "-c", action="store_true", help="Compare multiple models")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--list-models", action="store_true", help="List available models")
    parser.add_argument("--samples", "-s", help="Path to custom samples JSON file")

    args = parser.parse_args()

    if args.list_models:
        print("Available models:")
        for m in AVAILABLE_MODELS:
            print(f"  - {m}")
        return

    # Load prompt
    prompt_template = load_prompt(args.prompt)
    print(f"Prompt template loaded ({len(prompt_template)} chars)")

    # Default model
    model = args.model or AVAILABLE_MODELS[0]

    if args.interactive:
        interactive_test(model, prompt_template)
    elif args.compare:
        compare_models(AVAILABLE_MODELS[:3], prompt_template, SAMPLE_TRANSCRIPTS)
    else:
        test_model(model, prompt_template, SAMPLE_TRANSCRIPTS)


if __name__ == "__main__":
    main()
