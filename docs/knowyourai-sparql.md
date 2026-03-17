# KnowYourAI SPARQL Guide

This guide gives you a first clean query path from Singine into your local `#KnowYourAI` RDF corpus.

The current path is:

`knowyourai-framework RDF/XML -> Singine bridge SQLite schema -> supported SPARQL subset`

## Build the bridge

Use the default database path:

```bash
make bridge-build
make bridge-sources
```

Or choose a custom path:

```bash
SINGINE_CORTEX_DB=/tmp/knowyourai.db make bridge-build
SINGINE_CORTEX_DB=/tmp/knowyourai.db make bridge-sources
```

You should see a `knowyourai` source if the local repo exists at `~/ws/git/github/sindoc/knowyourai-framework`.

## Query shape limits

The current bridge supports a narrow but useful subset:

- `SELECT ?s WHERE { ?s a TYPE . }`
- `SELECT ?s ?label WHERE { ?s a TYPE ; rdfs:label ?label . }`
- `SELECT ?s WHERE { ?s PREDICATE "literal" . }`
- `SELECT ?o WHERE { SUBJECT PREDICATE ?o . }`
- `SELECT ?s ?o WHERE { ?s PREDICATE ?o . }`

This is enough to inspect the concept hierarchy, role labels, risk profile values, and related resources in the KnowYourAI pack.

## Useful prefixes in this dataset

- `rdf:` `http://www.w3.org/1999/02/22-rdf-syntax-ns#`
- `rdfs:` `http://www.w3.org/2000/01/rdf-schema#`
- `skos:` `http://www.w3.org/2004/02/skos/core#`
- `dc:` `http://purl.org/dc/elements/1.1/`
- `dcterms:` `http://purl.org/dc/terms/`
- `foaf:` `http://xmlns.com/foaf/0.1/`
- `knowyourai:` `https://github.com/sindoc/knowyourai-framework/blob/main/ontology.owl#`

## Named query files

List them:

```bash
make knowyourai-list
```

Run one:

```bash
make knowyourai-query QUERY=scenarios/knowyourai/list-concepts.rq
```

## What each query shows

`list-concepts.rq`
: Lists the main SKOS concepts and their labels.

`broader-links.rq`
: Shows the concept hierarchy. In the current corpus, several AI relationship categories point back to `AI Systems`.

`human-role-labels.rq`
: Shows the human-side role descriptions for each concept.

`risk-likelihoods.rq`
: Shows the linked `RiskProfile` node for each concept. Follow that node with the value queries to inspect its contents.

`risk-likelihood-values.rq`
: Lists the `likelihood` values stored on the blank-node style risk profiles.

`risk-impact-values.rq`
: Lists the `impact` values stored on the blank-node style risk profiles.

`related-resources.rq`
: Shows the related resource containers or linked resources attached to each concept.

## Example queries

List concept labels:

```sparql
SELECT ?s ?label
WHERE { ?s a skos:Concept ; rdfs:label ?label . }
LIMIT 20
```

Find the broader concept for `AI as a Tool`:

```sparql
SELECT ?o
WHERE {
  <https://github.com/sindoc/knowyourai-framework/blob/main/ai-human-relationships.rdf#ai-as-a-tool>
  skos:broader
  ?o .
}
LIMIT 10
```

Find all concepts with the exact human role label `Supervisor, parameter setter`:

```sparql
SELECT ?s
WHERE { ?s knowyourai:humanRoleLabel "Supervisor, parameter setter" . }
LIMIT 20
```

Inspect risk profile values after discovering a profile node:

```sparql
SELECT ?s ?o
WHERE { ?s knowyourai:likelihood ?o . }
LIMIT 20
```

## Practical interpretation

This first pass is not a full SPARQL engine. It is a readable inspection layer over your RDF so you can:

- see what the corpus contains
- validate predicate choices
- identify the concepts and resource links you want Singine to reason over
- prepare a later SQL-to-SPARQL or NL-to-SPARQL layer on top of a known dataset

Once this query pack is stable, the next step is to bind these patterns into higher-level Singine commands and server routes.
