#!/usr/bin/env python3
"""Repair Codex history visibility after switching model providers.

Default mode is dry-run. Pass --apply to write changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


OLD_DEFAULT_MODELS = {"", "old", "old-model", "gpt-5", "gpt-5.1-codex"}


class RepairError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_info(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {
        "path": str(path),
        "size": st.st_size,
        "mtime": st.st_mtime,
        "sha256": sha256(path),
    }


def resolve_codex_home(value: str | None) -> Path:
    home = value or os.environ.get("CODEX_HOME") or "~/.codex"
    return Path(os.path.expandvars(home)).expanduser().resolve()


def read_config(codex_home: Path) -> tuple[str, str]:
    config = codex_home / "config.toml"
    provider = "openai"
    model = "gpt-5"
    if not config.exists():
        return provider, model

    raw = config.read_text(encoding="utf-8", errors="replace")
    if tomllib is not None:
        try:
            data = tomllib.loads(raw)
            provider = str(data.get("model_provider") or data.get("provider") or provider).strip() or provider
            model = str(data.get("model") or model).strip() or model
            return provider, model
        except Exception:
            pass

    for line in raw.splitlines():
        match = re.match(r"\s*(model_provider|provider|model)\s*=\s*['\"]([^'\"]+)['\"]", line)
        if not match:
            continue
        if match.group(1) in {"model_provider", "provider"}:
            provider = match.group(2).strip() or provider
        elif match.group(1) == "model":
            model = match.group(2).strip() or model
    return provider, model


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if path.exists():
            shutil.copystat(path, temp_path, follow_symlinks=False)
        temp_path.replace(path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def backup_file(src: Path, backup_dir: Path, codex_home: Path) -> Path | None:
    if not src.exists():
        return None
    dst = backup_dir / "files" / src.relative_to(codex_home)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def online_backup_db(state_db: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(state_db, timeout=30.0)
    try:
        source.execute("PRAGMA busy_timeout = 30000")
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def rollout_files(codex_home: Path) -> list[Path]:
    files: list[Path] = []
    for dirname in ("sessions", "archived_sessions"):
        root = codex_home / dirname
        if root.exists():
            files.extend(sorted(root.rglob("rollout-*.jsonl")))
    return files


def parse_rollout_meta(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    first_end = data.find(b"\n")
    if first_end == -1:
        first = data
        tail = b""
    else:
        first = data[: first_end + 1]
        tail = data[first_end + 1 :]
    record = json.loads(first.decode("utf-8-sig").rstrip("\r\n"))
    if not isinstance(record, dict) or record.get("type") != "session_meta":
        raise RepairError(f"first line is not session_meta: {path}")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    thread_id = str(payload.get("id") or record.get("id") or "").strip()
    provider = str(
        payload.get("model_provider")
        or payload.get("modelProvider")
        or payload.get("provider")
        or record.get("model_provider")
        or record.get("modelProvider")
        or record.get("provider")
        or ""
    ).strip()
    return {"path": path, "data": data, "tail": tail, "record": record, "thread_id": thread_id, "provider": provider}


def apply_provider_fields(record: dict[str, Any], provider: str, model: str) -> bool:
    changed = False
    targets: list[dict[str, Any]] = [record]
    if isinstance(record.get("payload"), dict):
        targets.append(record["payload"])

    for obj in targets:
        provider_keys = [key for key in ("model_provider", "modelProvider", "provider") if key in obj]
        if not provider_keys and obj is not record:
            provider_keys = ["model_provider"]
        for key in provider_keys:
            if obj.get(key) != provider:
                obj[key] = provider
                changed = True

        model_keys = [key for key in ("model", "model_name", "modelName") if key in obj]
        if not model_keys and obj is not record:
            model_keys = ["model"]
        for key in model_keys:
            current = str(obj.get(key) or "").strip()
            if current in OLD_DEFAULT_MODELS and obj.get(key) != model:
                obj[key] = model
                changed = True
    return changed


def json_line(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def iso_utc(value: Any) -> str:
    if value is None:
        return ""
    timestamp = int(value)
    if timestamp > 10_000_000_000:
        timestamp //= 1000
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_cwd(cwd: str) -> str:
    if cwd.startswith("\\\\?\\"):
        return cwd[4:]
    return cwd


def workspace_root(cwd: str, codex_home: Path) -> str:
    clean = normalize_cwd(cwd)
    if not clean:
        return ""
    try:
        clean_path = Path(clean).expanduser()
        documents_codex = Path.home() / "Documents" / "Codex"
        if str(clean_path).lower().startswith(str(documents_codex).lower()):
            return str(documents_codex)
        if str(clean_path).lower().startswith(str(codex_home).lower()):
            return str(codex_home)
        parts = clean_path.parts
        if len(parts) >= 2 and os.name == "nt":
            return str(Path(parts[0]) / parts[1])
        if len(parts) >= 3:
            return str(Path(parts[0]) / parts[1] / parts[2])
    except Exception:
        pass
    return clean


def run(args: argparse.Namespace) -> dict[str, Any]:
    codex_home = resolve_codex_home(args.codex_home)
    state_db = codex_home / "state_5.sqlite"
    session_index = codex_home / "session_index.jsonl"
    global_state = codex_home / ".codex-global-state.json"
    config = codex_home / "config.toml"
    backup_root = codex_home / "history-provider-migration-backups"

    if not codex_home.exists():
        raise RepairError(f"Codex home does not exist: {codex_home}")
    if not state_db.exists():
        raise RepairError(f"state_5.sqlite does not exist: {state_db}")

    config_provider, config_model = read_config(codex_home)
    target_provider = args.target_provider or config_provider
    target_model = args.target_model or config_model

    connection = sqlite3.connect(state_db, timeout=30.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        rows = connection.execute("SELECT * FROM threads ORDER BY updated_at DESC, id DESC").fetchall()
    finally:
        connection.close()

    threads = {str(row["id"]): dict(row) for row in rows}
    non_target_ids = {tid for tid, row in threads.items() if row.get("model_provider") != target_provider}
    to_update_db = sorted(tid for tid in non_target_ids if tid != args.current_thread_id)

    metas = []
    by_id: dict[str, list[Path]] = {}
    malformed = []
    for path in rollout_files(codex_home):
        try:
            meta = parse_rollout_meta(path)
            metas.append(meta)
            if meta["thread_id"]:
                by_id.setdefault(meta["thread_id"], []).append(path)
        except Exception as exc:
            malformed.append({"path": str(path), "error": str(exc)})

    duplicates = {tid: [str(path) for path in paths] for tid, paths in by_id.items() if len(paths) > 1}
    if duplicates:
        raise RepairError(f"duplicate rollout files found: {json.dumps(duplicates, ensure_ascii=False)}")

    path_fixes = []
    for tid, row in threads.items():
        rollout_path = str(row.get("rollout_path") or "")
        if rollout_path and Path(rollout_path).exists():
            continue
        if tid in by_id:
            path_fixes.append((str(by_id[tid][0]), tid))

    to_update_rollouts = [
        meta
        for meta in metas
        if meta["thread_id"] != args.current_thread_id
        and (meta["thread_id"] in non_target_ids or (meta["provider"] and meta["provider"] != target_provider))
    ]

    result: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry-run",
        "codex_home": str(codex_home),
        "target_provider": target_provider,
        "target_model": target_model,
        "threads_total": len(threads),
        "db_threads_to_update": len(to_update_db),
        "db_rollout_path_fixes": len(path_fixes),
        "rollout_files_seen": len(metas),
        "rollout_files_to_update": len(to_update_rollouts),
        "malformed_rollouts": malformed,
    }

    if not args.apply:
        return result

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = backup_root / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {"created_at": datetime.now(timezone.utc).isoformat(), "files": {}, "stats": result}

    online_backup_db(state_db, backup_dir / "files" / "state_5.sqlite")
    for path in (config, session_index, global_state, state_db.with_name("state_5.sqlite-wal"), state_db.with_name("state_5.sqlite-shm")):
        if path.exists():
            manifest["files"][str(path)] = file_info(path)
            backup_file(path, backup_dir, codex_home)
    for meta in to_update_rollouts:
        path = meta["path"]
        manifest["files"][str(path)] = file_info(path)
        backup_file(path, backup_dir, codex_home)

    connection = sqlite3.connect(state_db, timeout=30.0)
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("BEGIN IMMEDIATE")
        for tid in to_update_db:
            old_model = str(threads[tid].get("model") or "").strip()
            if old_model in OLD_DEFAULT_MODELS:
                connection.execute("UPDATE threads SET model_provider = ?, model = ? WHERE id = ?", (target_provider, target_model, tid))
            else:
                connection.execute("UPDATE threads SET model_provider = ? WHERE id = ?", (target_provider, tid))
        for new_path, tid in path_fixes:
            connection.execute("UPDATE threads SET rollout_path = ? WHERE id = ?", (new_path, tid))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()

    updated_rollouts = 0
    for meta in to_update_rollouts:
        record = json.loads(json.dumps(meta["record"], ensure_ascii=False))
        if not apply_provider_fields(record, target_provider, target_model):
            continue
        new_data = json_line(record).encode("utf-8") + meta["tail"]
        atomic_write_bytes(meta["path"], new_data)
        after = parse_rollout_meta(meta["path"])
        if after["tail"] != meta["tail"]:
            raise RepairError(f"rollout tail changed unexpectedly: {meta['path']}")
        updated_rollouts += 1

    connection = sqlite3.connect(state_db, timeout=30.0)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("SELECT * FROM threads ORDER BY updated_at DESC, id DESC").fetchall()
    finally:
        connection.close()

    entries = []
    hints = {}
    projectless = []
    documents_codex = Path.home() / "Documents" / "Codex"
    for row in rows:
        tid = str(row["id"])
        cwd = normalize_cwd(str(row["cwd"] or ""))
        if int(row["archived"] or 0) == 0:
            entry = {
                "id": tid,
                "thread_name": str(row["title"] or row["first_user_message"] or row["preview"] or tid),
                "updated_at": iso_utc(row["updated_at_ms"] if "updated_at_ms" in row.keys() and row["updated_at_ms"] else row["updated_at"]),
                "model_provider": target_provider,
                "model": str(row["model"] or target_model),
                "cwd": str(row["cwd"] or ""),
                "rollout_path": str(row["rollout_path"] or ""),
            }
            entries.append(entry)
            hints[tid] = workspace_root(cwd, codex_home)
            if cwd and str(Path(cwd)).lower().startswith(str(documents_codex).lower()):
                projectless.append(tid)

    atomic_write_text(session_index, "".join(json_line(entry) for entry in entries))

    if global_state.exists():
        state = json.loads(global_state.read_text(encoding="utf-8"))
        existing_hints = dict(state.get("thread-workspace-root-hints") or {})
        for tid in threads:
            existing_hints.pop(tid, None)
        existing_hints.update(hints)
        state["thread-workspace-root-hints"] = existing_hints
        state["projectless-thread-ids"] = projectless
        atomic_write_text(global_state, json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n")

    manifest["stats"]["rollout_files_updated"] = updated_rollouts
    manifest["stats"]["session_index_rows"] = len(entries)
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    result["backup_dir"] = str(backup_dir)
    result["manifest"] = str(manifest_path)
    result["rollout_files_updated"] = updated_rollouts
    result["session_index_rows"] = len(entries)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", help="Codex data directory. Defaults to CODEX_HOME or ~/.codex.")
    parser.add_argument("--target-provider", help="Provider to migrate history to. Defaults to config.toml provider.")
    parser.add_argument("--target-model", help="Model to use when old/default model fields must be filled.")
    parser.add_argument("--current-thread-id", default="", help="Thread id to avoid editing while this repair is running.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, run dry-run only.")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run flag for readability.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run cannot be used together")
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
