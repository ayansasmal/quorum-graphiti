"""Static contract tests for the Quorum Graphiti MCP container image."""

from pathlib import Path

import tomllib

DOCKERFILE_PATH = Path(__file__).parents[1] / 'docker' / 'Dockerfile.quorum'
MCP_PYPROJECT_PATH = Path(__file__).parents[1] / 'pyproject.toml'


def read_dockerfile() -> str:
    """Return the Quorum Dockerfile text after asserting that it exists."""
    assert DOCKERFILE_PATH.is_file(), f'Missing Quorum Dockerfile: {DOCKERFILE_PATH}'
    return DOCKERFILE_PATH.read_text()


def test_installs_graphiti_core_from_the_repository_checkout() -> None:
    """The image must package the fork's local core with FalkorDB support."""
    dockerfile_text = read_dockerfile()

    assert 'FROM python:3.11-slim' in dockerfile_text
    assert 'apt-get install -y --no-install-recommends' in dockerfile_text
    assert 'curl' in dockerfile_text
    assert 'ca-certificates' in dockerfile_text
    assert 'WORKDIR /app/graphiti' in dockerfile_text
    assert 'COPY pyproject.toml uv.lock README.md ./' in dockerfile_text
    assert 'COPY graphiti_core ./graphiti_core' in dockerfile_text
    assert 'python -m pip install --no-cache-dir "/app/graphiti[falkordb]"' in dockerfile_text
    assert 'graphiti-core>=' not in dockerfile_text
    assert 'astral.sh/uv' not in dockerfile_text


def test_installs_mcp_with_metadata_and_local_core_dependency_removed() -> None:
    """The MCP install must retain extras without replacing the local core."""
    dockerfile_text = read_dockerfile()

    pyproject_copy = dockerfile_text.index(
        'COPY mcp_server/pyproject.toml ./pyproject.toml'
    )
    readme_copy = dockerfile_text.index('COPY mcp_server/README.md ./README.md')
    source_copy = dockerfile_text.index('COPY mcp_server/src ./src')
    dependency_removal = dockerfile_text.index(
        "sed -i '/graphiti-core\\[falkordb\\]/d' pyproject.toml"
    )
    mcp_install = dockerfile_text.index(
        'python -m pip install --no-cache-dir ".[providers,azure]"'
    )

    assert pyproject_copy < dependency_removal < mcp_install
    assert readme_copy < mcp_install
    assert source_copy < mcp_install
    assert 'COPY mcp_server/main.py ./main.py' in dockerfile_text
    assert 'COPY mcp_server/config ./config' in dockerfile_text


def test_sanitized_mcp_metadata_remains_valid() -> None:
    """Removing the PyPI core dependency must preserve valid MCP package metadata."""
    sanitized_text = '\n'.join(
        line
        for line in MCP_PYPROJECT_PATH.read_text().splitlines()
        if 'graphiti-core[falkordb]' not in line
    )
    metadata = tomllib.loads(sanitized_text)

    assert all(
        not dependency.startswith('graphiti-core')
        for dependency in metadata['project']['dependencies']
    )
    assert metadata['project']['optional-dependencies']['providers']
    assert metadata['project']['optional-dependencies']['azure']


def test_exposes_streamable_http_runtime_contract() -> None:
    """The image must expose the HTTP server and its health endpoint."""
    dockerfile_text = read_dockerfile()

    assert 'MCP_SERVER_HOST="0.0.0.0"' in dockerfile_text
    assert 'EXPOSE 8000' in dockerfile_text
    assert 'http://localhost:8000/health' in dockerfile_text
    assert 'CMD ["python", "main.py"]' in dockerfile_text


def test_sets_required_oci_image_labels() -> None:
    """The image must carry traceable OCI source, revision, and title labels."""
    dockerfile_text = read_dockerfile()

    assert 'ARG VCS_REF' in dockerfile_text
    assert 'org.opencontainers.image.title=' in dockerfile_text
    assert 'org.opencontainers.image.source=' in dockerfile_text
    assert 'org.opencontainers.image.revision="${VCS_REF}"' in dockerfile_text
