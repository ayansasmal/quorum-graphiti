# Repository Guidelines

## Quorum Fork Overlay

This repository is the Quorum-maintained fork of `getzep/graphiti`. Quorum-specific
`graphiti-core` prompt fixes, extraction guards, regression tests, and the Graphiti MCP
container belong here, not in the Quorum gateway.

- Preserve upstream compatibility where practical and keep patches suitable for upstreaming.
- Add a failing regression test before changing prompt or extraction behavior.
- Build the MCP container against this checkout's local `graphiti_core`; never replace it with
  a floating PyPI `graphiti-core>=...` dependency.
- Publish immutable multi-platform images as
  `ghcr.io/ayansasmal/graphiti-mcp:sha-<commit>`.
- Publishing does not deploy automatically. Quorum production must explicitly pin the verified
  image tag in `quorum/crossplane/environments/prod.yaml`.
- Do not suppress Quorum audit episodes. Guard invalid relationship extraction while preserving
  episode ingestion and lineage.
- Fact invalidation in `graphiti_core/prompts/dedupe_edges.py` is conservative: contradictions
  require the same specific subject or entity relationship plus logically incompatible claims.
  Uncertainty may empty `contradicted_facts`, but must not suppress a confident duplicate.
- Verify the Quorum fact-invalidation prompt contract with
  `UV_CACHE_DIR=/tmp/quorum-graphiti-uv-cache DISABLE_FALKORDB=1 DISABLE_KUZU=1 DISABLE_NEPTUNE=1 uv run --frozen pytest tests/prompts/test_quorum_prompt_regressions.py -q`.
- Edge extraction returns before the LLM when fewer than two distinct normalized entity names
  exist. Model-produced blank endpoints and normalized self-edges are rejected, while duplicate
  normalized node names resolve deterministically to the first node.
- Verify the Quorum edge guards with
  `UV_CACHE_DIR=/tmp/quorum-graphiti-uv-cache DISABLE_FALKORDB=1 DISABLE_KUZU=1 DISABLE_NEPTUNE=1 uv run --frozen pytest tests/utils/maintenance/test_edge_operations.py -q`.
- Entity summary prompts use the canonical `ATTRIBUTION:` block: retain only facts directly
  describing each entity, never carry facts across co-mentioned entities, and preserve durable
  existing summaries when new input adds no entity-specific fact. Pair summarization retains every
  explicit grammatical subject because community summaries can contain multiple entities.
- Production ingestion prompts use balanced `<PREVIOUS_MESSAGES>` delimiters. The spaced
  `<PREVIOUS MESSAGES>` form remains only in the offline evaluation module and must not be
  reintroduced into extraction or deduplication prompts.

### Quorum Fork MCP Image

Build from the repository root with the immutable commit-derived tag:

```bash
docker build -f mcp_server/docker/Dockerfile.quorum \
  --build-arg VCS_REF=$(git rev-parse HEAD) \
  -t ghcr.io/ayansasmal/graphiti-mcp:sha-$(git rev-parse HEAD) .
```

`Dockerfile.quorum` installs this checkout's local `graphiti_core` source before installing the MCP
server with its `providers` and `azure` extras. Production must use only immutable `sha-<commit>`
tags and explicitly pin the verified tag; never rewrite the image to use a floating PyPI Graphiti
release. Quorum audit episodes are provenance and must not be filtered or suppressed.

## Project Structure & Module Organization
Graphiti's core library lives under `graphiti_core/`, split into domain modules such as `nodes.py`, `edges.py`, `models/`, and `search/` for retrieval pipelines. Database drivers in `graphiti_core/driver/` support Neo4j, FalkorDB, and Neptune (plus a deprecated Kuzu driver). Additional core modules include `cross_encoder/` (reranking via BGE, OpenAI, and Gemini), `telemetry/` (OpenTelemetry tracing), `namespaces/` (namespace management), and `migrations/` (database migrations). Service adapters and API glue reside in `server/graph_service/`, while the MCP integration lives in `mcp_server/` (with its own `src/`, `tests/`, `config/`, and `docker/` subdirectories). Shared assets sit in `images/` and `examples/`. Tests cover the core package via `tests/`, with configuration in `conftest.py`, `pytest.ini`, and Docker compose files for optional services. Specifications live in `spec/` and type signatures in `signatures/`. Tooling manifests live at the repo root, including `pyproject.toml`, `Makefile`, and deployment compose files.

## Build, Test, and Development Commands
- `make install`: install the dev environment (`uv sync --extra dev`).
- `make format`: run `ruff` to sort imports and apply the canonical formatter.
- `make lint`: execute `ruff` plus `pyright` type checks against `graphiti_core`.
- `make test`: run unit tests only, excluding integration tests and disabling non-Neo4j drivers (`DISABLE_FALKORDB=1 DISABLE_KUZU=1 DISABLE_NEPTUNE=1 uv run pytest -m "not integration"`).
- `make check`: run format, lint, and test in sequence.
- `uv run pytest tests/path/test_file.py`: target a specific module or test selection.
- `docker-compose -f docker-compose.test.yml up`: provision local graph/search dependencies for integration flows.

## Coding Style & Naming Conventions
Python code uses 4-space indentation, 100-character lines, and prefers single quotes as configured in `pyproject.toml`. Modules, files, and functions stay snake_case; Pydantic models in `graphiti_core/models` use PascalCase with explicit type hints. Keep side-effectful code inside drivers or adapters (`graphiti_core/driver`, `graphiti_core/cross_encoder`, `graphiti_core/utils`) and rely on pure helpers elsewhere. Run `make format` before committing to normalize imports and docstring formatting.

## Testing Guidelines
Author tests alongside features under `tests/`, naming files `test_<feature>.py` and functions `test_<behavior>`. Integration test files use the `_int` suffix (e.g., `test_edge_int.py`, `test_node_int.py`). Use `@pytest.mark.integration` for database-reliant scenarios so CI can gate them; `make test` excludes these by default. Async tests run automatically via `asyncio_mode = auto` in `pytest.ini`. Reproduce regressions with a failing test first and validate fixes via `uv run pytest -k "pattern"`. Start required backing services through `docker-compose.test.yml` when running integration suites locally. The `mcp_server/` has its own separate test suite under `mcp_server/tests/`.

## Commit & Pull Request Guidelines
Commits use an imperative, present-tense summary (for example, `add async cache invalidation`) optionally suffixed with the PR number as seen in history (`(#927)`). Squash fixups and keep unrelated changes isolated. Pull requests should include: a concise description, linked tracking issue, notes about schema or API impacts, and screenshots or logs when behavior changes. Confirm `make lint` and `make test` pass locally, and update docs or examples when public interfaces shift.
