# AI Session Dashboard

`singine ai session dashboard` builds one HTML page that combines:

- the governed JSON session store under `~/.singine/ai/sessions`
- the older repo-backed EDN session records under `singine/ai/sessions`

The goal is to let you inspect Claude and Codex work side by side, including
interaction bodies and command-line session logs.

## Generate the page

```bash
python3 -m singine.command ai session dashboard \
  --output-dir /Users/skh/ws/git/github/sindoc/singine/target/sindoc.local/sessions \
  --json
```

This writes:

- `target/sindoc.local/sessions/index.html`
- `target/sindoc.local/sessions/sessions.json`
- and registers `/sessions/` on the `sindoc.local` index page

## Serve it from `sindoc.local`

Add a hosts entry:

```text
127.0.0.1 sindoc.local
```

Then serve the generated site root:

```bash
python3 -m singine.command web /Users/skh/ws/git/github/sindoc/singine/target/sindoc.local --port 8080
```

Open:

```text
http://sindoc.local:8080/
http://sindoc.local:8080/sessions/
```

## Useful filters

- `--provider claude`
- `--provider codex`
- `--root-dir ~/.singine/ai`
- `--repo-ai-dir /Users/skh/ws/git/github/sindoc/singine/ai`
