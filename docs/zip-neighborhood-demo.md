# Zip Neighborhood Demo

`singine demo zip-neighborhood` creates a first demo bundle that lines up:

- RabbitMQ raw messaging
- RabbitMQ staging messaging
- Kafka data streaming
- lambda handoff metadata
- notebook import for Collibra or Databricks
- multilingual and Wikipedia-to-Collibra mapping
- Markdown, XML, JSON, and MediaWiki publication fragments
- optional domain-event logging with git context capture

## Example

```bash
singine demo zip-neighborhood \
  --output-dir /tmp/singine-zip-neighborhood-demo \
  --db /tmp/singine-demo.db \
  --json
```

## Output

The command writes:

- `rabbitmq/raw/*.json`
- `rabbitmq/staging/*.json`
- `kafka/topic.json`
- `publication/demo.md`
- `publication/demo.xml`
- `publication/demo.json`
- `publication/demo.mediawiki`
- `manifest.json`

The publication files are intended as interchangeable fragments:

- Markdown for drafting and repo-native review
- XML for downstream transformation
- JSON for notebooks and API calls
- MediaWiki for wiki-native publication

## Notebook import

```python
import singine
from singine.zip_neighborhood_demo import build_zip_neighborhood_demo

demo = build_zip_neighborhood_demo()
demo["messages"]["kafka"][0]
```

This is the intended first import path for Collibra notebooks or Databricks:
the same module builds the in-memory object and the CLI writes the filesystem
bundle plus optional domain-event logging.
