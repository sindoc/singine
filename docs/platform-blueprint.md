# Platform Blueprint

`singine platform blueprint` writes a starter platform contract for the larger
system you described:

- Docker and local CentOS or RHEL farm execution
- OpenShift deployment shape
- Node.js web shell
- Python notebook-facing API
- Spring Boot metadata adapter interfaces
- Singine Clojure core orchestration
- Flowable execution ordering
- Collibra integration through CLI, REST, GraphQL, and opmodel-aligned
  interfaces

## Why this exists

The repo already has:

- Singine docker and messaging stacks
- notebook demos
- Collibra CLI and edge integration patterns
- trust and key-management surfaces

What was missing was one generated artifact that lines those pieces up as a
single platform contract.

## Example

```bash
singine platform blueprint \
  --output-dir /tmp/singine-platform-blueprint \
  --json
```

## Generated scaffold

The command writes:

- `platform-blueprint.json`
- `platform-blueprint.md`
- `deploy/openshift-template.yaml`
- `webapp/package.json`
- `webapp/server.js`
- `webapp/public/index.html`
- `webapp/public/styles.css`
- `python-api/service.py`
- `spring-adapter/.../MetadataProtocolAdapter.java`

The scaffold is intentionally lightweight. It gives the contract and file
layout, but it does not install npm packages or fetch external artifacts.

## Collibra alignment

The blueprint explicitly carries the three plain-text Collibra attribute
families used for governed execution:

- `Script Body`
- `Source Code`
- `Authorised Commands`

Those are the minimum bridge for Flowable/Groovy/shell or adapter execution on
edge while keeping Collibra as system of record.
