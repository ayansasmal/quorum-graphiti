# Quorum Graphiti Prompt Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Tasks 1–6 COMPLETE as of 2026-06-15. 42/42 regression tests passing. GHCR publishing workflow live at `.github/workflows/quorum-graphiti-publish.yml`. Tasks 7–9 (pin + production reconvergence) remain in the Quorum repo.

**Goal:** Harden Graphiti's fact invalidation, edge extraction, and entity-summary prompts; publish an immutable Quorum-owned MCP image; and explicitly pin that image in Quorum production.

**Architecture:** Prompt semantics remain in the Quorum Graphiti fork, with deterministic guards around edge extraction so model noncompliance cannot create self-loops. The MCP image installs `graphiti-core` from the same checkout, publishes a multi-platform `sha-<commit>` image to GHCR, and is deployed only after the separate Quorum repository pins that verified tag.

**Tech Stack:** Python 3.11, Pydantic, pytest/pytest-asyncio, Ruff, Pyright, uv, Docker Buildx, GitHub Actions, GHCR, Crossplane/AWS bootstrap compose.

---

## File Map

### Graphiti fork: `/Users/ayan/Desktop/Work/vscode/qc/graphiti/quorum-graphiti`

- Create `tests/prompts/test_quorum_prompt_regressions.py`: deterministic rendered-prompt and tag-regression tests.
- Modify `graphiti_core/prompts/dedupe_edges.py`: conservative same-subject contradiction guidance.
- Modify `graphiti_core/prompts/extract_edges.py`: explicit precondition and anti-hallucination rules.
- Modify `graphiti_core/prompts/snippets.py`: shared entity-attribution summary rules.
- Modify `graphiti_core/prompts/summarize_nodes.py`: pair/context summary attribution.
- Modify `graphiti_core/prompts/extract_nodes.py`: batch and episode summary attribution plus standardized tags.
- Modify `graphiti_core/prompts/dedupe_nodes.py`: standardized tags.
- Modify `graphiti_core/prompts/extract_nodes_and_edges.py`: standardized tags.
- Modify `graphiti_core/utils/maintenance/edge_operations.py`: distinct-entity fast return and normalized self-edge rejection.
- Modify `tests/utils/maintenance/test_edge_operations.py`: extraction-call and self-edge regressions.
- Create `mcp_server/docker/Dockerfile.quorum`: standalone image built from local `graphiti_core`.
- Create `mcp_server/tests/test_quorum_image_contract.py`: static image-contract tests.
- Create `.github/workflows/quorum-graphiti-image.yml`: test, build, and GHCR publication.
- Modify `README.md`: Quorum fork build and image contract.
- Modify `AGENTS.md` and `CLAUDE.md`: record final commands and release workflow.

### Quorum: `/Users/ayan/Desktop/Work/vscode/qc/quorum`

- Modify `crossplane/environments/prod.yaml`: immutable Graphiti image tag.
- Modify `crossplane/tests/rendered.yaml`: regenerated expected Crossplane output.
- Modify `docs/DEPLOYMENT-AWS.md`: Graphiti build, verification, pin, and rollback procedure.
- Modify `AGENTS.md` and `CLAUDE.md`: record the pinned fork-image workflow.

---

### Task 1: Conservative Fact-Invalidation Prompt

**Files:**
- Create: `tests/prompts/test_quorum_prompt_regressions.py`
- Modify: `graphiti_core/prompts/dedupe_edges.py`

- [ ] **Step 1: Write the failing rendered-prompt test**

