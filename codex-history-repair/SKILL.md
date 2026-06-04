---
name: codex-history-repair
description: Recover Codex Desktop or Codex CLI history after switching model providers, especially when old OpenAI/cc_switch/custom-provider conversations disappear from the current provider's history list. Use when Codex needs to inspect or repair ~/.codex / CODEX_HOME session metadata, state_5.sqlite, session_index.jsonl, .codex-global-state.json, sessions/**/rollout-*.jsonl, or archived_sessions after provider/model migration on Windows, Linux, or macOS.
---

# Codex History Repair

Use this skill to recover local Codex history visibility after a provider switch. The proven Windows case migrated historical `OpenAI` and `cc_switch` threads into the current `custom` provider by synchronizing provider metadata across SQLite, rollout session metadata, session index, and global workspace hints.

## Core Idea

Codex history is not stored in one place. Visibility depends on several metadata surfaces agreeing:

- `config.toml`: current default `model_provider` and `model`.
- `state_5.sqlite`: canonical thread metadata in the `threads` table.
- `sessions/**/rollout-*.jsonl`: per-thread records; the first line is `session_meta`.
- `archived_sessions/*.jsonl`: archived rollout files.
- `session_index.jsonl`: global non-archived history list.
- `.codex-global-state.json`: Desktop UI state, including projectless thread ids and workspace hints.

When a provider switch makes history disappear, migrate old provider metadata to the current target provider and rebuild derived indexes. Do not use symlinks for this problem.

## Safety Rules

1. Never delete history files.
2. Prefer dry-run first; require explicit user approval before applying if not already requested.
3. Back up before writing.
4. Use SQLite online backup for live `state_5.sqlite`; do not rely only on copying the database file when WAL files exist.
5. Modify rollout files only on the first `session_meta` line; never alter later conversation event lines.
6. Do not close Codex Desktop if the current agent is running inside it. Apply online, then ask the user to restart manually to verify.
7. If duplicate rollout files map to the same thread id, stop and report instead of guessing.

## Recommended Workflow

1. Locate Codex home:
   - Use `CODEX_HOME` if set.
   - Otherwise use `~/.codex`.
   - On Windows, the common path is `C:\Users\<user>\.codex`.

2. Inspect current state:
   - Read `config.toml` for target `model_provider` and `model`.
   - Query `state_5.sqlite` provider counts and archived counts.
   - Count rollout files under `sessions` and `archived_sessions`.
   - Count current `session_index.jsonl` lines.
   - Inspect `.codex-global-state.json` projectless ids and workspace hints.

3. Dry-run repair:
   - Use `scripts/repair_history_provider.py --codex-home <path> --target-provider <provider> --dry-run`.
   - Confirm the planned database thread count, rollout file count, and rebuilt index count match expectations.

4. Apply repair:
   - Use `scripts/repair_history_provider.py --codex-home <path> --target-provider <provider> --apply`.
   - Keep the backup path from stdout.
   - Tell the user to restart Codex Desktop manually and check history.

5. Validate:
   - `threads` total unchanged.
   - `model_provider` is the target provider for all intended threads.
   - `session_index.jsonl` rows equal non-archived thread count.
   - All index `rollout_path` values exist.
   - All rollout first-line provider values are target provider.

## Script

Use the bundled script for deterministic repair:

```bash
python scripts/repair_history_provider.py --codex-home ~/.codex --target-provider custom --dry-run
python scripts/repair_history_provider.py --codex-home ~/.codex --target-provider custom --apply
```

On Windows PowerShell:

```powershell
python C:\Users\<user>\.codex\skills\codex-history-repair\scripts\repair_history_provider.py --codex-home C:\Users\<user>\.codex --target-provider custom --apply
```

The script defaults to dry-run unless `--apply` is passed. It creates backups under `CODEX_HOME/history-provider-migration-backups/<timestamp>/`.

## Rollback

If the repair fails or the UI looks wrong after restart:

1. Close Codex Desktop manually.
2. Restore files from the backup directory:
   - `state_5.sqlite`
   - `state_5.sqlite-wal`
   - `state_5.sqlite-shm`
   - `session_index.jsonl`
   - `.codex-global-state.json`
   - modified `rollout-*.jsonl`
3. Reopen Codex Desktop.

Use the backup `manifest.json` to see which files were copied and modified.

## Platform Notes

- Windows paths may contain `\\?\` prefixes in SQLite `cwd`; normalize before deriving workspace hints.
- Linux/macOS use POSIX paths and usually store data in `~/.codex`.
- SQLite/WAL behavior matters on every platform. Online backup is safer while Codex is running.
- Desktop global state may not exist in CLI-only installations; in that case skip `.codex-global-state.json` repair.

## Lessons From The Successful Windows Repair

- The original failure had 73 threads in `state_5.sqlite`, but only 6 lines in `session_index.jsonl`.
- Provider values were split across `cc_switch`, `OpenAI`, and `custom`.
- Migrating all thread metadata to `custom`, rebuilding `session_index.jsonl`, updating rollout first lines, and rebuilding workspace hints restored visibility after manual restart.
- The most important checks were provider counts, non-archived count versus index rows, valid rollout paths, and verifying that only rollout first lines changed.
