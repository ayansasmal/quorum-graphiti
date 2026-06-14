from graphiti_core.prompts.dedupe_edges import resolve_edge


def test_resolve_edge_requires_conservative_fact_contradictions() -> None:
    existing_fact_sentinel = 'SENTINEL existing lunar archive uses SQLite'
    invalidation_candidate_sentinel = 'SENTINEL candidate lunar archive uses PostgreSQL'
    new_fact_sentinel = 'SENTINEL new orbital telemetry uses NATS'

    messages = resolve_edge(
        {
            'existing_edges': [
                {
                    'idx': 0,
                    'fact': existing_fact_sentinel,
                }
            ],
            'edge_invalidation_candidates': [
                {
                    'idx': 1,
                    'fact': invalidation_candidate_sentinel,
                }
            ],
            'new_edge': {
                'fact': new_fact_sentinel,
            },
        }
    )

    rendered_prompt = '\n'.join(message.content for message in messages)

    assert 'conservative fact deduplication assistant' in rendered_prompt
    assert 'SAME specific subject or entity relationship' in rendered_prompt
    assert 'logically INCOMPATIBLE claims' in rendered_prompt
    assert 'Facts about different subjects are NEVER contradictions' in rendered_prompt
    assert 'return an empty contradicted_facts list' in rendered_prompt
    assert 'When uncertain, return empty lists.' not in rendered_prompt
    assert existing_fact_sentinel in rendered_prompt
    assert invalidation_candidate_sentinel in rendered_prompt
    assert new_fact_sentinel in rendered_prompt
    assert 'Next.js Pages Router project entry point' in rendered_prompt
    assert 'public review routes using NextAuth' in rendered_prompt
    assert 'duplicate_facts=[], contradicted_facts=[]' in rendered_prompt
