# Quorum Graphiti Prompt Hardening Design

**Date:** 2026-06-14  
**Status:** Accepted — finalized 2026-06-14  
**Owner:** Quorum platform team

## Problem

OpenAI logs from the Quorum production Graphiti pipeline exposed four quality defects:

1. Fact invalidation marks unrelated facts as contradictions.
2. Edge extraction can hallucinate a self-referential edge when only one entity exists.
3. Batch entity summaries can attribute one entity's facts to a co-mentioned entity.
4. Previous-message prompt tags use both `PREVIOUS_MESSAGES` and `PREVIOUS MESSAGES`.

These prompts belong to `graphiti-core`, not Quorum's JavaScript governance endpoint. Quorum's
`POST /governance/detect-conflict` answers whether an incoming governed knowledge version
contradicts an existing version. Graphiti's fact deduplication and invalidation pipeline is a
separate process that runs after `add_memory`.

The existing Quorum Graphiti image also installs `graphiti-core` through a floating lower-bound
dependency. Rebuilding the same image source can therefore select different prompt behavior.

## Goals

- Make fact invalidation conservative for unrelated subjects and relationships.
- Prevent edge-extraction LLM calls when fewer than two distinct entities are available.
- Prevent self-referential edges even when model output violates instructions.
- Improve entity-specific attribution in summary prompts.
- Standardize previous-message prompt tags.
- Build the MCP server against the fork's exact local `graphiti_core` source.
- Publish immutable multi-platform images to GHCR.
- Keep production rollout explicit through Quorum's `graphitiTag` pin.

## Non-Goals

- Replacing Quorum's governance contradiction prompt.
- Dropping audit episodes from Graphiti.
- Automatically deploying every Graphiti `main` commit to Quorum production.
- Rewriting Graphiti's extraction architecture.
- Cleaning existing graph data as part of the prompt change.

## Approaches Considered

### 1. Patch installed `site-packages` during the Quorum Docker build

This is fast but brittle. Patches depend on package layout, are difficult to unit test beside the
source, and can silently fail when upstream files move.

### 2. Publish a private patched Python package

This gives exact dependency control but adds package publication, versioning, and registry
credentials without providing value beyond the container artifact Quorum already deploys.

### 3. Build from the Quorum-maintained Graphiti fork

This is the selected approach. Prompt code and tests remain together, upstream changes can be
merged normally, and the resulting container is the only artifact Quorum needs.

## Design

### Fact invalidation

Update `graphiti_core/prompts/dedupe_edges.py` so contradiction requires:

- the same specific subject or entity relationship;
- logically incompatible claims about that same subject or relationship; and
- enough evidence to prefer invalidation over coexistence.

The prompt will include a negative example where routing, database, and authentication facts do
not contradict one another. Existing continuous index semantics remain unchanged:
`duplicate_facts` can reference only existing facts, while `contradicted_facts` can reference both
existing facts and invalidation candidates.

This remains a prompt change because semantic contradiction cannot be determined reliably with a
generic deterministic parser.

### Edge extraction

Add a deterministic precondition at the Graphiti extraction-call boundary
(`graphiti_core/utils/maintenance/edge_operations.py`, before the `extract_edges()` LLM call at the
`ExtractedEdges` response):

1. Normalize entity names using the same comparison semantics already used by the extraction
   pipeline.
2. Count distinct non-empty names.
3. If fewer than two exist, return `ExtractedEdges(edges=[])` without calling the LLM.

Retain and strengthen prompt instructions that source and target must be distinct and facts must
be supported by the current message.

Add deterministic post-validation in the same module, after the LLM response is parsed into
`ExtractedEdges`, that rejects any model-produced edge whose normalized source and target names are
equal. This protects the graph even when a model ignores the prompt.

Audit episodes continue through `add_memory`. Only relationship extraction is skipped when a valid
two-entity relationship cannot exist.

### Entity summaries

Extend the shared summary instructions (`graphiti_core/prompts/snippets.py`, `summary_instructions`)
and the batch-summary prompt (`graphiti_core/prompts/summarize_nodes.py`, `summarize_context` and
`summarize_pair`) with an attribution rule:

- include only facts directly and specifically describing the entity being summarized;
- do not transfer facts from co-mentioned entities;
- preserve an existing summary when the new message has no entity-specific durable fact.