```python
from graphiti_core.prompts.dedupe_edges import resolve_edge


def _content(messages):
    return '\n'.join(message.content for message in messages)


def test_fact_deduplication_requires_same_subject_and_incompatible_claims():
    prompt = _content(
        resolve_edge(
            {
                'existing_edges': [],
                'edge_invalidation_candidates': [
                    {'idx': 0, 'fact': 'Next.js Pages Router is the project entry point.'},
                    {'idx': 1, 'fact': 'Use npx prisma db push for development schema changes.'},
                ],
                'new_edge': 'Public review routes use NextAuth authentication.',
            }
        )
    )

    assert 'SAME specific subject or entity relationship' in prompt
    assert 'logically INCOMPATIBLE claims' in prompt
    assert 'different subjects are NEVER contradictions' in prompt
    assert 'Next.js Pages Router' in prompt
    assert 'NextAuth authentication' in prompt
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
uv run pytest tests/prompts/test_quorum_prompt_regressions.py::test_fact_deduplication_requires_same_subject_and_incompatible_claims -v
```

Expected: FAIL because the current prompt lacks the same-subject rule and negative Quorum example.

- [ ] **Step 3: Add minimal conservative contradiction instructions**

Update the system message in `resolve_edge()`:

```python
content=(
    'You are a conservative fact deduplication assistant. '
    'NEVER mark facts with key differences as duplicates. '
    'NEVER mark facts as contradictions unless they describe the SAME specific subject or '
    'entity relationship and make logically INCOMPATIBLE claims. '
    'Facts about different subjects are NEVER contradictions. When uncertain, return empty lists.'
),
```

Add this rule before the examples:

```text
CONTRADICTION REQUIREMENTS:
- The NEW FACT and candidate must describe the SAME specific subject or entity relationship.
- Their claims must be logically INCOMPATIBLE; both cannot remain true in the same scope and time.
- Topical similarity, shared technologies, or appearing in the candidate list is not contradiction evidence.
- Facts about different subjects are NEVER contradictions. When uncertain, omit the idx.
```

Add this negative example:

```text
EXISTING FACT: idx=3, "Next.js Pages Router is the project entry point"
NEW FACT: "Public review routes use NextAuth authentication"
Result: duplicate_facts=[], contradicted_facts=[] (different subjects — no contradiction)
```

- [ ] **Step 4: Run the focused prompt test**

Run:

```bash
uv run pytest tests/prompts/test_quorum_prompt_regressions.py -v
```

Expected: PASS.

- [ ] **Step 5: Format and commit**

```bash
uv run ruff format graphiti_core/prompts/dedupe_edges.py tests/prompts/test_quorum_prompt_regressions.py
git add graphiti_core/prompts/dedupe_edges.py tests/prompts/test_quorum_prompt_regressions.py
git commit -m "fix: make fact invalidation conservative"
```

---

### Task 2: Deterministic Edge-Extraction Guards

**Files:**
- Modify: `tests/utils/maintenance/test_edge_operations.py`
- Modify: `graphiti_core/utils/maintenance/edge_operations.py`
- Modify: `graphiti_core/prompts/extract_edges.py`

- [ ] **Step 1: Write failing tests for zero, one, and duplicate entity names**

Add a shared episode/client fixture and these parametrized cases:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    'nodes',
    [
        [],
        [EntityNode(uuid='alice-1', name='Alice', group_id='group_1', labels=['Person'])],
        [
            EntityNode(uuid='alice-1', name=' Alice ', group_id='group_1', labels=['Person']),
            EntityNode(uuid='alice-2', name='alice', group_id='group_1', labels=['Person']),
        ],
    ],
)
async def test_extract_edges_skips_llm_without_two_distinct_entity_names(nodes):
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock()
    clients = SimpleNamespace(
        driver=MagicMock(),
        llm_client=mock_llm,
        embedder=MagicMock(),
        cross_encoder=MagicMock(),
    )
    episode = EpisodicNode(
        uuid='ep_uuid',
        name='Episode',
        group_id='group_1',
        source='message',
        source_description='desc',
        content='[AUDIT] OUTCOME by Alice | tool: remember | pos: 88',
        valid_at=datetime.now(timezone.utc),
    )

    edges = await extract_edges(clients, episode, nodes, [], {}, group_id='group_1')

    assert edges == []
    mock_llm.generate_response.assert_not_awaited()
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
uv run pytest tests/utils/maintenance/test_edge_operations.py -k "skips_llm_without_two_distinct" -v
```

Expected: FAIL because `generate_response()` is called.

- [ ] **Step 3: Add the distinct-name fast return**

Near the beginning of `extract_edges()`, after `llm_client` is assigned:

```python
distinct_node_names = {
    _normalize_string_exact(node.name)
    for node in nodes
    if _normalize_string_exact(node.name)
}
if len(distinct_node_names) < 2:
    logger.debug('Skipping edge extraction: fewer than two distinct entity names')
    return []
