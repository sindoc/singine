# Control Center

`singine intranet control-center` builds a single local control-plane page for:

- this machine
- your dotfiles control surface
- your Claude/Codex session observatory
- the live edge Docker runtime

## Generate

```bash
python3 -m singine.command intranet control-center \
  --output-dir /Users/skh/ws/git/github/sindoc/singine/target/sindoc.local/control \
  --json
```

This writes:

- `target/sindoc.local/control/index.html`
- `target/sindoc.local/control/control.json`

and registers `/control/` on the `sindoc.local` index page.

## Serve

```bash
python3 -m singine.command web /Users/skh/ws/git/github/sindoc/singine/target/sindoc.local --port 8080
```

Open:

```text
http://sindoc.local:8080/
http://sindoc.local:8080/control/
```

## What it shows

- machine identity and repo root
- dotfiles summary with links to `/dotfiles/`
- AI session summary with links to `/sessions/`
- live Docker edge container status
- command snippets for `singine edge status`, `singine edge logs`, `singine edge up`, and `singine edge down`
