# MCP Docker Host Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Quorum job containers to call Graphiti MCP through Docker DNS while retaining MCP SDK DNS-rebinding protection.

**Architecture:** Configure the existing `FastMCP` instance with an explicit transport-security allowlist for Docker and loopback hostnames. Lock the behavior with a focused regression test that exercises the SDK middleware's host validation.

**Tech Stack:** Python 3.11, MCP Python SDK 1.27.2, FastMCP, Pydantic, pytest.

---

### Task 1: Add the host-security regression test

**Files:**
- Modify: `mcp_server/tests/test_quorum_image_contract.py`

- [ ] **Step 1: Write the failing test**

Import the MCP server module and assert its `FastMCP` transport settings keep
protection enabled, accept `graphiti:8000`, and reject `untrusted.example`.

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
UV_CACHE_DIR=/tmp/quorum-graphiti-uv-cache uv run --project mcp_server \
  pytest mcp_server/tests/test_quorum_image_contract.py \
  -k docker_hostname -q
```

Expected: FAIL because the current implicit allowlist contains only loopback
hosts.

### Task 2: Configure explicit transport security

**Files:**
- Modify: `mcp_server/src/graphiti_mcp_server.py`

- [ ] **Step 1: Import the SDK security settings**

Add:

```python
from mcp.server.transport_security import TransportSecuritySettings
```

- [ ] **Step 2: Configure the existing `FastMCP` instance**

Pass explicit settings:

```python
transport_security=TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=['graphiti:*', 'localhost:*', '127.0.0.1:*', '[::1]:*'],
    allowed_origins=[
        'http://graphiti:*',
        'http://localhost:*',
        'http://127.0.0.1:*',
        'http://[::1]:*',
    ],
),
```

- [ ] **Step 3: Run the focused test to verify GREEN**

Run the Task 1 command. Expected: PASS.

### Task 3: Update repository guidance

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Document the internal MCP hostname contract**

Record that Docker clients use `graphiti:8000`, the explicit allowlist must be
preserved, and public access remains gated by Quorum Gateway.

- [ ] **Step 2: Open changed markdown through show-md**

Start the viewer idempotently and open each changed markdown file with its
absolute path.

### Task 4: Verify and commit

- [ ] **Step 1: Run focused tests**

```bash
UV_CACHE_DIR=/tmp/quorum-graphiti-uv-cache uv run --project mcp_server \
  pytest mcp_server/tests/test_quorum_image_contract.py -q
```

- [ ] **Step 2: Run formatting and lint**

```bash
UV_CACHE_DIR=/tmp/quorum-graphiti-uv-cache uv run --project mcp_server ruff check \
  mcp_server/src/graphiti_mcp_server.py \
  mcp_server/tests/test_quorum_image_contract.py
```

- [ ] **Step 3: Commit using Conventional Commits**

```bash
git add AGENTS.md README.md mcp_server/src/graphiti_mcp_server.py \
  mcp_server/tests/test_quorum_image_contract.py docs/superpowers/
git commit -m "fix(mcp): allow graphiti docker host"
```

### Task 5: Publish and verify immutable image

- [ ] **Step 1: Push the commit**

Push `main` so the Graphiti image workflow builds the commit-derived tag.

- [ ] **Step 2: Verify CI and GHCR**

Wait for the image workflow to succeed and verify
`ghcr.io/ayansasmal/graphiti-mcp:sha-<commit>` exists.

- [ ] **Step 3: Request production deployment approval**

Do not modify `GRAPHITI_TAG` until the user separately approves the exact
immutable tag.
