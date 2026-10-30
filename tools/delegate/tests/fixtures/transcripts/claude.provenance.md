# claude.jsonl provenance

- **Harness:** Claude Code 2.1.309 (`entrypoint: claude-desktop`)
- **Captured:** 2026-10-30, from a subagent run whose whole content was one `echo`
- **Kept:** four records: the user prompt, a `tool_use`, its `tool_result`, the plain reply
- **Cut:** every `attachment` record, every `api-request-shape`, `api-request-blob`
  and `api-request` record, the `thinking` record, and the `wireToolInputs` key
- **Redacted:** home-directory prefix rewritten to `~`; the REQ-415 credential chain
  ran and changed nothing
- **Golden:** `claude.expected.txt` is the output of `tools/delegate/extract-chat` at
  the merge base of REQ-660, before `--format` existed

Replace this fixture rather than editing it when the record shape changes.