```

- [ ] **Step 4: Run the fast-return tests and verify GREEN**

Run:

```bash
uv run pytest tests/utils/maintenance/test_edge_operations.py -k "skips_llm_without_two_distinct" -v
```

Expected: 3 PASS.

- [ ] **Step 5: Write a failing normalized self-edge test**

Add a test whose model response uses `" Alice "` and `"alice"` while two valid nodes are supplied:

```python
@pytest.mark.asyncio
async def test_extract_edges_drops_normalized_self_edge_names():
    alice = EntityNode(uuid='alice_uuid', name='Alice', group_id='group_1', labels=['Person'])
    bob = EntityNode(uuid='bob_uuid', name='Bob', group_id='group_1', labels=['Person'])
    response = ExtractedEdges(
        edges=[
            ExtractedEdge(
                source_entity_name=' Alice ',
                target_entity_name='alice',
                relation_type='REMEMBERS',
                fact='Alice remembers something.',
            )
        ]
    ).model_dump()
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(return_value=response)
    clients = SimpleNamespace(
        driver=MagicMock(),
        llm_client=mock_llm,
        embedder=MagicMock(),
        cross_encoder=MagicMock(),
    )
    episode = EpisodicNode(
        uuid='ep_uuid',
        name='Episode',
        group_id='group_1',
        source='message',
        source_description='desc',
        content='Alice remembers something.',
        valid_at=datetime.now(timezone.utc),
    )

    edges = await extract_edges(
        clients,
        episode,
        [alice, bob],
        [],
        {},
        group_id='group_1',
    )

    assert edges == []
```

- [ ] **Step 6: Run the normalized self-edge test and verify RED**

Run:

```bash
uv run pytest tests/utils/maintenance/test_edge_operations.py::test_extract_edges_drops_normalized_self_edge_names -v
```

Expected: FAIL because exact name lookup occurs before normalized comparison.

- [ ] **Step 7: Normalize lookup and reject equal normalized endpoints**

Replace the exact-only name table with:

```python
normalized_name_to_node: dict[str, EntityNode] = {}
for node in nodes:
    normalized_name = _normalize_string_exact(node.name)
    if normalized_name and normalized_name not in normalized_name_to_node:
        normalized_name_to_node[normalized_name] = node
```

Resolve model names and reject equal endpoints:

```python
source_normalized = _normalize_string_exact(edge_data.source_entity_name)
target_normalized = _normalize_string_exact(edge_data.target_entity_name)
if source_normalized == target_normalized:
    logger.info('Dropping self-edge for normalized entity name %s', source_normalized)
    continue

source_node = normalized_name_to_node.get(source_normalized)
target_node = normalized_name_to_node.get(target_normalized)
```

Use the resolved nodes when converting the accepted extracted edge to `EntityEdge`.

- [ ] **Step 8: Strengthen the edge prompt**

Add to the system/user prompt:

```text
If ENTITIES contains fewer than two distinct names, return {"edges": []} immediately.
NEVER create an edge whose normalized source and target names refer to the same entity.
NEVER fabricate a relationship merely because a message contains an action word.
```

- [ ] **Step 9: Run focused and full edge-operation tests**

Run:

```bash
uv run pytest tests/utils/maintenance/test_edge_operations.py -k "extract_edges" -v
```

Expected: all selected tests PASS.

- [ ] **Step 10: Format and commit**

```bash
uv run ruff format graphiti_core/prompts/extract_edges.py graphiti_core/utils/maintenance/edge_operations.py tests/utils/maintenance/test_edge_operations.py
git add graphiti_core/prompts/extract_edges.py graphiti_core/utils/maintenance/edge_operations.py tests/utils/maintenance/test_edge_operations.py
git commit -m "fix: guard Graphiti edge extraction"
```

---

### Task 3: Entity-Specific Summary Attribution

**Files:**
- Modify: `tests/prompts/test_quorum_prompt_regressions.py`
- Modify: `graphiti_core/prompts/snippets.py`
- Modify: `graphiti_core/prompts/summarize_nodes.py`
- Modify: `graphiti_core/prompts/extract_nodes.py`

- [ ] **Step 1: Write failing summary-attribution prompt tests**

```python
from graphiti_core.prompts.extract_nodes import (
    extract_entity_summaries_from_episodes,
    extract_summaries_batch,
)
from graphiti_core.prompts.summarize_nodes import summarize_context, summarize_pair


