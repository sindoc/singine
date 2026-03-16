# Singine Core

This is the Clojure runtime for Singine.

It contains the server, Camel routes, broker logic, Java helper classes, and the core test suite.

Common tasks:

- run tests
- start the local server
- open a REPL
- compile Java helpers into `classes/`
- generate HTML Javadoc with `ant javadoc-html`
- generate XML Javadoc with `ant javadoc-xml` after installing `com.saxonica:xmldoclet`

The XML doclet target is intended for Saxonica's `xmldoclet` project:
https://github.com/Saxonica/xmldoclet

Use `make help` in this directory for the local entrypoints.
