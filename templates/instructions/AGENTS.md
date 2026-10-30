# AGENTS.md

This project runs spec-driven development with the ADLC toolkit (Agentic
Development Life Cycle). Every agent harness this project uses reads this file
from the project root; settings that only one harness understands live in that
harness's own files.

## Workflow

Requirements come before code. `/spec` drafts a requirement, `/validate` checks
it, `/architect` designs it and breaks it into tasks, then the tasks are
implemented, self-reviewed with `/reflect`, reviewed, and closed out with
`/wrapup`. `/proceed REQ-xxx` runs the whole pipeline for one requirement, and
`/sprint` runs several in parallel.

## Skills

<!-- adlc:skills -->

## Project context

Read these before changing the project:

- `.adlc/ETHOS.md` — the principles every skill follows
- `.adlc/context/project-overview.md` — what this project is and who uses it
- `.adlc/context/architecture.md` — how it is built
- `.adlc/context/conventions.md` — how code is written here
- `.adlc/specs/` — requirements, with their architecture and tasks
- `.adlc/knowledge/` — lessons learned and validated assumptions
