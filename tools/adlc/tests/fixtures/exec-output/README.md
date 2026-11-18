# Exec output parser fixtures (REQ-662 BR-6, AC-6)

Every file here is **synthetic**: written by hand in the shape of the committed probe
captures (`.adlc/research/harness-probes/codex.json`, `stdout_tail`) and of `claude -p
--output-format json`, not captured from a run. Each name says so (`*.synthetic.*`).
TASK-266 replaces the `codex-*` files with one real `codex exec --json` launch, passed
through REQ-664 BR-9's credential redaction and `$HOME` to `~` rewrite, with the harness
version noted. No file holds a credential or an absolute home path.

| File | What the parser must say |
|------|--------------------------|
| `codex-jsonl.synthetic.stdout.jsonl` + `codex-jsonl.synthetic.last-message.txt` | parses: the session id is `thread.started`'s `thread_id`, the final message is the `-o` file |
| `codex-jsonl-no-terminal.synthetic.stdout.jsonl` | parse failure: no `turn.completed`, the stream was truncated |
| `codex-jsonl-cut.synthetic.stdout.jsonl` | parse failure: the last line is cut, with no newline |
| `codex-jsonl-empty-message.synthetic.last-message.txt` | parse failure: the final message is empty |
| `not-json.synthetic.stdout.txt` | parse failure under either format: stdout is not JSON |
| `claude-json.synthetic.stdout.json` | parses under `format: json` |
