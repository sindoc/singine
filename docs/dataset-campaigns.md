# Dataset Campaigns

`singine campaign dataset-plan` turns a free-form brief into a governed dataset
collection plan grounded in:

- active contracts
- active contacts
- common vocabulary
- phased standards alignment
- trusted realms

The plan is intentionally Collibra-aligned without requiring a live Collibra
runtime. It emits a JSON structure that can be used as input to a glossary,
reference-data, or operating-model workflow.

## Example

```bash
singine campaign dataset-plan \
  --title "Molecular Imaging Governance" \
  --brief "Create a collection of datasets phased by active contracts and contacts, with a shared vocabulary across Collibra, AI/LLM/MLOps, health, functional medicine, and functional programming for molecular biology." \
  --contract "research-master-services-agreement" \
  --contract "data-sharing-annex" \
  --contact "health-data-steward" \
  --contact "molecular-biology-lead" \
  --trusted-realm "molecularimaging.be" \
  --vocabulary-term "evidence lineage" \
  --output /tmp/molecular-imaging-campaign.json \
  --json
```

## Output shape

The generated payload contains:

- `scope.active_contracts`
- `scope.active_contacts`
- `scope.trusted_realms`
- `standards_phases`
- `common_vocabulary`
- `datasets`

The trusted realm list always includes `molecularimaging.be` so the campaign can
be anchored to a governed scientific publication or evidence boundary by
default.

## Typical use

- capture the campaign brief from business language first
- map direct contract pressure in phase 1
- align indirect standards and vocabulary in phase 2
- attach scientific and imaging evidence lineage in phase 3

This gives Singine core, the realm operator surface, and Collibra-style
vocabulary work one shared dataset campaign artifact.
