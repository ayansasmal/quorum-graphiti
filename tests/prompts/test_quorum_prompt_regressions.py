from graphiti_core.prompts.dedupe_edges import resolve_edge


def test_resolve_edge_requires_conservative_fact_contradictions() -> None:
    messages = resolve_edge(
        {
            'existing_edges': [
                {
                    'idx': 0,
                    'fact': 'The Next.js Pages Router project entry point is pages/_app.tsx.',
                }
            ],
            'edge_invalidation_candidates': [],
            'new_edge': {
                'fact': 'Public review routes use NextAuth for authentication.',
            },
        }
    )

    rendered_prompt = '\n'.join(message.content for message in messages)

    assert 'conservative fact deduplication assistant' in rendered_prompt
    assert 'SAME specific subject or entity relationship' in rendered_prompt
    assert 'logically INCOMPATIBLE claims' in rendered_prompt
    assert 'Facts about different subjects are NEVER contradictions' in rendered_prompt
    assert 'Next.js Pages Router project entry point' in rendered_prompt
    assert 'public review routes using NextAuth' in rendered_prompt
    assert 'duplicate_facts=[], contradicted_facts=[]' in rendered_prompt
