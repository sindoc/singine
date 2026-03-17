# SilkPage — DocBook Website Layer

SilkPage is the DocBook-based website generation layer for Singine documentation.
It transforms XML source files into static HTML sites using Norman Walsh's DocBook Website XSL stylesheets.

## Structure

```
silkpage/
├── trunk/core/         # SilkPage core build system (Ant + Saxon + DocBook Website)
│   └── src/
│       ├── xml/build/  # Ant build task definitions (tasks.xml)
│       └── xsl/        # XSL stylesheet adapters
└── site/               # Site-specific content (per deployment)
```

## Technology Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| Saxon 6.5.3 | XSLT 1.0 | XML transformation engine |
| DocBook Website | 2.4.1 | Website page layout DTDs |
| DocBook XSL | — | Stylesheet library |
| Apache FOP | — | PDF generation (optional) |
| JTidy | — | HTML correction and validation |
| Ant | 1.10+ | Build orchestration |

## Build

### Prerequisites

- Java 21 (OpenJDK or Temurin)
- Ant 1.10+
- DocBook Website XSL stylesheets installed

### Generate a site

```bash
ant -f trunk/core/src/xml/build/tasks.xml website \
  -Duser.xml.dir=site/silkpage.markupware.com/src/xml \
  -Ddocbook.website.home=/path/to/docbook-website \
  -Ddocbook.xsl.home=/path/to/docbook-xsl
```

## Integration with Singine

SilkPage generates the published documentation for:

- `singine-activity` — Activity taxonomy and ultimate metric model
- `singine-auth` — JwsToken and CertAuthority reference
- `singine-local` — Local network server and trusted individual store
- `singine.ai` — AI session management and provider governance

Published to: `sina.khakbaz.com/docs/activity/`

## Relation to Norman Walsh xmldoclet

SilkPage and Norman Walsh's xmldoclet share the same XML-first publication philosophy:

- xmldoclet generates machine-readable XML Javadoc from Java source annotations
- SilkPage transforms that XML into publishable HTML documentation

The Ant `javadoc-xml` target in `core/build.xml` feeds output into SilkPage-compatible XML documents.
