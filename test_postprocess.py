#!/usr/bin/env python3
"""
Quick test harness for post-processing model.
Usage: python test_postprocess.py

Loads the model once, then loops: paste/type input, see output.
"""
import time
import sys

# Suppress tokenizer parallelism warning
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler

MODEL = "mlx-community/gemma-4-e4b-it-4bit"

# Default prompt - edit this to iterate
PROMPT_TEMPLATE = """Lightly clean up this transcribed speech. Remove filler words, stutters, and fix grammar. Preserve the speaker's voice and meaning. Do not rewrite or restructure. Output ONLY the cleaned text.

{text}"""


def process(model, tokenizer, text, prompt_template=PROMPT_TEMPLATE):
    user_message = prompt_template.format(text=text)
    messages = [{"role": "user", "content": user_message}]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
        enable_thinking=False,
    )

    sampler = make_sampler(temp=0.1)
    t0 = time.time()
    result = generate(
        model, tokenizer,
        prompt=prompt,
        max_tokens=min(len(text.split()) * 3, 800),
        sampler=sampler,
    )
    elapsed = time.time() - t0

    return result.strip(), elapsed


def main():
    print(f"Loading {MODEL}...")
    t0 = time.time()
    model, tokenizer = load(MODEL)
    print(f"Model loaded in {time.time()-t0:.1f}s\n")

    print("=" * 60)
    print("Post-processing test harness")
    print("Paste/type transcription text, then press Enter twice (empty line) to process.")
    print("Type 'q' to quit, 'p' to change prompt template.")
    print("=" * 60)

    prompt_template = PROMPT_TEMPLATE

    while True:
        print("\n--- INPUT (empty line to process, 'q' to quit, 'p' to edit prompt) ---")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line == 'q' and not lines:
                print("Bye!")
                return
            if line == 'p' and not lines:
                print("Enter new prompt template ({text} = placeholder):")
                print("(empty line to finish)")
                plines = []
                while True:
                    try:
                        pl = input()
                    except EOFError:
                        break
                    if pl == '':
                        break
                    plines.append(pl)
                if plines:
                    prompt_template = '\n'.join(plines)
                    print(f"\nPrompt updated ({len(prompt_template)} chars)")
                break
            if line == '':
                break
            lines.append(line)

        if not lines:
            continue

        text = ' '.join(lines)
        print(f"\n--- PROCESSING ({len(text.split())} words) ---")
        result, elapsed = process(model, tokenizer, text, prompt_template)

        print(f"\n--- OUTPUT ({elapsed:.1f}s, {len(result.split())} words) ---")
        print(result)
        print(f"\n--- DIFF: {len(text.split())}w -> {len(result.split())}w ({elapsed:.1f}s) ---")


if __name__ == "__main__":
    main()
