# RAHBAR Assignment 03

Read `docs/codex/RAGOPS-SPEC.md`, then `docs/codex/HANDOFF.md` before editing.

- Preserve the Assignment 02 pipeline; RAGOps uses a separate verified ingestion entry point.
- Only ingestion Jobs write Chroma. API, evaluation and report tools only read it.
- Never commit credentials, raw third-party corpus files, or manufactured measurements.
- Preserve the configured checkout identities. Nofal owns API, Kubernetes, scripts, workflows and cluster evidence; Aoun owns data verification and evaluation. Describe shared fixes in PRs.
- Use feature branches and PRs into dev; never push directly to main or dev.
- The students authorized automated cross-account review and merging after validation on 26 November 2026. Disclose that these are AI-assisted reviews, not completed human reviews. Never claim manual question authorship, synthetic review, screenshots or demo attendance without evidence.
- Run ruff, API/indexer tests and mypy, and eval/ragops/scripts tests as applicable. Keep real-cluster and offline-fixture evidence distinct.
- AI-generated questions remain synthetic. Missing human requirements stay FILL under NEEDS HUMAN.