The rule applies to both ordinary batch summaries and episode-based summaries. Any semantically
mirrored prompt must be updated in the same change.

### Prompt tags

Standardize prompt delimiters on valid underscore names:

```text
<PREVIOUS_MESSAGES>
</PREVIOUS_MESSAGES>
```

The spaced `<PREVIOUS MESSAGES>` variant currently appears in five prompt modules —
`extract_nodes_and_edges.py`, `extract_nodes.py`, `dedupe_nodes.py`, `extract_edges.py`, and
`eval.py` — and `extract_edges.py` carries both variants. The four ingestion-path modules
(`extract_nodes_and_edges`, `extract_nodes`, `dedupe_nodes`, `extract_edges`) are normalized to the
underscore form and are the "production prompt modules" the tests assert against;
`graphiti_core/prompts/eval.py` is an offline evaluation module and is out of scope. This is prompt
consistency rather than an application-parser fix. Tests will prevent either spaced variant from
being reintroduced in production prompt modules.

### Container build

Add a Quorum standalone MCP Dockerfile at `mcp_server/docker/Dockerfile.quorum` with the repository
root as its build context. The root context is required so the build can install the fork's local
`graphiti_core` source rather than a PyPI release. It will:

1. install the root `graphiti-core` project from local source;
2. install `mcp_server` against that local package;
3. preserve Quorum's `0.0.0.0` transport behavior;
4. expose the existing health endpoint; and
5. label the image with the source commit.

The build must not rewrite the MCP dependency to a PyPI `graphiti-core>=...` range.

### Image publication

A fork-owned GitHub Actions workflow will:

- run prompt and extraction regression tests;
- build `linux/amd64` and `linux/arm64`;
- publish `ghcr.io/ayansasmal/graphiti-mcp:sha-<commit>`;
- optionally update a convenience `main` tag, which production must never consume; and
- use `GITHUB_TOKEN` with `packages: write`.

Publishing succeeds independently of Quorum deployment.

### Quorum integration

After the image is built and verified:

1. update `quorum/crossplane/environments/prod.yaml` to the immutable `sha-...` tag;
2. update deployment documentation and generated validation fixtures;
3. reconverge the production environment; and
4. verify the Graphiti container image, health, and a controlled ingestion case.

The Graphiti source commit and Quorum deployment-pin commit remain separate for traceability.

## Testing

### Deterministic unit tests

- Rendered fact-deduplication prompt contains same-subject and incompatible-claim rules.
- Rendered prompt contains an unrelated-facts negative example.
- Edge extraction skips the LLM for zero entities, one entity, and duplicate entity names.
- Edge extraction still calls the LLM for two distinct entities.
- Post-validation rejects self-referential edges.
- Summary prompts contain entity-specific attribution rules.
- Production prompt modules contain no `<PREVIOUS MESSAGES>` tags.
- Docker build installs local `graphiti-core`, confirmed through image metadata and an import-path
  assertion.

### Live-model regression tests

Live tests are non-blocking for fork pull requests without an OpenAI key and blocking for protected
same-repository runs:

- the reported Next.js, Prisma, and NextAuth facts produce no contradictions;
- a one-entity audit episode produces no edges and consumes no edge-extraction LLM call;
- `/api/auth/[...nextauth]` receives only its own endpoint facts in its summary.

### Container verification

- Build the image locally for the host platform.
- Start it with FalkorDB and the required environment.
- Verify `/health`.
- Use an MCP client to call `add_memory`.
- Confirm the running package resolves to the forked source version.

## Error Handling and Rollback

- A failed prompt regression blocks image publication.
- A failed multi-platform build publishes no deployable tag.
- A published image is not production until Quorum explicitly pins it.
- Rollback changes `graphitiTag` to the previously verified immutable image tag and reconverges.
- Existing malformed graph facts are handled separately through a reviewed repair or re-ingestion
  procedure; this change does not hard-delete graph data.

## Success Criteria

- The four reported prompt issues have deterministic regression coverage.
- The one-entity edge path does not invoke the LLM.
- Self-referential edges cannot pass deterministic validation.
- The image contains the fork's exact `graphiti-core` source.
- GHCR contains a multi-platform immutable `sha-...` image.
- Quorum production runs the explicitly pinned image and remains healthy.