def test_summary_prompts_require_entity_specific_attribution():
    contexts = [
        extract_summaries_batch(
            {
                'previous_episodes': [],
                'episode_content': (
                    'Public reviews use /api/reviews/*. '
                    'NextAuth is located at /api/auth/[...nextauth].'
                ),
                'entities': [{'name': '/api/auth/[...nextauth]', 'summary': ''}],
            }
        ),
        extract_entity_summaries_from_episodes(
            {
                'previous_episodes': [],
                'episode_content': 'NextAuth is located at /api/auth/[...nextauth].',
                'entities': [{'name': '/api/auth/[...nextauth]', 'summary': ''}],
            }
        ),
        summarize_context(
            {
                'messages': ['NextAuth is located at /api/auth/[...nextauth].'],
                'node_name': '/api/auth/[...nextauth]',
            }
        ),
        summarize_pair({'node_summaries': ['Summary A', 'Summary B']}),
    ]

    for messages in contexts:
        prompt = _content(messages)
        assert 'directly and specifically describe' in prompt
        assert 'co-mentioned entities' in prompt
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/prompts/test_quorum_prompt_regressions.py -k "summary_prompts" -v
```

Expected: FAIL because the required attribution language is absent.

- [ ] **Step 3: Extend shared summary instructions**

Add to `summary_instructions`:

```text
11. For each summary, include only facts that directly and specifically describe that entity.
12. Do not transfer facts from co-mentioned entities, even when they are topically related.
13. If new messages contain no entity-specific durable fact, preserve the existing summary.
```

- [ ] **Step 4: Add attribution to pair/context and episode prompts**

Add the same semantic rule to:

- `summarize_nodes.summarize_pair()`
- `summarize_nodes.summarize_context()`
- `_entity_episode_summary_system_prompt`
- `extract_entity_summaries_from_episodes()`

Use this canonical wording:

```text
ATTRIBUTION: Include only facts that directly and specifically describe the entity being summarized.
Do not carry over facts about co-mentioned entities, even when they are topically related.
```

- [ ] **Step 5: Run focused prompt tests**

Run:

```bash
uv run pytest tests/prompts/test_quorum_prompt_regressions.py -k "summary" -v
```

Expected: PASS.

- [ ] **Step 6: Run existing summary-operation tests**

Run:

```bash
uv run pytest tests/utils/maintenance/test_entity_extraction.py tests/utils/maintenance/test_node_operations.py -k "summar" -v
```

Expected: all selected tests PASS.

- [ ] **Step 7: Format and commit**

```bash
uv run ruff format graphiti_core/prompts/snippets.py graphiti_core/prompts/summarize_nodes.py graphiti_core/prompts/extract_nodes.py tests/prompts/test_quorum_prompt_regressions.py
git add graphiti_core/prompts/snippets.py graphiti_core/prompts/summarize_nodes.py graphiti_core/prompts/extract_nodes.py tests/prompts/test_quorum_prompt_regressions.py
git commit -m "fix: keep entity summaries attribution-specific"
```

---

### Task 4: Standardize Production Prompt Tags

**Files:**
- Modify: `tests/prompts/test_quorum_prompt_regressions.py`
- Modify: `graphiti_core/prompts/extract_nodes_and_edges.py`
- Modify: `graphiti_core/prompts/extract_nodes.py`
- Modify: `graphiti_core/prompts/dedupe_nodes.py`
- Modify: `graphiti_core/prompts/extract_edges.py`

- [ ] **Step 1: Write the failing source-level tag regression**

```python
from pathlib import Path


