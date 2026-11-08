"""Prometheus metrics for the query pipeline (section 4.8).

Request count and latency live in routes/metrics.py. These cover the stages of the
pipeline. The cache hit ratio is hits / (hits + misses) over rahbar_cache_lookups_total.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

RETRIEVAL_SECONDS = Histogram(
    "rahbar_retrieval_seconds", "Question embedding plus vector search",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
GENERATION_SECONDS = Histogram(
    "rahbar_generation_seconds", "LLM call, including the one retry",
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 40, 60, 120),
)
CACHE_LOOKUPS = Counter(
    "rahbar_cache_lookups_total", "Semantic cache lookups", ["result"],  # hit | miss | skipped
)
ABSTENTIONS = Counter(
    "rahbar_abstentions_total", "Questions declined because the documents do not cover them",
)
FALLBACKS = Counter(
    "rahbar_fallbacks_total", "Canned responses given after the model failed validation twice",
)
INVALID_CITATIONS = Counter(
    "rahbar_invalid_citations_total",
    "Model citations dropped because no such passage was retrieved",
)
TOKENS = Counter("rahbar_tokens_total", "LLM tokens used", ["direction"])  # in | out