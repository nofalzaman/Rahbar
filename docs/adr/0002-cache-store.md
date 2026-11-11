# ADR 0002: Redis for the semantic cache, keyed by index id

## Status
Accepted · 2026-11-11

## Context
A repeated question, however it is phrased, should not pay for a model call. The cache must
survive an api restart, must not serve answers from an index that has since been rebuilt,
and must never cache a mistake.

## Decision
Redis (`k8s/base/redis.yaml`, a Deployment with the `cache-data` PVC). Entries hold a
normalised question embedding and the answer; `api/app/services/cache.py` compares them in
Python and counts a hit at or above `CACHE_THRESHOLD`. The indexer writes a fresh
`index_id` into the Chroma collection metadata on every build, and every cache key
includes it. After a re-index the new `index_id` makes every old entry miss, without the
indexer ever touching Redis, which keeps the NetworkPolicy rule "redis from api only".
Follow-ups, abstentions, out-of-scope answers and anything that failed validation are never
cached (`never_cache` in `cache.py`). The cache is bounded (`CACHE_MAX_ENTRIES`) and entries
have a TTL. A dead Redis is a cache miss, not an error.

## Options considered
A second Chroma collection would reuse infrastructure we already run, but it would give the
api write access to the vector store, which breaks "the indexer is the only writer". An
in-process dict is lost on restart and not shared by the three replicas.

## Consequences
One more stateful service. Plain Redis has no vector search, so the lookup reads every
entry (at most 200) and compares in Python; that is fine at this size and would not scale to
a large cache. The threshold is measured, not guessed: see `docs/PIPELINE.md`.
