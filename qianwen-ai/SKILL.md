---
name: qianwen-ai
description: Use QianWen AI skills for Qwen/DashScope text, vision, image generation, video generation including HappyHorse and Wan models, audio TTS, model selection, usage queries, and API key authentication.
---

# QianWen AI

## Overview

Use this skill when the user wants to call QianWen/Qwen/DashScope capabilities from Codex: text generation, image generation/editing, video generation/editing, vision/OCR/video understanding, TTS, model selection, authentication, or usage/billing checks.

This is a thin local wrapper around the official QianWen-AI skill set vendored in:

`vendor/qianwen-ai-skills/`

## Dispatch

First choose the matching vendored sub-skill and read that sub-skill's `SKILL.md` before acting:

| User intent | Vendored skill |
| --- | --- |
| Configure or verify API keys, debug 401/auth errors | `vendor/qianwen-ai-skills/qianwen-ops-auth/SKILL.md` |
| Text generation, chat, code, reasoning, function calling | `vendor/qianwen-ai-skills/qianwen-text/SKILL.md` |
| Image/video understanding, OCR, chart analysis | `vendor/qianwen-ai-skills/qianwen-vision/SKILL.md` |
| Text-to-image, image editing, style transfer | `vendor/qianwen-ai-skills/qianwen-image-generation/SKILL.md` |
| Text-to-video, image-to-video, HappyHorse/Wan video generation or editing | `vendor/qianwen-ai-skills/qianwen-video-generation/SKILL.md` |
| Text-to-speech | `vendor/qianwen-ai-skills/qianwen-audio-tts/SKILL.md` |
| Pick an appropriate QianWen model | `vendor/qianwen-ai-skills/qianwen-model-selector/SKILL.md` |
| Usage, quota, subscription, billing queries | `vendor/qianwen-ai-skills/qianwen-usage/SKILL.md` |
| Check for QianWen skill updates | `vendor/qianwen-ai-skills/qianwen-update-check/SKILL.md` |

When multiple capabilities are involved, load the auth sub-skill first only if credentials are missing or failing, then load the task-specific sub-skill.

## Execution Rules

- Use absolute script paths from the vendored sub-skill directory.
- Run generated artifacts in the current working directory, normally under `output/<sub-skill-name>/`.
- Never write generated output, API responses, or user media into this skill directory or any `vendor/` skill directory.
- Do not print API keys or credentials. Report only non-secret status such as `set`, `missing`, `valid`, or HTTP status.
- Credentials should come from `DASHSCOPE_API_KEY` or `QIANWEN_API_KEY` in the environment or from a `.env` in the current working directory. Do not commit `.env` files.
- For video generation, tasks are asynchronous: submit, poll until terminal status, download the result, then verify the local file is non-empty.

## Notes

The vendored QianWen skills are copied from `QianWen-AI/qianwen-ai`. Treat their `SKILL.md`, `references/`, and `scripts/` as the source of truth for exact model parameters, endpoints, limits, and fallback workflows.
