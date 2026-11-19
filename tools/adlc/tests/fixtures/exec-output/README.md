# Exec output parser fixtures (REQ-662 BR-6, AC-6)

The `codex-exec-*.0.166.0.*` files are **real**: one `codex exec --json` launch and its
`codex exec resume`, captured on 2026-11-18 with codex-cli 0.166.0 and passed through REQ-664
BR-9's credential redaction and `$HOME` to `~` rewrite (`harness_probe.scrub`).
`.adlc/research/harness-probes/codex-exec-manual.md` records the runs they come from. A
`*.derived.*` file is cut from a real one by hand, and a `*.synthetic.*` file is written by
hand. No file holds a credential or an absolute home path.

| File | What the parser must say |
|------|--------------------------|
| `codex-exec-launch.0.166.0.stdout.jsonl` + `.last-message.txt` | parses: the session id is `thread.started`'s `thread_id`, the final message is the `-o` file |
| `codex-exec-launch.0.166.0.stderr.txt` | holds the harness's refusal of a `forbidden` command, the adapter's `denied_stderr` |
| `codex-exec-resume.0.166.0.*` | the resume of that session: the same session id |
| `codex-exec-launch.no-terminal.derived.stdout.jsonl` | parse failure: no `turn.completed`, the stream was truncated |
| `codex-exec-launch.cut.derived.stdout.jsonl` | parse failure: the last line is cut, with no newline |
| `codex-exec.empty.derived.last-message.txt` | parse failure: the final message is empty |
| `not-json.synthetic.stdout.txt` | parse failure under either format: stdout is not JSON |
| `claude-json.synthetic.stdout.json` | parses under `format: json` |
