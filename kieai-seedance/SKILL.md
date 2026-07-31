---
name: kieai-seedance
description: Use KieAI to submit, poll, and download bytedance/seedance-2 and bytedance/seedance-2-fast video tasks.
---

# KieAI Seedance

## Overview

Use this skill when the user wants to generate Seedance videos through KieAI's intermediary API, especially for:

- `bytedance/seedance-2`
- `bytedance/seedance-2-fast`

The workflow is asynchronous:

1. Submit a generation task
2. Poll for status until the task reaches `success` or `fail`
3. Download the returned media URLs

## Setup

Set `KIEAI_API_KEY` in the environment or in a local `.env` file. Copy `.env.example` to `.env` for local use.

The script also reads `.env` from the current working directory and from this skill directory.

## Usage

Use the bundled script:

```bash
python scripts/seedance.py submit --model bytedance/seedance-2 --prompt "..."
```

```bash
python scripts/seedance.py run --model bytedance/seedance-2-fast --prompt "..."
```

```bash
python scripts/seedance.py poll --task-id YOUR_TASK_ID
```

Rules:

- Use `run` for the normal end-to-end flow.
- Use `submit` when you only need the task ID.
- Use `poll` when you already have a task ID and want to check status.
- Pass `--model bytedance/seedance-2` for the standard model or `--model bytedance/seedance-2-fast` for the fast variant.
- Keep reference media as hosted URLs; the API does not upload local files.
- Save generated files under the configured output directory, not inside the skill folder.

## API Notes

This skill uses:

- `POST https://api.kie.ai/api/v1/jobs/createTask`
- `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...`

The request body uses the KieAI `input` object, and the script downloads media from `resultJson.resultUrls` when a task succeeds.
