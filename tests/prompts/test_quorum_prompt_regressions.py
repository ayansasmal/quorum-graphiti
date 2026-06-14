import pytest

from graphiti_core.prompts.dedupe_edges import resolve_edge
from graphiti_core.prompts.extract_nodes import (
    extract_entity_summaries_from_episodes,
    extract_summaries_batch,
)
from graphiti_core.prompts.summarize_nodes import summarize_context, summarize_pair

CANONICAL_ATTRIBUTION_BLOCK = (
    'ATTRIBUTION: Include only facts that directly and specifically describe the entity being '
    'summarized.\n'
    'Do not carry over facts about co-mentioned entities, even when they are topically related.'
)


def _content(messages: list) -> str:
    return '\n'.join(message.content for message in messages)


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

    rendered_prompt = _content(messages)

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


@pytest.mark.parametrize(
    ('prompt_function', 'context'),
    [
        (
            extract_summaries_batch,
            {
                'previous_episodes': [{'content': 'Avery founded Northwind.'}],
                'episode_content': 'Avery: Northwind hired Mina as CTO.',
                'entities': [
                    {'name': 'Avery', 'summary': 'Avery founded Northwind.'},
                    {'name': 'Northwind', 'summary': 'Northwind was founded by Avery.'},
                ],
            },
        ),
        (
            extract_entity_summaries_from_episodes,
            {
                'previous_episodes': [{'content': 'Avery founded Northwind.'}],
                'episode_content': 'Avery: Northwind hired Mina as CTO.',
                'entities': [
                    {'name': 'Avery', 'summary': 'Avery founded Northwind.'},
                    {'name': 'Northwind', 'summary': 'Northwind was founded by Avery.'},
                ],
            },
        ),
        (
            summarize_context,
            {
                'previous_episodes': [{'content': 'Avery founded Northwind.'}],
                'episode_content': 'Avery: Northwind hired Mina as CTO.',
                'node_name': 'Northwind',
                'node_summary': 'Northwind was founded by Avery.',
                'attributes': {'industry': {'description': 'Northwind industry'}},
            },
        ),
        (
            summarize_pair,
            {
                'node_summaries': [
                    {'summary': 'Avery founded Northwind.'},
                    {'summary': 'Northwind hired Mina as CTO.'},
                ],
            },
        ),
    ],
)
def test_entity_summary_prompts_include_canonical_attribution_block(
    prompt_function,
    context: dict,
) -> None:
    rendered_prompt = _content(prompt_function(context))

    assert CANONICAL_ATTRIBUTION_BLOCK in rendered_prompt


def test_summary_context_preserves_entity_context() -> None:
    rendered_prompt = _content(
        summarize_context(
            {
                'previous_episodes': [{'content': 'Avery founded Northwind.'}],
                'episode_content': 'Avery: Northwind hired Mina as CTO.',
                'node_name': 'Northwind',
                'node_summary': 'Northwind was founded by Avery.',
                'attributes': {'industry': {'description': 'Northwind industry'}},
            }
        )
    )

    assert 'New facts must be supported by MESSAGES' in rendered_prompt
    assert 'Preserve durable facts from ENTITY CONTEXT' in rendered_prompt
    assert (
        'If MESSAGES add no entity-specific durable fact, preserve the existing summary unchanged.'
        in rendered_prompt
    )
    assert (
        'summary must only use\n        information from the provided MESSAGES'
        not in rendered_prompt
    )


def test_summary_pair_preserves_explicit_grammatical_subjects() -> None:
    rendered_prompt = _content(
        summarize_pair(
            {
                'node_summaries': [
                    {'summary': 'Avery founded Northwind.'},
                    {'summary': 'Northwind hired Mina as CTO.'},
                ],
            }
        )
    )

    assert CANONICAL_ATTRIBUTION_BLOCK in rendered_prompt
    assert (
        "Preserve each statement's explicit grammatical subject; include only facts that directly "
        'and specifically describe that subject.' in rendered_prompt
    )
    assert (
        'Never reassign a fact to another named subject or co-mentioned entity.' in rendered_prompt
    )
    assert (
        'Keep facts about co-mentioned entities attached to their own explicit grammatical '
        'subjects, even when the facts are topically related.' in rendered_prompt
    )
    assert 'entity ownership' not in rendered_prompt


@pytest.mark.parametrize(
    'prompt_function',
    [extract_summaries_batch, summarize_context],
)
def test_shared_summary_prompts_preserve_existing_summary_without_new_entity_facts(
    prompt_function,
) -> None:
    context = {
        'previous_episodes': [{'content': 'Avery founded Northwind.'}],
        'episode_content': 'Avery: Northwind hired Mina as CTO.',
        'entities': [{'name': 'Northwind', 'summary': 'Northwind was founded by Avery.'}],
        'node_name': 'Northwind',
        'node_summary': 'Northwind was founded by Avery.',
        'attributes': {'industry': {'description': 'Northwind industry'}},
    }

    rendered_prompt = _content(prompt_function(context))

    assert (
        'Preserve the existing summary when new messages contain no entity-specific durable fact.'
        in rendered_prompt
    )


def test_episode_summary_prompt_preserves_existing_summary_without_new_durable_fact() -> None:
    rendered_prompt = _content(
        extract_entity_summaries_from_episodes(
            {
                'previous_episodes': [{'content': 'Avery founded Northwind.'}],
                'episode_content': 'Avery: Northwind hired Mina as CTO.',
                'entities': [
                    {'name': 'Avery', 'summary': 'Avery founded Northwind.'},
                    {'name': 'Northwind', 'summary': 'Northwind was founded by Avery.'},
                ],
            }
        )
    )

    assert CANONICAL_ATTRIBUTION_BLOCK in rendered_prompt
    assert (
        'If the new episodes add no durable fact, return the existing summary unchanged.'
        in rendered_prompt
    )
