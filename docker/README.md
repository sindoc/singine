# Singine Docker

This directory contains Dockerfiles and compose files used to package or exercise Singine-related services locally.

Current variants:

- `docker-compose.edge.yml`
- `docker-compose.mail.yml`
- `Dockerfile.edge`
- `Dockerfile.mail`

Use `make help` in this directory for the common compose commands.

The `edge` packaging is the closest Docker view of the local Singine HTTP
surface. The corresponding CLI inspection command is:

```bash
singine server inspect --environment-type docker --json
```

That command reports the default edge host/port assumptions, Docker packaging
files, git awareness, and the taxonomy/publication paths that the containerized
service is expected to preserve.