PRODUCTION_PROMPT_MODULES = (
    'graphiti_core/prompts/extract_nodes_and_edges.py',
    'graphiti_core/prompts/extract_nodes.py',
    'graphiti_core/prompts/dedupe_nodes.py',
    'graphiti_core/prompts/extract_edges.py',
)


def test_production_prompts_do_not_use_spaced_previous_message_tags():
    for module_path in PRODUCTION_PROMPT_MODULES:
        source = Path(module_path).read_text()
        assert '<PREVIOUS MESSAGES>' not in source, module_path
        assert '</PREVIOUS MESSAGES>' not in source, module_path
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
uv run pytest tests/prompts/test_quorum_prompt_regressions.py::test_production_prompts_do_not_use_spaced_previous_message_tags -v
```

Expected: FAIL for the production modules still using spaced tags.

- [ ] **Step 3: Replace only production prompt delimiters**

Replace:

```text
<PREVIOUS MESSAGES>
</PREVIOUS MESSAGES>
```

with:

```text
<PREVIOUS_MESSAGES>
</PREVIOUS_MESSAGES>
```

Do not alter prose such as “PREVIOUS MESSAGES are context only,” and do not modify
`graphiti_core/prompts/eval.py`.

- [ ] **Step 4: Run prompt regressions and format**

Run:

```bash
uv run pytest tests/prompts/test_quorum_prompt_regressions.py -v
uv run ruff format graphiti_core/prompts/extract_nodes_and_edges.py graphiti_core/prompts/extract_nodes.py graphiti_core/prompts/dedupe_nodes.py graphiti_core/prompts/extract_edges.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add graphiti_core/prompts/extract_nodes_and_edges.py graphiti_core/prompts/extract_nodes.py graphiti_core/prompts/dedupe_nodes.py graphiti_core/prompts/extract_edges.py tests/prompts/test_quorum_prompt_regressions.py
git commit -m "fix: standardize production prompt tags"
```

---

### Task 5: Build the MCP Image from Local Graphiti Core

**Files:**
- Create: `mcp_server/docker/Dockerfile.quorum`
- Create: `mcp_server/tests/test_quorum_image_contract.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Write failing static image-contract tests**

```python
from pathlib import Path


DOCKERFILE = Path('mcp_server/docker/Dockerfile.quorum')


def test_quorum_image_installs_graphiti_core_from_checkout():
    source = DOCKERFILE.read_text()
    assert 'COPY pyproject.toml uv.lock /app/graphiti/' in source
    assert 'COPY graphiti_core/ /app/graphiti/graphiti_core/' in source
    assert 'pip install --no-cache-dir \"/app/graphiti[falkordb]\"' in source
    assert 'graphiti-core>=' not in source


def test_quorum_image_runs_standalone_mcp_server():
    source = DOCKERFILE.read_text()
    assert 'COPY mcp_server/' in source
    assert 'MCP_SERVER_HOST=\"0.0.0.0\"' in source
    assert 'CMD [\"python\", \"main.py\"]' in source
```

- [ ] **Step 2: Run the image-contract tests and verify RED**

Run:

```bash
uv run pytest mcp_server/tests/test_quorum_image_contract.py -v
```

Expected: FAIL because `Dockerfile.quorum` does not exist.

- [ ] **Step 3: Create the Quorum Dockerfile**

Create `mcp_server/docker/Dockerfile.quorum`:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV MCP_SERVER_HOST="0.0.0.0" \
    TRANSPORT="streamable-http" \
    PYTHONUNBUFFERED=1

WORKDIR /app/graphiti
COPY pyproject.toml uv.lock /app/graphiti/
COPY graphiti_core/ /app/graphiti/graphiti_core/
COPY README.md LICENSE /app/graphiti/
RUN pip install --no-cache-dir "/app/graphiti[falkordb]"

