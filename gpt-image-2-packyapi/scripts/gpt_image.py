#!/usr/bin/env python3
"""Generate or edit images with PackyAPI gpt-image-2."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4


DEFAULT_BASE_URL = "https://www.packyapi.com"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_OUTPUT_DIR = "./outputs"
DEFAULT_TIMEOUT_SECONDS = 300
VALID_QUALITY = {"auto", "low", "medium", "high"}
VALID_RESPONSE_FORMAT = {"url", "b64_json"}
VALID_OUTPUT_FORMAT = {"png", "jpeg"}
VALID_BACKGROUND = {"opaque"}
VALID_MODERATION = {"auto", "low"}
VALID_INPUT_FIDELITY = {"high", "low"}
SIZE_RE = re.compile(r"^(\d+)x(\d+)$")


class GptImageError(Exception):
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


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise GptImageError(f"{name} must be an integer") from exc


def normalize_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise GptImageError("PACKYAPI_BASE_URL cannot be empty")
    return value


def validate_size(size: str) -> None:
    if size == "auto":
        return

    match = SIZE_RE.match(size)
    if not match:
        raise GptImageError("size must be auto or WIDTHxHEIGHT, for example 1024x1024")

    width = int(match.group(1))
    height = int(match.group(2))
    long_edge = max(width, height)
    short_edge = min(width, height)
    pixels = width * height

    if width % 16 or height % 16:
        raise GptImageError("size width and height must be multiples of 16")
    if long_edge > 3840:
        raise GptImageError("size max edge must be <= 3840")
    if long_edge / short_edge > 3:
        raise GptImageError("size aspect ratio must be <= 3:1")
    if pixels < 655_360 or pixels > 8_294_400:
        raise GptImageError("size total pixels must be between 655360 and 8294400")


def validate_common(args: argparse.Namespace) -> None:
    validate_size(args.size)
    if args.quality not in VALID_QUALITY:
        raise GptImageError(f"quality must be one of {sorted(VALID_QUALITY)}")
    if args.response_format not in VALID_RESPONSE_FORMAT:
        raise GptImageError(f"response_format must be one of {sorted(VALID_RESPONSE_FORMAT)}")
    if args.output_format not in VALID_OUTPUT_FORMAT:
        raise GptImageError("output_format should be png or jpeg")
    if args.output_compression is not None:
        if args.output_format != "jpeg":
            raise GptImageError("output_compression should only be used with output_format=jpeg")
        if not 0 <= args.output_compression <= 100:
            raise GptImageError("output_compression must be between 0 and 100")
    if args.background and args.background not in VALID_BACKGROUND:
        raise GptImageError("background=transparent is not supported; use opaque or omit it")
    if args.moderation and args.moderation not in VALID_MODERATION:
        raise GptImageError(f"moderation must be one of {sorted(VALID_MODERATION)}")


def api_headers(api_key: str, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "*/*",
        "Connection": "keep-alive",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def request_json(
    url: str,
    api_key: str,
    payload: dict[str, object],
    timeout_seconds: int,
) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers=api_headers(api_key, "application/json"),
        method="POST",
    )
    return parse_response(request, timeout_seconds)


def encode_multipart(
    fields: dict[str, object],
    files: dict[str, Path],
) -> tuple[bytes, str]:
    boundary = f"----gpt-image-2-packyapi-{uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                f"{value}\r\n".encode("utf-8"),
            ]
        )

    for name, path in files.items():
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{path.name}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                path.read_bytes(),
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def request_multipart(
    url: str,
    api_key: str,
    fields: dict[str, object],
    files: dict[str, Path],
    timeout_seconds: int,
) -> dict[str, object]:
    body, content_type = encode_multipart(fields, files)
    request = urllib.request.Request(
        url,
        data=body,
        headers=api_headers(api_key, content_type),
        method="POST",
    )
    return parse_response(request, timeout_seconds)


def parse_response(request: urllib.request.Request, timeout_seconds: int) -> dict[str, object]:
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GptImageError(f"PackyAPI HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GptImageError(f"PackyAPI request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        preview = raw[:300].decode("utf-8", errors="replace")
        raise GptImageError(f"PackyAPI returned non-JSON response: {preview}") from exc

    if not isinstance(parsed, dict):
        raise GptImageError("PackyAPI returned an unexpected non-object JSON response")
    return parsed


def make_output_path(output_dir: Path, output_format: str, prefix: str) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = "jpg" if output_format == "jpeg" else output_format
    return output_dir / f"{prefix}-{timestamp}-{uuid4().hex[:8]}.{suffix}"


def save_result(
    response: dict[str, object],
    output_dir: Path,
    output_format: str,
    prefix: str,
    timeout_seconds: int,
) -> dict[str, object]:
    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise GptImageError("PackyAPI response did not include data[0]")

    item = data[0]
    if not isinstance(item, dict):
        raise GptImageError("PackyAPI response data[0] was not an object")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = make_output_path(output_dir, output_format, prefix)

    if isinstance(item.get("b64_json"), str):
        output_path.write_bytes(base64.b64decode(item["b64_json"]))
    elif isinstance(item.get("url"), str):
        download_file(item["url"], output_path, timeout_seconds)
    else:
        raise GptImageError("PackyAPI response data[0] did not include url or b64_json")

    return {
        "output_path": str(output_path.resolve()),
        "url": item.get("url"),
        "revised_prompt": item.get("revised_prompt"),
        "created": response.get("created"),
    }


def download_file(url: str, output_path: Path, timeout_seconds: int) -> None:
    request = urllib.request.Request(url, headers={"Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            output_path.write_bytes(response.read())
    except urllib.error.URLError as exc:
        raise GptImageError(f"Failed to download generated image: {exc.reason}") from exc


def common_payload(args: argparse.Namespace, model: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": model,
        "prompt": args.prompt,
        "n": 1,
        "size": args.size,
        "quality": args.quality,
        "output_format": args.output_format,
        "response_format": args.response_format,
    }
    optional_fields = {
        "output_compression": args.output_compression,
        "background": args.background,
        "moderation": args.moderation,
        "user": args.user,
    }
    payload.update({key: value for key, value in optional_fields.items() if value is not None})
    return payload


def resolve_settings(args: argparse.Namespace) -> tuple[str, str, str, Path, int]:
    skill_dir = Path(__file__).resolve().parents[1]
    load_dotenv(skill_dir / ".env")
    load_dotenv(Path.cwd() / ".env")

    api_key = args.api_key or os.getenv("PACKYAPI_API_KEY")
    if not api_key:
        raise GptImageError("PACKYAPI_API_KEY is required")

    base_url = normalize_base_url(args.base_url or os.getenv("PACKYAPI_BASE_URL", DEFAULT_BASE_URL))
    model = args.model or os.getenv("PACKYAPI_MODEL", DEFAULT_MODEL)
    output_dir = Path(args.output_dir or os.getenv("PACKYAPI_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    timeout_seconds = args.timeout_seconds or env_int(
        "PACKYAPI_TIMEOUT_SECONDS",
        DEFAULT_TIMEOUT_SECONDS,
    )
    return api_key, base_url, model, output_dir, timeout_seconds


def generate(args: argparse.Namespace) -> dict[str, object]:
    validate_common(args)
    api_key, base_url, model, output_dir, timeout_seconds = resolve_settings(args)
    payload = common_payload(args, model)
    response = request_json(
        f"{base_url}/v1/images/generations",
        api_key,
        payload,
        timeout_seconds,
    )
    result = save_result(response, output_dir, args.output_format, "generated", timeout_seconds)
    result.update({"mode": "generate", "model": model})
    return result


def edit(args: argparse.Namespace) -> dict[str, object]:
    validate_common(args)
    if args.input_fidelity and args.input_fidelity not in VALID_INPUT_FIDELITY:
        raise GptImageError(f"input_fidelity must be one of {sorted(VALID_INPUT_FIDELITY)}")

    image_path = Path(args.image)
    if not image_path.is_file():
        raise GptImageError(f"image file not found: {image_path}")

    files = {"image": image_path}
    if args.mask:
        mask_path = Path(args.mask)
        if not mask_path.is_file():
            raise GptImageError(f"mask file not found: {mask_path}")
        files["mask"] = mask_path

    api_key, base_url, model, output_dir, timeout_seconds = resolve_settings(args)
    fields = common_payload(args, model)
    if args.input_fidelity:
        fields["input_fidelity"] = args.input_fidelity

    response = request_multipart(
        f"{base_url}/v1/images/edits",
        api_key,
        fields,
        files,
        timeout_seconds,
    )
    result = save_result(response, output_dir, args.output_format, "edited", timeout_seconds)
    result.update({"mode": "edit", "model": model})
    return result


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prompt", required=True, help="Image prompt or edit instruction.")
    parser.add_argument("--size", default="auto", help="auto or WIDTHxHEIGHT.")
    parser.add_argument("--quality", default="auto", choices=sorted(VALID_QUALITY))
    parser.add_argument("--response-format", default="url", choices=sorted(VALID_RESPONSE_FORMAT))
    parser.add_argument("--output-format", default="png", choices=sorted(VALID_OUTPUT_FORMAT))
    parser.add_argument("--output-compression", type=int)
    parser.add_argument("--background")
    parser.add_argument("--moderation", choices=sorted(VALID_MODERATION))
    parser.add_argument("--user")
    parser.add_argument("--api-key")
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--output-dir")
    parser.add_argument("--timeout-seconds", type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Create an image from text.")
    add_common_args(generate_parser)
    generate_parser.set_defaults(func=generate)

    edit_parser = subparsers.add_parser("edit", help="Edit an existing image.")
    add_common_args(edit_parser)
    edit_parser.add_argument("--image", required=True, help="Input image path.")
    edit_parser.add_argument("--mask", help="Optional PNG mask path.")
    edit_parser.add_argument("--input-fidelity", default="high", choices=sorted(VALID_INPUT_FIDELITY))
    edit_parser.set_defaults(func=edit)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.func(args)
    except GptImageError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
