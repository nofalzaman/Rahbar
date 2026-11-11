# ADR 0003: Structure-aware chunks, and the corpus baked into the indexer image

## Status
Accepted · 2026-11-11

## Context
Fixed-size chunks cut definitions and tables in half. The FAST-NUCES documents must not be
published, but the Job needs them inside the cluster.

## Decision
`indexer/pipeline/chunk.py` splits on section headings, then paragraphs, then sentences,
under a size limit counted in words, with overlap, and starts each chunk with its heading.
The shipped size and overlap come from the measurements in `docs/PIPELINE.md`. The corpus
reaches the Job as part of the indexer image, through a named build context:
`--build-context corpus=./corpus/raw` for local images and `./eval/fixtures` for every image
CI builds and publishes. The real documents never enter a published image.

## Options considered
A volume populated with `kubectl cp` would keep documents out of images entirely, but adds
a manual step to every fresh cluster and to the weekly CronJob. A ConfigMap is limited to
1 MiB.

## Consequences
A local indexer image is not publishable and must be rebuilt when the corpus changes.
Chunk size counts words, not model tokens, so the numbers are approximate.
