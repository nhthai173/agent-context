---
title: Remember via agent-context
order: 90
---
Save cross-session learnings (a user preference, a correction, a project fact) with this instead of native memory, when the session is inside `agent-context` or a project registered in it (its `AGENTS.md`/`CLAUDE.md` has an `agentctx:begin` block). Don't ask first; the user reviews via `git log`. If a memory in the Shared memories list already covers the fact, don't save it again: say which one.

`uv run {{tool}}/agentctx.py remember --to <layer> --type <user|feedback|project|reference> --reason "<why this scope>" "<the fact>"`

`--to`: `global`, `teams/<t>`, `users/<u>`, or a project (`teams/<t>/projects/<repo>`, `users/<u>/projects/<repo>`): the narrowest layer where it's true. It commits that one file and runs `sync`; a non-zero exit prints what to do next. Native memory only if `remember` can't run at all. End your reply with one line saying what you remembered and where.
