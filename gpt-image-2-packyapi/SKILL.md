---
name: gpt-image-2-packyapi
description: Generate or edit images with PackyAPI's gpt-image-2 model using a local Python CLI, including prompt-to-image and image-edit workflows.
---

# GPT Image 2 PackyAPI

## Overview

Use this skill when the user wants to generate a new image or edit an existing image through PackyAPI's `gpt-image-2` model. The bundled script calls the OpenAI Images API endpoints directly: `/v1/images/generations` for text-to-image and `/v1/images/edits` for image editing.

## Setup

Set `PACKYAPI_API_KEY` and `PACKYAPI_BASE_URL` in the environment. The script also reads a local `.env` file if present. Copy `.env.example` to `.env` for local use.

## Usage

Choose one path:

```bash
python scripts/gpt_image.py generate --prompt "..." --size 1024x1024 --quality high
```

```bash
python scripts/gpt_image.py edit --image /path/to/input.png --prompt "..." --mask /path/to/mask.png --size 1024x1024
```

Rules:

- Use `generate` when there is no source image.
- Use `edit` when a source image is provided.
- Keep `n=1`; do not request multiple outputs in one call.
- Do not pass `response_format`; PackyAPI's gateway currently rejects it with HTTP 400 "Unknown parameter" and always returns `b64_json`. The script saves the result to `PACKYAPI_OUTPUT_DIR` automatically.
- Use valid 16-multiple sizes only; `auto` is allowed.
- For edits, pass one image at a time. Do not pass `input_fidelity`; PackyAPI's gateway currently rejects it for `gpt-image-2` with HTTP 400.
- Do not use Chat Completions or Responses API image paths for this model.

## Script behavior

The script validates size and request options, sends the correct PackyAPI request, downloads `url` responses or decodes `b64_json`, saves the result into `PACKYAPI_OUTPUT_DIR` or `./outputs`, and prints a compact JSON summary for the caller.

## Environment

See `.env.example` for the available variables. Keep the API key out of the repo.
