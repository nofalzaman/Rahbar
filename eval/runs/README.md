# Measurement provenance

The `chunk-*` runs use real embeddings and a stub generator at floor zero to isolate
retrieval. Their absent-topic failures are expected and are not the shipped baseline.
`chunk-measurements.json` records the size/overlap, counts and word amplification.
The 100/0 run is the deliberate small-chunk break.

`generation-low-temperature.json` and `break-generation-high-temperature.json` use
the real Ollama LLM against the separate calibration collection, with the cache off.
`generation-repeat.json` records five uncached high-temperature requests and their
actual identical safe fallbacks. `break-source.json` includes raw version metadata;
`break-retrieval-top1.json` limits retrieval to one passage.

`fixtures-raw.json` deliberately fails abstention at floor zero. `fixtures-final.json`
passes at the measured floor in `fixture-floor.json`, using fictional fixture documents
and the stub LLM. `poisoned-document-real-model.json` separately uses the real model
on a retrieved poisoned fixture paragraph.

`previous-chunk-*` were recovered from the earlier local project directory. Their
all-zero recall comes from unresolved golden labels at that time. They are retained
as historical evidence of the calibration mistake and must not be used as a baseline.
`index-sections.json` is an earlier metadata inventory, not a quality measurement.

The submission baseline and final real-corpus Ingress results live one directory up:
`eval/baseline.json` and `eval/results.json`.
