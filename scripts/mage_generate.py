#!/usr/bin/env python3
"""
Automate image generation on mage.space using Playwright.

Usage:
    # Single prompt
    python scripts/mage_generate.py "a cozy cabin in the mountains at sunset"

    # With options
    python scripts/mage_generate.py "a dragon flying over a castle" --model "Flux" --ratio "16:9"

    # Batch from markdown file (parses room-prompts.md format)
    python scripts/mage_generate.py --batch room-prompts.md

    # Save to specific directory
    python scripts/mage_generate.py "a sunset" --output ./my-images

Batch mode reads a markdown file with entries like:

    ### Room Name
    **Ratio:** 16:9

    > Prompt text here...

Each prompt is generated 3x with FLUX.2 Dev, then 2x with Z-Image Turbo.

Prerequisites:
    pip install playwright
    playwright install chromium

The script uses your existing browser session (persistent context) so you
stay logged in to mage.space across runs.
"""

import argparse
import asyncio
import functools
import os
import re
import sys
import time
from pathlib import Path

# Force unbuffered output
print = functools.partial(print, flush=True)

from playwright.async_api import async_playwright


MAGE_URL = "https://www.mage.space/explore"
USER_DATA_DIR = os.path.expanduser("~/.mage-playwright-profile")


def parse_batch_markdown(filepath: str) -> list[dict]:
    """Parse a markdown file with ### Name, **Ratio:** X:Y, and > prompt entries.

    Returns a list of dicts with keys: name, ratio, prompt.
    """
    with open(filepath) as f:
        content = f.read()

    entries = []
    # Split on ### headers (level 3)
    sections = re.split(r"^### ", content, flags=re.MULTILINE)

    for section in sections[1:]:  # skip preamble before first ###
        lines = section.strip().split("\n")
        name = lines[0].strip()

        # Extract ratio
        ratio = None
        for line in lines:
            m = re.match(r"\*\*Ratio:\*\*\s*(\S+)", line)
            if m:
                ratio = m.group(1)
                break

        # Extract prompt (blockquote lines starting with >)
        prompt_lines = []
        for line in lines:
            if line.startswith(">"):
                prompt_lines.append(line.lstrip("> ").strip())

        if prompt_lines and ratio:
            prompt = " ".join(prompt_lines)
            entries.append({"name": name, "ratio": ratio, "prompt": prompt})

    return entries


async def wait_for_page_ready(page, timeout=60000):
    """Wait for the mage.space explore page to be fully loaded."""
    await page.wait_for_load_state("domcontentloaded", timeout=timeout)
    # Wait for either the prompt input or login link to appear
    await page.locator(
        "img[alt='Send'], a[href='/profile']:has-text('Login')"
    ).first.wait_for(state="visible", timeout=timeout)


async def select_model(page, model_name: str):
    """Click the model selector and choose a model by opening the model dialog."""
    # The model button is the first button in the row next to the Send button.
    # Find it by locating the Send img and navigating to sibling buttons.
    send_img = page.locator("img[alt='Send']")
    await send_img.wait_for(state="visible", timeout=10000)

    # The prompt bar contains the Send button. The model button is a sibling
    # button in the same container row.
    prompt_bar = send_img.locator("xpath=ancestor::*[2]")
    model_btn = prompt_bar.locator("button").first
    try:
        await model_btn.scroll_into_view_if_needed()
        await model_btn.click(timeout=5000)
    except Exception as e:
        print(f"  Warning: Could not click model button: {e}")
        return
    await page.wait_for_timeout(500)

    # Wait for the model dialog to appear
    dialog = page.locator("dialog")
    try:
        await dialog.wait_for(state="visible", timeout=5000)
    except Exception:
        print(f"  Warning: Model dialog did not appear")
        await page.keyboard.press("Escape")
        return

    # Find and click the model within the dialog
    model_option = dialog.locator(f"text={model_name}").first
    try:
        await model_option.click(timeout=5000)
        await page.wait_for_timeout(500)
    except Exception:
        print(f"  Warning: Could not find model '{model_name}', using default")
        await page.keyboard.press("Escape")


async def select_aspect_ratio(page, ratio: str):
    """Click the aspect ratio selector and choose a ratio from the dialog."""
    # The ratio button is in the bottom prompt bar, shows current ratio like "4:5"
    ratio_btn = page.locator(
        "button:has-text('4:5'), button:has-text('1:1'), button:has-text('16:9'), button:has-text('9:16'), button:has-text('3:2'), button:has-text('2:3'), button:has-text('5:4')"
    ).first
    await ratio_btn.click()
    await page.wait_for_timeout(500)

    # Wait for the aspect ratio dialog
    dialog = page.locator("dialog")
    try:
        await dialog.wait_for(state="visible", timeout=5000)
    except Exception:
        print(f"  Warning: Ratio dialog did not appear")
        await page.keyboard.press("Escape")
        return

    # Find and click the ratio button within the dialog
    ratio_option = dialog.get_by_role("button", name=ratio, exact=True)
    try:
        await ratio_option.click(timeout=3000)
        await page.wait_for_timeout(500)
    except Exception:
        print(f"  Warning: Could not find ratio '{ratio}', using default")
        await page.keyboard.press("Escape")


