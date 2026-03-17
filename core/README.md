# Singine Core

This is the Clojure runtime for Singine.

It contains the server, Camel routes, broker logic, Java helper classes, and the core test suite.

The runtime is the canonical local edge/server surface. It currently exposes
the HTTP routes documented in `singine server inspect`, including:

- `/health`
- `/bridge`
- `/cap`
- `/messages`
- `/timez`

Default server behavior:

- bind host: `0.0.0.0`
- default client host: `127.0.0.1`
- default port: `8080`

The action/activity API alignment lives here as well:

- Java interfaces: `core/java/singine/activity/`
- taxonomy source of truth: `resources/singine/activity/taxonomy.edn`
- local publication/build chain: Ant + Javadoc + xmldoclet

Common tasks:

- run tests
- start the local server
- open a REPL
- compile Java helpers into `classes/`
- generate HTML Javadoc with `ant javadoc-html`
- generate XML Javadoc with `ant javadoc-xml` after installing `com.saxonica:xmldoclet`

Useful cross-surface commands from the repo root:

- `singine server inspect`
- `singine server health`
- `singine snapshot save`
- `make serve`
- `make javac`

The XML doclet target is intended for Saxonica's `xmldoclet` project:
https://github.com/Saxonica/xmldoclet

Use `make help` in this directory for the local entrypoints.