WORKDIR /app/mcp
COPY mcp_server/pyproject.toml /app/mcp/pyproject.toml
RUN python - <<'PY'
from pathlib import Path
path = Path('/app/mcp/pyproject.toml')
text = path.read_text()
text = text.replace('    "graphiti-core[falkordb]>=0.29.2",\n', '')
path.write_text(text)
PY
RUN pip install --no-cache-dir ".[providers,azure]"
COPY mcp_server/ /app/mcp/

ARG VCS_REF
LABEL org.opencontainers.image.source="https://github.com/ayansasmal/quorum-graphiti" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.title="Quorum Graphiti MCP Server"

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1
CMD ["python", "main.py"]
```

- [ ] **Step 4: Run static tests and build locally**

Run:

```bash
uv run pytest mcp_server/tests/test_quorum_image_contract.py -v
docker build \
  -f mcp_server/docker/Dockerfile.quorum \
  --build-arg VCS_REF="$(git rev-parse HEAD)" \
  -t quorum-graphiti-mcp:test .
```

Expected: tests PASS and Docker build completes.

- [ ] **Step 5: Verify the installed package comes from the local source**

Run:

```bash
docker run --rm quorum-graphiti-mcp:test \
  python -c "import graphiti_core, pathlib; print(pathlib.Path(graphiti_core.__file__).resolve())"
```

Expected: `/usr/local/lib/python3.11/site-packages/graphiti_core/__init__.py` with the image label
matching the current fork commit. The package contents originate from the copied checkout.

- [ ] **Step 6: Document local build and ownership**

Add a “Quorum fork image” section to `README.md`, `AGENTS.md`, and `CLAUDE.md` with:

```bash
docker build -f mcp_server/docker/Dockerfile.quorum \
  --build-arg VCS_REF="$(git rev-parse HEAD)" \
  -t ghcr.io/ayansasmal/graphiti-mcp:sha-$(git rev-parse --short HEAD) .
```

State that production uses only immutable `sha-*` tags and that audit episodes must not be filtered
before ingestion.

- [ ] **Step 7: Commit**

```bash
git add mcp_server/docker/Dockerfile.quorum mcp_server/tests/test_quorum_image_contract.py README.md AGENTS.md CLAUDE.md
git commit -m "build: package Quorum Graphiti from local core"
```

---

### Task 6: Publish Immutable GHCR Images

**Files:**
- Create: `.github/workflows/quorum-graphiti-image.yml`
- Modify: `mcp_server/tests/test_quorum_image_contract.py`
- Modify: `README.md`

- [ ] **Step 1: Extend the contract test for workflow invariants**

```python
WORKFLOW = Path('.github/workflows/quorum-graphiti-image.yml')


def test_quorum_image_workflow_publishes_immutable_multiplatform_tag():
    source = WORKFLOW.read_text()
    assert 'packages: write' in source
    assert 'ghcr.io/ayansasmal/graphiti-mcp' in source
    assert 'type=sha,prefix=sha-' in source
    assert 'linux/amd64,linux/arm64' in source
    assert 'mcp_server/docker/Dockerfile.quorum' in source
```

- [ ] **Step 2: Run the workflow-contract test and verify RED**

Run:

```bash
uv run pytest mcp_server/tests/test_quorum_image_contract.py -v
```

Expected: FAIL because the workflow is absent.

- [ ] **Step 3: Create the image workflow**

Create `.github/workflows/quorum-graphiti-image.yml`:

```yaml
name: Quorum Graphiti Image

on:
  push:
    branches: [main]
    paths:
      - "graphiti_core/**"
      - "mcp_server/**"
      - ".github/workflows/quorum-graphiti-image.yml"
  workflow_dispatch:

env:
  IMAGE_NAME: ghcr.io/ayansasmal/graphiti-mcp

