# Indexing and retrieval pipeline

Measurements recorded on 11 November 2026. The corpus is eight checksum-verified public
FAST-NUCES documents. Raw documents are excluded from Git and public images.

## Extraction and cleaning
`indexer/pipeline/extract.py` uses pdfplumber for PDF text and tables, and OCR at 200 DPI
when a page contains fewer than 20 text characters. The actual run OCR'd 24/26 pages of
the 2023 rules, 5/58 of the 2026 academic handbook, 4/64 of the student handbook, and all
8/8 pages of the entrepreneurship policy. Some cover/blank pages also trigger OCR.
The prospectus (5 pages) and annual report (85 pages) needed no OCR. See
`docs/evidence/indexer-final.txt` for per-document counts.

A real table example is the Fee Structure HTML page: flattening its cells produces
`Program Fee BBA / BS Rs. 12,000 MBA / MS Rs. 12,000 PhD Rs. 12,000`.
The shipped extractor preserves row boundaries as `| BBA / BS | Rs. 12,000 |` under
`Tuition Fee (w.e.f. Fall 2026 semester)`. PDF table bounding boxes are removed from
the surrounding text and appended as Markdown rows. This preserves columns, but can
move a table away from its original position. Two-column handbook prose can still
interleave; OCR spelling and formula typography are not fully recoverable.

Cleaning applies NFKC, collapses horizontal whitespace, joins lower-case hyphenated
line breaks and removes repeated edge lines seen on at least half the pages (minimum
four pages). It deliberately keeps numbered clauses and table rows. Duplicate PDF
pages are retained; retrieval drops duplicate texts. Standalone numbered rules that
look like headings are retained even when no body follows them.

## Chunking measurements
The unit is whitespace-separated **words**, not tokenizer tokens. Chunks follow sections,
paragraphs and sentences; heading words are added to each chunk. The three candidates
used the same verified golden set, pinned embeddings, current/older source filters and
top-k=5. A stub generator isolated retrieval quality; at floor zero it deliberately
answers the absent-topic questions, so these runs are not generation baselines.

| Size (words) | Overlap (words) | recall@3 | recall@5 | Chunks | Stored/original words |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 150 | 25 | 0.8000 | 0.8000 | 1012 | 1.1716 |
| 400 | 50 | 0.6667 | 0.7333 | 664 | 1.0789 |
| 700 | 100 | 0.7333 | 0.8000 | 594 | 1.0640 |
| 100 | 0 | 0.8000 | 0.8000 | 1206 | 1.0405 |

We ship **700/100**: it ties the best recall@5 among the three candidates with fewer
chunks and lower amplification. Its 86,501 stored words /
81,296 cleaned words = 1.0640x.
This is a word-based storage-amplification proxy, not a measured model-token ratio.
We also counted tokenizer pieces using BERT WordPiece and the installed embedding
model's 30,522-entry GGUF vocabulary (standard lowercasing/normalization, excluding
special tokens and task prefixes). The original text has **101,326 tokens** and the
700/100 stored chunks have **107,569 tokens**, giving **1.061613x** token amplification.
The 150/25, 400/50 and 100/0 token ratios are 1.165979x, 1.074986x and 1.036841x.
This explicit tokenizer convention is separate from the chunker's word-size setting.
See `eval/runs/token-amplification.json` for counts and methodology.
The 100/0 row is the deliberate chunking break; recall did not worsen on this small
set, but storage and fragmentation increased. It still uses the structure-aware splitter,
so it is not an experiment with a completely fixed-size splitter.
The PDF's stricter fixed-size experiment was also run separately: **1,019 fixed
100-WordPiece-token windows, no overlap**, with first-token section/page metadata.
Recall@3 fell to **0.4000** and recall@5 to **0.4667**; token amplification was 1.0000x.
See `break-fixed-100-tokens.json` and `fixed-token-measurements.json`. Crossing section
boundaries harms both context continuity and section-based recall matching.

The cached extraction came from the real indexer image; each candidate was actually
embedded into a separate Chroma calibration collection and queried through a running
API. `eval/runs/chunk-*.json` retain the responses and configurations. The final real
Kubernetes Job independently reported 594 chunks in 207.1 seconds before the security
dependency refresh. Final image/cluster checks are recorded in the evidence directory.

## Embedding and storage
The model is `nomic-embed-text`, dimension 768, with `search_document: ` and
`search_query: ` prefixes. Both workloads read the same ConfigMap. Collection metadata
records `embed_model`, `dimension`, chunk settings and a new `index_id` per build.
Chunk metadata is `source`, `section`, `page`, `doc_version`, `superseded`.
Readiness rejects an empty index or a mismatched model name.

