# VajraTrace

> Real-time identification of fraud-linked cryptocurrency exchanges from victim-reported suspect wallet addresses through automated blockchain analytics.

## Quick Start

```bash
git clone <repo-url> && cd vajratrace
cp .env.example .env
# Fill in your API keys in .env
docker-compose up --build
```

Open in your browser:

- **Frontend:** [http://localhost:3000](http://localhost:3000)
- **API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Neo4j Browser:** [http://localhost:7474](http://localhost:7474) (neo4j / vajratrace)

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full specification.
