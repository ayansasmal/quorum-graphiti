# MCP Docker Host Security Design

## Problem

Quorum production calls the Graphiti MCP endpoint through Docker DNS at
`http://graphiti:8000/mcp`. Graphiti constructs `FastMCP` with its default
`127.0.0.1` host and later changes the bind address to `0.0.0.0`. MCP Python SDK
1.27.2 therefore retains its automatically generated localhost-only transport
security allowlist and rejects the Docker hostname with HTTP 421:
`Invalid Host header`.

## Design

Construct `FastMCP` with explicit `TransportSecuritySettings` that keep DNS
rebinding protection enabled and allow only the expected local and container
hostnames:

- `graphiti:*` for Quorum's internal Docker network
- `localhost:*`
- `127.0.0.1:*`
- `[::1]:*`

Allow matching HTTP origins for local browser or integration clients. Production
Quorum job requests do not send an Origin header, which the SDK permits for
same-origin and non-browser clients.

## Security Boundary

Do not disable DNS rebinding protection and do not use a wildcard host. Graphiti
remains reachable only on the internal Docker network in the AWS deployment;
the public gateway remains the authenticated external access boundary.

## Testing

Add a regression test that inspects the configured FastMCP transport security
settings and proves:

1. DNS rebinding protection remains enabled.
2. `graphiti:8000` is accepted.
3. an unrelated host is rejected.

Run the focused MCP tests, formatting, and lint checks before publishing the
immutable multi-platform image.

## Deployment

Publish `ghcr.io/ayansasmal/graphiti-mcp:sha-<commit>`. Publishing does not
deploy automatically. Quorum production requires separate approval before
updating `GRAPHITI_TAG` and reconverging the EC2 host.
