# Dotfiles Control

`singine dotfiles` gives you a first safe layer of control over the dotfiles
you named:

- shell startup files: `.profile`, `.bash_profile`, `.bashrc`, `.zprofile`, `.zshrc`
- editor config: `.vimrc`
- shell helper directory: `.box-shell`
- Claude state: `.claude` and `~/ws/.claude`
- Logseq state: `.logseq`
- Dropbox root: `~/Dropbox`

## Inspect

```bash
python3 -m singine.command dotfiles inspect --json
```

## Build an HTML dashboard

```bash
python3 -m singine.command dotfiles dashboard \
  --output-dir /Users/skh/ws/git/github/sindoc/singine/target/sindoc.local/dotfiles \
  --json
```

That writes:

- `target/sindoc.local/dotfiles/index.html`
- `target/sindoc.local/dotfiles/dotfiles.json`
- and registers `/dotfiles/` on the `sindoc.local` index page

Serve it with:

```bash
python3 -m singine.command web /Users/skh/ws/git/github/sindoc/singine/target/sindoc.local --port 8080
```

Then open:

```text
http://sindoc.local:8080/dotfiles/
```

## Capture current state into the repo

For file-backed targets, capture copies into the dotfiles repo:

```bash
python3 -m singine.command dotfiles capture bashrc --json
python3 -m singine.command dotfiles capture vimrc --json
```

For directory-backed targets, Singine writes a manifest into the repo:

```bash
python3 -m singine.command dotfiles capture claude-home --json
python3 -m singine.command dotfiles capture logseq-home --json
python3 -m singine.command dotfiles capture dropbox --json
```

This first step is intentionally non-destructive: it inventories and captures.
It does not rewrite your home directory or symlink files yet.
