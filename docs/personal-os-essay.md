# Personal OS Essay

`singine essay personal-os` writes a reflective publication bundle around the
idea of software as a personal operating system.

The command stays grounded in local references you already use:

- the `sindoc42` onepager PDF under `~/ws/today`
- the `lutino.collibra` metamodel tree under `~/ws/today`
- the Logseq PDF under `~/ws/logseq`
- the notebook fragment output under `~/ws/today/singine-notebook`
- the XML request/response examples under `~/ws/today/singine-mail/xml`

## What it generates

- `essay.md`
- `essay.html`
- `visual.svg`
- `essay.tex`
- `workflow/request.xml`
- `workflow/response.xml`
- `rules/personal_os_rules.sinlisp`
- `interfaces/adapter.bal`
- `interfaces/bridge.h`
- `interfaces/bridge.rs`
- `interfaces/bridge.pico`
- `interfaces/grammar.ixml`
- `manifest.json`

## Why this exists

This command is the essay counterpart to the platform and demo generators. It
keeps the domains distinct:

- Logseq as reflective graph memory
- Collibra as governed business and metamodel surface
- SQLite as local persistence layer
- XML request/response as signed workflow boundary
- Ballerina as service choreography layer
- C and Rust as low-level control points
- Pico, Lisp, and SinLisp as compact rule-expression surfaces

## Example

```bash
singine essay personal-os \
  --output-dir /tmp/singine-personal-os \
  --json
```

## Output style

The bundle is intentionally multi-format:

- Markdown and HTML for reading
- SVG for the visual complex-plane/fractal projection
- LaTeX for type-driven publication
- XML for request/response workflow envelopes
- SinLisp and Pico for compact rule inheritance
- ixml for grammar compatibility
- Ballerina, C, and Rust for interface contracts