async def generate_image(
    page,
    prompt: str,
    model: str = None,
    ratio: str = None,
    output_dir: Path = None,
    name: str = None,
):
    """Generate a single image from a prompt.

    Returns the path to the saved image, or None if saving was skipped.
    """
    print(f"\n--- Generating: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

    # Optionally change model
    if model:
        print(f"  Model: {model}")
        await select_model(page, model)

    # Optionally change aspect ratio
    if ratio:
        print(f"  Ratio: {ratio}")
        await select_aspect_ratio(page, ratio)

    # Clear and type the prompt — the input is a contenteditable paragraph
    # Try multiple selectors to find the prompt input
    prompt_el = None
    selectors = [
        "div[contenteditable='true']",
        "[contenteditable='true'] p",
        "p[data-placeholder]",
        "div[role='textbox']",
        "[placeholder*='Describe']",
    ]
    for sel in selectors:
        loc = page.locator(sel).first
        if await loc.count() > 0 and await loc.is_visible():
            prompt_el = loc
            print(f"  Found prompt input via: {sel}")
            break

    if not prompt_el:
        # Fallback: click just above the Send button
        print("  Using fallback: clicking near Send button")
        send_box = await page.locator("img[alt='Send']").bounding_box()
        if send_box:
            # Click to the left of the send button (in the prompt area)
            await page.mouse.click(send_box["x"] - 200, send_box["y"])
            prompt_el = None  # we already clicked
        else:
            raise RuntimeError("Cannot find prompt input or Send button")
    else:
        await prompt_el.click()
    await page.wait_for_timeout(200)

    # Select all and delete to clear any previous text
    await page.keyboard.press("Meta+a")
    await page.keyboard.press("Backspace")
    await page.wait_for_timeout(200)

    # Type the prompt character by character (contenteditable needs this)
    await page.keyboard.type(prompt, delay=10)
    await page.wait_for_timeout(300)

    # Click send
    send_btn = page.locator("img[alt='Send']")
    await send_btn.click()
    print("  Submitted, waiting for generation...")

    # Wait for generation to complete by watching the "Generating: X / 10" text
    # First wait for it to appear (confirms generation started)
    generating_text = page.get_by_text("Generating:")
    try:
        await generating_text.first.wait_for(state="visible", timeout=15000)
        print("  Generation started...")
    except Exception:
        print("  Warning: Generation may not have started, checking sidebar...")

    # Now wait for it to disappear (generation complete) — up to 5 minutes for slow models
    try:
        await generating_text.first.wait_for(state="hidden", timeout=300000)
    except Exception:
        print("  Warning: Generation may have timed out after 5 min")
        return None

    # Also wait for the sidebar image to confirm
    sidebar_img = page.locator("img[alt='Mage media']")
    try:
        await sidebar_img.first.wait_for(state="visible", timeout=10000)
    except Exception:
        print("  Warning: Sidebar image not found, but generation text disappeared")

    print("  Generation complete!")
    await page.wait_for_timeout(500)

    # Click the generated image in the sidebar to open detail view
    filepath = None
    try:
        await sidebar_img.first.click(timeout=5000)
        await page.wait_for_timeout(1000)

        # Click "Save" to save it to your mage.space account
        save_btn = page.get_by_role("button", name="Save")
        await save_btn.click(timeout=5000)
        # Wait for the button to change to "Success"
        await page.get_by_text("Success").first.wait_for(state="visible", timeout=10000)
        print("  Saved to mage.space account!")

        # Download locally if output_dir specified
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            detail_img = page.locator("img[alt='Mage media']").first
            src = await detail_img.get_attribute("src", timeout=5000)
            if src:
                if name:
                    safe_name = "".join(
                        c if c.isalnum() or c in " -_" else "_" for c in name
                    )
                else:
                    safe_name = "".join(
                        c if c.isalnum() or c in " -_" else "_" for c in prompt[:50]
                    )
                timestamp = int(time.time())
                filename = f"{safe_name}_{timestamp}.jpg"
                filepath = output_dir / filename

                response = await page.request.get(src)
                body = await response.body()
                filepath.write_bytes(body)
                print(f"  Downloaded: {filepath}")

        # Close the detail view with Escape (Close button may not be visible)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

        return str(filepath) if filepath else "saved"

    except Exception as e:
        print(f"  Warning: Could not save/download image: {e}")
        # Try to close any open detail view
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

    return None


async def main():
    parser = argparse.ArgumentParser(description="Generate images on mage.space")
    parser.add_argument("prompt", nargs="?", help="Text prompt for image generation")
    parser.add_argument(
        "--batch",
        type=str,
        help="Markdown file with ### Name, **Ratio:**, and > prompt entries (e.g. room-prompts.md)",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Model name for single-prompt mode (batch mode uses FLUX.2 Dev 3x + Z-Image Turbo 2x)",
    )
    parser.add_argument(
        "--ratio", type=str, help="Aspect ratio (e.g. '1:1', '16:9', '4:5')"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="./mage-output",
        help="Output directory for saved images",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (no visible browser)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=60.0,
        help="Delay between batch generations (seconds)",
    )
    args = parser.parse_args()

    if not args.prompt and not args.batch:
        parser.error("Provide a prompt or --batch file")

    # Collect prompts
    prompts = []
    if args.batch:
        prompts = parse_batch_markdown(args.batch)
        print(f"Loaded {len(prompts)} prompts from {args.batch}")
        for entry in prompts:
            print(f"  - {entry['name']} (ratio: {entry['ratio']})")
    else:
        prompts = [{"name": "prompt", "ratio": args.ratio, "prompt": args.prompt}]

    output_dir = Path(args.output)

    # Build generation plan: each prompt N times per model
    MODELS = [
        ("Flux 2 Dev", 3),
        ("Z-Image Turbo", 2),
    ]

    total_generations = len(prompts) * sum(count for _, count in MODELS)
    print(
        f"\nGeneration plan: {len(prompts)} prompts x {len(MODELS)} models = {total_generations} total images"
    )
    for model_name, count in MODELS:
        print(f"  {model_name}: {count}x each prompt")

    async with async_playwright() as p:
        # Use persistent context to preserve login session
        browser = await p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=args.headless,
            viewport={"width": 1280, "height": 900},
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        print(f"\nNavigating to {MAGE_URL}...")
        await page.goto(MAGE_URL, wait_until="domcontentloaded")
        await wait_for_page_ready(page)
        print("Page ready!")

        # Check if logged in by looking for the Send button (only visible when logged in)
        send_visible = await page.locator("img[alt='Send']").is_visible()
        if not send_visible:
            print("\nNot logged in! Please log in manually in the browser window.")
            print("The script will continue once you're logged in (up to 5 min)...")
            await page.locator("img[alt='Send']").wait_for(
                state="visible", timeout=300000
            )
            print("Login detected, continuing...")
        else:
            print("Logged in!")

        results = []
        gen_num = 0

        for model_name, count in MODELS:
            print(f"\n{'='*60}")
            print(f"MODEL: {model_name} ({count}x per prompt)")
            print(f"{'='*60}")

            # Select model once per model batch
            await select_model(page, model_name)
            await page.wait_for_timeout(500)

            for entry in prompts:
                for run in range(1, count + 1):
                    gen_num += 1
                    print(
                        f"\n[{gen_num}/{total_generations}] {entry['name']} — {model_name} (run {run}/{count})"
                    )

                    if gen_num > 1:
                        await asyncio.sleep(args.delay)

                    try:
                        result = await generate_image(
                            page,
                            entry["prompt"],
                            model=None,  # already selected above
                            ratio=entry["ratio"],
                            output_dir=output_dir,
                            name=entry.get("name"),
                        )
                    except Exception as e:
                        print(f"  ERROR: {e}")
                        print("  Waiting 60s, then restarting browser...")
                        await asyncio.sleep(60)
                        try:
                            await browser.close()
                        except Exception:
                            pass
                        browser = await p.chromium.launch_persistent_context(
                            USER_DATA_DIR,
                            headless=args.headless,
                            viewport={"width": 1280, "height": 900},
                        )
                        page = (
                            browser.pages[0]
                            if browser.pages
                            else await browser.new_page()
                        )
                        await page.goto(MAGE_URL, wait_until="domcontentloaded")
                        await wait_for_page_ready(page)
                        # Re-select model after browser restart
                        await select_model(page, model_name)
                        await page.wait_for_timeout(500)
                        result = None

                    results.append(
                        {
                            "name": entry["name"],
                            "model": model_name,
                            "run": run,
                            "prompt": entry["prompt"],
                            "file": result,
                        }
                    )

        print(f"\n{'='*60}")
        print(f"Done! Generated {len(results)} image(s)")
        print(f"{'='*60}")
        for r in results:
            status = f"-> {r['file']}" if r["file"] else "(not saved)"
            print(f"  {r['name']} [{r['model']} #{r['run']}]: {status}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