jobs:
  test-and-publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --extra dev
      - run: >
          uv run pytest
          tests/prompts/test_quorum_prompt_regressions.py
          tests/utils/maintenance/test_edge_operations.py
          mcp_server/tests/test_quorum_image_contract.py
          -v
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=main
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: mcp_server/docker/Dockerfile.quorum
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          build-args: |
            VCS_REF=${{ github.sha }}
          cache-from: type=gha,scope=quorum-graphiti
          cache-to: type=gha,mode=max,scope=quorum-graphiti
```

- [ ] **Step 4: Run contract tests and inspect workflow syntax**

Run:

```bash
uv run pytest mcp_server/tests/test_quorum_image_contract.py -v
git diff --check
```

Expected: PASS with no whitespace errors.

- [ ] **Step 5: Commit and push the Graphiti fork**

```bash
git add .github/workflows/quorum-graphiti-image.yml mcp_server/tests/test_quorum_image_contract.py README.md
git commit -m "ci: publish Quorum Graphiti image"
git push origin main
```

- [ ] **Step 6: Verify the GitHub Actions run and image manifest**

Run:

```bash
gh run list --workflow "Quorum Graphiti Image" --limit 1
gh run watch --exit-status
docker buildx imagetools inspect ghcr.io/ayansasmal/graphiti-mcp:sha-$(git rev-parse --short HEAD)
```

Expected: successful workflow; manifest contains `linux/amd64` and `linux/arm64`.

---

### Task 7: Full Fork Verification

**Files:**
- Modify only if failures reveal a defect in files touched by Tasks 1-6.

- [ ] **Step 1: Run formatting and static analysis**

```bash
uv run ruff check graphiti_core tests mcp_server/tests
uv run ruff format --check graphiti_core tests mcp_server/tests
uv run pyright graphiti_core
```

Expected: PASS.

- [ ] **Step 2: Run focused regressions**

```bash
uv run pytest \
  tests/prompts/test_quorum_prompt_regressions.py \
  tests/utils/maintenance/test_edge_operations.py \
  tests/utils/maintenance/test_entity_extraction.py \
  tests/utils/maintenance/test_node_operations.py \
  mcp_server/tests/test_quorum_image_contract.py \
  -v
```

Expected: PASS.

- [ ] **Step 3: Run the non-integration suite**

```bash
DISABLE_FALKORDB=1 DISABLE_KUZU=1 DISABLE_NEPTUNE=1 \
  uv run pytest -m "not integration"
```

Expected: PASS.

- [ ] **Step 4: Verify the working tree**

```bash
git status --short
git log --oneline origin/main..HEAD
```

Expected: clean after commits, or only expected unpushed commits before Task 6 push.

---

### Task 8: Pin the Verified Image in Quorum

**Files:**
- Modify: `/Users/ayan/Desktop/Work/vscode/qc/quorum/crossplane/environments/prod.yaml`
- Modify: `/Users/ayan/Desktop/Work/vscode/qc/quorum/crossplane/tests/rendered.yaml`
- Modify: `/Users/ayan/Desktop/Work/vscode/qc/quorum/docs/DEPLOYMENT-AWS.md`
- Modify: `/Users/ayan/Desktop/Work/vscode/qc/quorum/AGENTS.md`
- Modify: `/Users/ayan/Desktop/Work/vscode/qc/quorum/CLAUDE.md`

- [ ] **Step 1: Capture the verified image tag**

```bash
GRAPHITI_SHA=$(git -C ../graphiti/quorum-graphiti rev-parse --short HEAD)
GRAPHITI_TAG="sha-${GRAPHITI_SHA}"
docker buildx imagetools inspect "ghcr.io/ayansasmal/graphiti-mcp:${GRAPHITI_TAG}"
```

Expected: the immutable image exists with both required platforms.

- [ ] **Step 2: Write the rendered-config assertion first**

Add this test to `crossplane/tests/render.test.js`:

```javascript
it('pins Graphiti to an immutable fork image tag', () => {
  /** Canonical production environment input. */
  const environment = yaml.load(readFileSync('crossplane/environments/prod.yaml', 'utf8'))
  /** Rendered composite resource with normalized production inputs. */
  const renderedEnvironment = render().find((document) => document.kind === 'QuorumEnvironment')

  expect(environment.spec.images.graphitiTag).toMatch(/^sha-[0-9a-f]{7,40}$/)
  expect(renderedEnvironment.spec.images.graphitiTag).toBe(environment.spec.images.graphitiTag)
})
```

Run:

```bash
cd /Users/ayan/Desktop/Work/vscode/qc/quorum
npm run test:deploy -- --run crossplane/tests/render.test.js
```

Expected: FAIL because production still specifies `0.4.x`.

- [ ] **Step 3: Update the production pin**

Update the pin using the verified fork commit:

```bash
GRAPHITI_TAG="sha-$(git -C ../graphiti/quorum-graphiti rev-parse --short HEAD)"
perl -0pi -e 's/graphitiTag: "[^"]+"/graphitiTag: "'"${GRAPHITI_TAG}"'"/' \
  crossplane/environments/prod.yaml
