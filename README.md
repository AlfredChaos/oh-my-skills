# oh-my-skills

Shared local skill workspace for Claude Code, Codex, and Hermes.

Each top-level subdirectory is one skill:

```text
oh-my-skills/
├── gpt-image-2-packyapi/
│   ├── SKILL.md
│   ├── .env.example
│   ├── agents/
│   └── scripts/
└── README.md
```

## Current Skills

- `gpt-image-2-packyapi`: Generate and edit images through PackyAPI's `gpt-image-2` Images API.

## Conventions

- Put each skill directly under this repository root.
- Keep each skill self-contained, including its own `.env.example` when environment variables are needed.
- Do not commit real `.env` files, generated outputs, caches, or local runtime state.
- Use the top-level `.gitignore` for shared ignore rules. Add a skill-local `.gitignore` only for extra artifacts that are specific to that skill.

## Agent Integration

This repository is symlinked into each agent's skills directory as `oh-my-skills`:

```text
~/.claude/skills/oh-my-skills -> /Users/alfredchaos/home/infinityflow/oh-my-skills
~/.codex/skills/oh-my-skills  -> /Users/alfredchaos/home/infinityflow/oh-my-skills
~/.hermes/skills/oh-my-skills -> /Users/alfredchaos/home/infinityflow/oh-my-skills
```

For agents that only scan one level below their `skills` directory, add individual skill symlinks too:

```text
~/.claude/skills/gpt-image-2-packyapi -> ./gpt-image-2-packyapi
~/.codex/skills/gpt-image-2-packyapi  -> ./gpt-image-2-packyapi
~/.hermes/skills/gpt-image-2-packyapi -> ./gpt-image-2-packyapi
```
