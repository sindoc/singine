# Template Library

Singine now carries a persistent library of reusable templates and archetypes so
the generated bundles do not need to live only under `/tmp`.

## Commands

List the library:

```bash
singine template list --json
```

Materialize one entry:

```bash
singine template materialize personal-os-essay \
  --output-dir /tmp/singine-personal-os \
  --json
```

Use the archetype alias for higher-level bundles:

```bash
singine archetype list --json
singine archetype materialize platform-blueprint \
  --output-dir /tmp/singine-platform-blueprint \
  --json
```

## Current built-ins

- `personal-os-essay`
- `platform-blueprint`
- `zip-neighborhood-demo`

## Intent

The library is repo-backed and reusable. `/tmp` remains a convenient output
target, but the archetype definitions now live in Singine itself and can be
materialized repeatedly into any destination directory.