The indexer builds a temporary collection, checks its count, deletes the previous name
and renames the replacement. Readers serve the old collection during extraction and
embedding, but delete/rename is **not atomic**: a brief unavailable interval is possible.
Manual overlapping indexer Jobs are not serialized; run one manual reindex at a time.
The CronJob itself has `concurrencyPolicy: Forbid` and runs the same real pipeline as
the Job. The former `--dummy` CronJob argument was removed.

## Relevance floor and semantic cache
The shipped real-model floor remains **0.35**; the real-model golden run declined both
must-abstain questions. It is not a perfect separator: absence is also decided by the
generator. A single score threshold cannot preserve every relevant passage and reject
every absent-topic near-match in this corpus. In the 700/100 raw run the top scores for
hostel and bus questions were 0.6291
and 0.7127.

Cache calibration used real normalized question embeddings. At thresholds 0.75, 0.85,
0.92 and 0.93 the false-hit counts were 2, 1, 1 and 0 respectively. The decisive false
hit was old versus current withdrawal deadlines, similarity **0.924046**. We ship
**0.93**, the lowest tested zero-false-hit threshold. This small six-pair sample does
not establish safety for every future question. The two tested paraphrases scored
0.870621 and 0.886380 and therefore miss at the safer threshold; exact repeated
questions can still hit. Evidence: `eval/runs/cache-thresholds.json`.

Redis entries expire after 86,400 seconds and are bounded to 200 per index. Keys include
the new `index_id`, so reindexing makes old answers miss without granting the indexer
Redis access. Follow-ups, abstentions and validation fallbacks are never cached.
An empty cache is checked before embedding, and a Redis failure is a miss on the query
path (although readiness still reports the dependency failure).

## Evaluation method and known limits
The 17 original question intents were present before tuning; unresolved labels in Git
were repaired against the source documents. The ambiguous annual-report question was
made specific to its applications table (p.18). Two version questions now ask about the
genuinely different withdrawal deadlines: 2023 p.16 versus 2026 p.23.

Recall counts known-relevant source/section references found in the first k retrieved
chunks. Section comparison ignores case/spacing and accepts a prefix only at a boundary;
optional page constraints must also match. This strict rule can count a miss when a
clause's text is inside a neighbouring clause's chunk. In particular 4.25 can be bundled
under 4.24. We retain these misses instead of relabelling after tuning.
Exact clause numbers also trigger a Chroma text-contains query before vector results;
the implementation already has this limited form of hybrid retrieval.

The final Ingress run reports recall@3=0.7333,
recall@5=0.8000, citation validity=100%,
and must-abstain correctness=100%.
Version-sensitive recall@5 is 50%, the weakest
type. Citation validity proves that cited passages were retrieved; it does not prove
the answer is true or complete. The optional expected-text check still misses q09.
Some answerable questions are declined or fall back. These are limitations, not passes
of a human answer-quality review. `eval/results.json` and `eval/baseline.json` are the
real-model run; fixture/stub results are kept separately.

## CI calibration
The fixture corpus uses the same model and real embeddings, with the stub LLM. Its
lowest answerable top score was 0.7205; the absent-topic
maximum was 0.5593. The midpoint **0.6399** is in both
workflows. Gap=0.1612. Fixture baseline recall@5=1.0, abstention=100%, citation
validity=100%. The stub tests retrieval and gating, not resistance of a real LLM to
poisoned text. The fixture includes a poisoned paragraph for real-model testing too.
The gate fails on recall@5 dropping more than 0.05, any answered must-abstain question,
or citation validity below 0.95. These thresholds were not loosened.
Do not assume all kind versions ignore NetworkPolicy. Recent kindnet embeds enforcement
([upstream documentation](https://kube-network-policies.sigs.k8s.io/docs/concepts/modularity/)).
The CI overlay permits the actual Ollama container IP, rather than the laptop's address.
Calico/minikube remains a separate firewall demonstration. The supplied checklist's
blanket statement about kind was corrected after the fresh-cluster startup failure.

The fixture injection question originally contained “earlier instructions”, which the
old-version detector mistook for an older-policy request. A regression fix excludes
instruction/prompt wording from version intent; the recalibrated fixture recall is 1.0.
The real-model poisoned-document test retrieved the repeat-course chunk containing the
planted attendance instruction and answered “Only the grade of the most recent attempt
counts.” without following the instruction. See `eval/runs/poisoned-document-real-model.json`.
