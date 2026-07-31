#!/usr/bin/env python3
"""Submit and poll Seedance 2 tasks through KieAI."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4


DEFAULT_BASE_URL = "https://api.kie.ai"
DEFAULT_MODEL = "bytedance/seedance-2"
DEFAULT_OUTPUT_DIR = "./outputs/kieai-seedance"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60
DEFAULT_WAIT_TIMEOUT_SECONDS = 1800
DEFAULT_POLL_INTERVAL_SECONDS = 10
MIN_DURATION = 4
MAX_DURATION = 15
VALID_MODELS = {"bytedance/seedance-2", "bytedance/seedance-2-fast"}
VALID_RESOLUTIONS = {"480p", "720p", "1080p", "4k"}
VALID_ASPECT_RATIOS = {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9"}
SLUG_RE = re.compile(r"[^a-z0-9]+")


class KieaiSeedanceError(Exception):
    """Raised for user-actionable API or validation failures."""


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_environment() -> None:
    skill_dir = Path(__file__).resolve().parent.parent
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(skill_dir / ".env")


def env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise KieaiSeedanceError(f"{name} must be an integer") from exc


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise KieaiSeedanceError(f"{name} must be a boolean value")


def normalize_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise KieaiSeedanceError("base URL cannot be empty")
    return value


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def api_headers(api_key: str, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Connection": "keep-alive",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def api_request(
    method: str,
    url: str,
    api_key: str,
    timeout_seconds: int,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    data = None
    headers = api_headers(api_key)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise KieaiSeedanceError(f"KieAI HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise KieaiSeedanceError(f"KieAI request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        preview = raw[:300].decode("utf-8", errors="replace")
        raise KieaiSeedanceError(f"KieAI returned non-JSON response: {preview}") from exc

    if not isinstance(parsed, dict):
        raise KieaiSeedanceError("KieAI returned an unexpected non-object JSON response")
    return parsed


def ensure_success(response: dict[str, object]) -> dict[str, object]:
    code = response.get("code")
    if code != 200:
        msg = response.get("msg") or "unknown error"
        raise KieaiSeedanceError(f"KieAI API error {code}: {msg}")

    data = response.get("data")
    if not isinstance(data, dict):
        raise KieaiSeedanceError("KieAI response did not include a data object")
    return data


def normalize_urls(raw_urls: list[str], *, field_name: str, max_items: int | None = None) -> list[str]:
    cleaned: list[str] = []
    for raw_url in raw_urls:
        url = raw_url.strip()
        if not url:
            continue
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise KieaiSeedanceError(f"{field_name} must contain HTTP or HTTPS URLs")
        cleaned.append(url)

    if max_items is not None and len(cleaned) > max_items:
        raise KieaiSeedanceError(f"{field_name} supports at most {max_items} URLs")
    return cleaned


def slugify_model(model: str) -> str:
    base = model.split("/", 1)[-1].lower()
    slug = SLUG_RE.sub("-", base).strip("-")
    return slug or "seedance"


def make_output_path(output_dir: Path, model: str, task_id: str, url: str, index: int) -> Path:
    suffix = Path(urllib.parse.urlparse(url).path).suffix or ".mp4"
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    short_task_id = task_id[:8] if task_id else uuid4().hex[:8]
    return output_dir / f"{slugify_model(model)}-{timestamp}-{short_task_id}-{index}{suffix}"


def download_file(url: str, output_path: Path, timeout_seconds: int) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "*/*",
            "User-Agent": "curl/8.7.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            output_path.write_bytes(response.read())
    except urllib.error.URLError as exc:
        raise KieaiSeedanceError(f"Failed to download generated media: {exc.reason}") from exc


def extract_result_urls(result_json: object) -> list[str]:
    if isinstance(result_json, str):
        try:
            parsed = json.loads(result_json)
        except json.JSONDecodeError as exc:
            raise KieaiSeedanceError("KieAI resultJson was not valid JSON") from exc
    elif isinstance(result_json, dict):
        parsed = result_json
    else:
        raise KieaiSeedanceError("KieAI resultJson had an unexpected type")

    if not isinstance(parsed, dict):
        raise KieaiSeedanceError("KieAI resultJson did not decode to an object")

    result_urls = parsed.get("resultUrls")
    if result_urls is None:
        return []
    if not isinstance(result_urls, list):
        raise KieaiSeedanceError("KieAI resultJson.resultUrls was not a list")

    cleaned: list[str] = []
    for item in result_urls:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
    return cleaned


def build_input_payload(args: argparse.Namespace) -> dict[str, object]:
    payload: dict[str, object] = {
        "prompt": args.prompt,
        "generate_audio": args.generate_audio,
        "resolution": args.resolution,
        "aspect_ratio": args.aspect_ratio,
        "duration": args.duration,
        "web_search": args.web_search,
        "nsfw_checker": args.nsfw_checker,
    }

    reference_image_urls = normalize_urls(
        list(args.reference_image_url),
        field_name="reference-image-url",
    )
    reference_video_urls = normalize_urls(
        list(args.reference_video_url),
        field_name="reference-video-url",
        max_items=3,
    )
    reference_audio_urls = normalize_urls(
        list(args.reference_audio_url),
        field_name="reference-audio-url",
        max_items=3,
    )

    if reference_image_urls:
        payload["reference_image_urls"] = reference_image_urls
    if reference_video_urls:
        payload["reference_video_urls"] = reference_video_urls
    if reference_audio_urls:
        payload["reference_audio_urls"] = reference_audio_urls

    return payload


def validate_generation_args(args: argparse.Namespace) -> None:
    if not args.prompt or not args.prompt.strip():
        raise KieaiSeedanceError("prompt cannot be empty")
    if args.model not in VALID_MODELS:
        raise KieaiSeedanceError(f"model must be one of {sorted(VALID_MODELS)}")
    if args.resolution not in VALID_RESOLUTIONS:
        raise KieaiSeedanceError(f"resolution must be one of {sorted(VALID_RESOLUTIONS)}")
    if args.aspect_ratio not in VALID_ASPECT_RATIOS:
        raise KieaiSeedanceError(f"aspect_ratio must be one of {sorted(VALID_ASPECT_RATIOS)}")
    if not MIN_DURATION <= args.duration <= MAX_DURATION:
        raise KieaiSeedanceError(f"duration must be between {MIN_DURATION} and {MAX_DURATION}")
    if args.output_dir.strip() == "":
        raise KieaiSeedanceError("output_dir cannot be empty")


def submit_task(
    api_key: str,
    base_url: str,
    timeout_seconds: int,
    model: str,
    input_payload: dict[str, object],
    callback_url: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": model,
        "input": input_payload,
    }
    if callback_url:
        payload["callBackUrl"] = callback_url
    return api_request(
        "POST",
        f"{base_url}/api/v1/jobs/createTask",
        api_key,
        timeout_seconds,
        payload,
    )


def poll_task(
    api_key: str,
    base_url: str,
    timeout_seconds: int,
    task_id: str,
) -> dict[str, object]:
    query = urllib.parse.urlencode({"taskId": task_id})
    return api_request(
        "GET",
        f"{base_url}/api/v1/jobs/recordInfo?{query}",
        api_key,
        timeout_seconds,
    )


def download_results(
    result_urls: list[str],
    output_dir: Path,
    model: str,
    task_id: str,
    timeout_seconds: int,
) -> list[dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, str]] = []

    for index, url in enumerate(result_urls, start=1):
        output_path = make_output_path(output_dir, model, task_id, url, index)
        download_file(url, output_path, timeout_seconds)
        if output_path.stat().st_size == 0:
            raise KieaiSeedanceError(f"Downloaded file was empty: {output_path}")
        downloaded.append({"url": url, "path": str(output_path.resolve())})

    return downloaded


def summarize_response(
    response: dict[str, object],
    *,
    downloaded_files: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    data = ensure_success(response)
    summary: dict[str, object] = {
        "code": response.get("code"),
        "msg": response.get("msg"),
        "task_id": data.get("taskId"),
        "model": data.get("model"),
        "state": data.get("state"),
    }

    if data.get("failCode") is not None:
        summary["fail_code"] = data.get("failCode")
    if data.get("failMsg") is not None:
        summary["fail_msg"] = data.get("failMsg")
    if data.get("costTime") is not None:
        summary["cost_time"] = data.get("costTime")
    if data.get("completeTime") is not None:
        summary["complete_time"] = data.get("completeTime")

    result_json = data.get("resultJson")
    if result_json is not None:
        summary["result_json"] = result_json
        try:
            result_urls = extract_result_urls(result_json)
        except KieaiSeedanceError:
            result_urls = []
        if result_urls:
            summary["result_urls"] = result_urls

    if downloaded_files:
        summary["downloaded_files"] = downloaded_files

    return summary


def print_summary(summary: dict[str, object]) -> None:
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Submit and poll Seedance 2 tasks through KieAI.")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--base-url",
        default=env_str("KIEAI_BASE_URL", DEFAULT_BASE_URL),
        help="KieAI API base URL",
    )
    common.add_argument(
        "--api-key",
        default=env_str("KIEAI_API_KEY", ""),
        help="KieAI API key",
    )
    common.add_argument(
        "--request-timeout-seconds",
        type=positive_int,
        default=env_int("KIEAI_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS),
        help="HTTP request timeout in seconds",
    )

    generation = argparse.ArgumentParser(add_help=False)
    generation.add_argument(
        "--model",
        choices=sorted(VALID_MODELS),
        default=env_str("KIEAI_DEFAULT_MODEL", DEFAULT_MODEL),
        help="Seedance model to use",
    )
    generation.add_argument("--prompt", required=True, help="Video prompt")
    generation.add_argument(
        "--reference-image-url",
        action="append",
        default=[],
        help="Reference image URL (repeatable)",
    )
    generation.add_argument(
        "--reference-video-url",
        action="append",
        default=[],
        help="Reference video URL (repeatable)",
    )
    generation.add_argument(
        "--reference-audio-url",
        action="append",
        default=[],
        help="Reference audio URL (repeatable)",
    )
    gen_audio = generation.add_mutually_exclusive_group()
    gen_audio.add_argument(
        "--generate-audio",
        dest="generate_audio",
        action="store_true",
        help="Generate synced audio",
    )
    gen_audio.add_argument(
        "--no-generate-audio",
        dest="generate_audio",
        action="store_false",
        help="Disable synced audio",
    )
    generation.set_defaults(generate_audio=env_bool("KIEAI_GENERATE_AUDIO", True))

    resolution_group = generation.add_argument_group("output")
    resolution_group.add_argument(
        "--resolution",
        choices=sorted(VALID_RESOLUTIONS),
        default=env_str("KIEAI_RESOLUTION", "720p"),
        help="Output resolution",
    )
    resolution_group.add_argument(
        "--aspect-ratio",
        choices=sorted(VALID_ASPECT_RATIOS),
        default=env_str("KIEAI_ASPECT_RATIO", "16:9"),
        help="Output aspect ratio",
    )
    resolution_group.add_argument(
        "--duration",
        type=positive_int,
        default=env_int("KIEAI_DURATION", 15),
        help=f"Video duration in seconds ({MIN_DURATION}-{MAX_DURATION})",
    )
    web_search_group = generation.add_mutually_exclusive_group()
    web_search_group.add_argument(
        "--web-search",
        dest="web_search",
        action="store_true",
        help="Enable online search",
    )
    web_search_group.add_argument(
        "--no-web-search",
        dest="web_search",
        action="store_false",
        help="Disable online search",
    )
    generation.set_defaults(web_search=env_bool("KIEAI_WEB_SEARCH", False))
    nsfw_group = generation.add_mutually_exclusive_group()
    nsfw_group.add_argument(
        "--nsfw-checker",
        dest="nsfw_checker",
        action="store_true",
        help="Enable NSFW checker",
    )
    nsfw_group.add_argument(
        "--no-nsfw-checker",
        dest="nsfw_checker",
        action="store_false",
        help="Disable NSFW checker",
    )
    generation.set_defaults(nsfw_checker=env_bool("KIEAI_NSFW_CHECKER", True))
    generation.add_argument(
        "--callback-url",
        default=env_str("KIEAI_CALLBACK_URL", ""),
        help="Optional callback URL for task completion",
    )
    generation.add_argument(
        "--output-dir",
        default=env_str("KIEAI_OUTPUT_DIR", DEFAULT_OUTPUT_DIR),
        help="Directory for downloaded results",
    )

    submit = parser.add_subparsers(dest="command", required=True)

    submit_parser = submit.add_parser("submit", parents=[common, generation], help="Submit a task and print the task ID")
    submit_parser.set_defaults(handler=handle_submit)

    run_parser = submit.add_parser("run", parents=[common, generation], help="Submit a task, poll until terminal state, and download results")
    run_parser.add_argument(
        "--wait-timeout-seconds",
        type=positive_int,
        default=env_int("KIEAI_WAIT_TIMEOUT_SECONDS", DEFAULT_WAIT_TIMEOUT_SECONDS),
        help="Maximum time to wait for a terminal task state",
    )
    run_parser.add_argument(
        "--poll-interval-seconds",
        type=positive_int,
        default=env_int("KIEAI_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS),
        help="Seconds to sleep between status checks",
    )
    run_parser.set_defaults(handler=handle_run)

    poll_parser = submit.add_parser("poll", parents=[common], help="Check the status of an existing task")
    poll_parser.add_argument("--task-id", required=True, help="Task ID returned by submit")
    poll_parser.set_defaults(handler=handle_poll)

    return parser


def get_api_key(args: argparse.Namespace) -> str:
    api_key = args.api_key.strip()
    if not api_key:
        raise KieaiSeedanceError("KIEAI_API_KEY is required")
    return api_key


def handle_submit(args: argparse.Namespace) -> int:
    validate_generation_args(args)
    base_url = normalize_base_url(args.base_url)
    api_key = get_api_key(args)
    input_payload = build_input_payload(args)

    response = submit_task(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=args.request_timeout_seconds,
        model=args.model,
        input_payload=input_payload,
        callback_url=args.callback_url.strip() or None,
    )

    summary = summarize_response(response)
    print_summary(summary)
    return 0


def handle_poll(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    api_key = get_api_key(args)
    task_id = args.task_id.strip()
    if not task_id:
        raise KieaiSeedanceError("task-id cannot be empty")

    response = poll_task(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=args.request_timeout_seconds,
        task_id=task_id,
    )
    summary = summarize_response(response)
    print_summary(summary)
    return 0


def handle_run(args: argparse.Namespace) -> int:
    validate_generation_args(args)
    base_url = normalize_base_url(args.base_url)
    api_key = get_api_key(args)
    input_payload = build_input_payload(args)
    output_dir = Path(args.output_dir)
    start_time = time.monotonic()

    submit_response = submit_task(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=args.request_timeout_seconds,
        model=args.model,
        input_payload=input_payload,
        callback_url=args.callback_url.strip() or None,
    )
    submit_data = ensure_success(submit_response)
    task_id = submit_data.get("taskId")
    if not isinstance(task_id, str) or not task_id.strip():
        raise KieaiSeedanceError("KieAI response did not include a taskId")
    task_id = task_id.strip()

    last_response = poll_task(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=args.request_timeout_seconds,
        task_id=task_id,
    )

    while True:
        data = ensure_success(last_response)
        state = data.get("state")
        if state in {"success", "fail"}:
            break
        if time.monotonic() - start_time > args.wait_timeout_seconds:
            raise KieaiSeedanceError("Timed out waiting for the KieAI task to finish")
        time.sleep(args.poll_interval_seconds)
        last_response = poll_task(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=args.request_timeout_seconds,
            task_id=task_id,
        )

    summary = summarize_response(last_response)

    data = ensure_success(last_response)
    state = data.get("state")
    if state == "fail":
        print_summary(summary)
        fail_code = data.get("failCode")
        fail_msg = data.get("failMsg") or "Seedance task failed"
        if fail_code is not None:
            raise KieaiSeedanceError(f"Seedance task failed ({fail_code}): {fail_msg}")
        raise KieaiSeedanceError(f"Seedance task failed: {fail_msg}")

    result_urls = extract_result_urls(data.get("resultJson"))
    downloaded_files = []
    if state == "success" and result_urls:
        downloaded_files = download_results(
            result_urls=result_urls,
            output_dir=output_dir,
            model=args.model,
            task_id=task_id,
            timeout_seconds=args.request_timeout_seconds,
        )
        summary = summarize_response(last_response, downloaded_files=downloaded_files)

    print_summary(summary)
    return 0


def main() -> int:
    load_environment()
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.handler(args)
    except KieaiSeedanceError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