```

Regenerate the checked-in render fixture:

```bash
bash crossplane/tests/render.sh > crossplane/tests/rendered.yaml
rg -n "${GRAPHITI_TAG}|graphiti-mcp" \
  crossplane/environments/prod.yaml crossplane/tests/rendered.yaml
```

Expected: `prod.yaml` contains the immutable tag and rendered bootstrap data carries the same
Graphiti tag into the production secret/bootstrap flow.

- [ ] **Step 4: Update deployment guidance**

Document:

- image verification with `docker buildx imagetools inspect`;
- explicit `graphitiTag` repinning;
- production reconvergence;
- health verification; and
- rollback to the previous immutable tag.

Update `AGENTS.md` and `CLAUDE.md` with the same operational direction.

- [ ] **Step 5: Run Quorum validation**

```bash
npm run test:gateway
npm test -- --run crossplane
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Commit the Quorum pin separately**

```bash
git add crossplane/environments/prod.yaml crossplane/tests/rendered.yaml docs/DEPLOYMENT-AWS.md AGENTS.md CLAUDE.md
git commit -m "chore(deploy): pin Quorum Graphiti image"
git push origin prod
```

---

### Task 9: Production Reconvergence and Verification

**Files:**
- No source files unless verification uncovers a defect.

- [ ] **Step 1: Reconverge using the canonical production operation**

Use the repository's existing AWS deployment/restart script or SSM operation. Do not manually edit
the host compose file.

Expected: bootstrap fetches the new `GRAPHITI_TAG`, pulls the immutable image, and recreates the
Graphiti service.

- [ ] **Step 2: Verify the running image and health**

Run through SSM:

```bash
docker inspect quorum-graphiti-1 --format='{{.Config.Image}}'
docker inspect quorum-graphiti-1 --format='{{.State.Health.Status}}'
docker exec quorum-graphiti-1 curl -sf http://127.0.0.1:8000/health
```

Expected:

```text
ghcr.io/ayansasmal/graphiti-mcp:sha-${GRAPHITI_SHA}
healthy
{"status":"healthy","service":"graphiti-mcp"}
```

- [ ] **Step 3: Run a controlled MCP ingestion check**

Use an MCP client to submit:

```text
[AUDIT] OUTCOME by ayansasmal | tool: remember | pos: verification
```

Expected:

- `add_memory` succeeds;
- the episode remains available for lineage;
- no self-referential `REMEMBERS` fact is created; and
- logs show the fewer-than-two-distinct-entities fast return without an edge-extraction LLM call.

- [ ] **Step 4: Verify ordinary two-entity extraction**

Submit:

```text
Alice congratulated Bob.
```

Expected: a valid `Alice -> CONGRATULATED -> Bob` fact is created, proving the guard did not disable
normal extraction.

- [ ] **Step 5: Record deployment evidence**

Append the verified image tag, health result, and controlled-ingestion result to the deployment
record or handoff document used for this production change. Do not include credentials, API keys,
or raw OpenAI prompt contents.
