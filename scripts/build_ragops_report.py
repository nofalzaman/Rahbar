"""Build the seven-page review report only from committed run artifacts."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                               Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT/'eval/results'
OUT = ROOT/'docs/report'
STYLES = getSampleStyleSheet()
STYLES['BodyText'].fontSize = 9
STYLES['BodyText'].leading = 12
STYLES['Heading1'].fontSize = 19
STYLES['Heading2'].fontSize = 12
STYLES['Heading2'].spaceBefore = 9
story: list = []


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def run(label: str) -> dict:
    found = [read(p) for p in RESULTS.glob('*.json') if '-gate' not in p.stem
             and p.name not in ('coverage-before.json', 'coverage-after.json')]
    return max((r for r in found if isinstance(r, dict) and r.get('label') == label), key=lambda r: r['run_id'])


def text(value: str, style: str = 'BodyText') -> None:
    story.append(Paragraph(escape(value).replace('\n', '<br/>'), STYLES[style]))
    story.append(Spacer(1, 4))


def table(rows: list[list], widths: list[float] | None = None) -> None:
    if widths:
        widths = [w*493/sum(widths) for w in widths]
    cells = [[Paragraph(escape(str(c)), STYLES['BodyText']) for c in row] for row in rows]
    t = Table(cells, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e7edf2')),
                          ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                          ('LINEBELOW', (0, 0), (-1, 0), .6, colors.HexColor('#7d94a8')),
                          ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#d7dfe5')),
                          ('LEFTPADDING', (0, 0), (-1, -1), 5),
                          ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                          ('TOPPADDING', (0, 0), (-1, -1), 5),
                          ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    story.append(t)
    story.append(Spacer(1, 7))


def page(title: str) -> None:
    if story:
        story.append(PageBreak())
    text(title, 'Heading1')


def fmt(value: object) -> str:
    return f'{value:.4f}' if isinstance(value, float) else str(value)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = run('bounded-baseline')
    candidate = run('final-candidate')
    bad = run('bad-k1')
    drift = run('drift')
    before, after = [read(RESULTS/f'coverage-{s}.json') for s in ('before', 'after')]
    verification = [read(p) for p in (RESULTS/'verification').glob('*.json')]
    planted = next(r for r in verification if r['run_id'] == '20261126T134101-9f109d53')
    golden = [json.loads(s) for s in (ROOT/'eval/golden.jsonl').read_text().splitlines() if s.strip()]
    bm, cm, dm = [r['run1']['metrics'] for r in (baseline, candidate, drift)]
    resources = read(RESULTS/'resource-summary.json')
    page('RAHBAR: Assignment 03 / RAGOps')
    text('Nofal Zaman - 24I-3117 | Aoun Muhammad - 24I-3065', 'Heading2')
    text('Software Construction and Development (CS4032), Fall 2026. Review draft prepared 26 November 2026. Due date reported by the group: 27 November 2026.')
    text('We extended the existing university-document RAG service with verified incremental ingestion, three-level evaluation, versioned query traces, coverage checks and gated Kubernetes release. The controlled change reduces top-k from 5 to 3; embedding and generation settings are held constant. Every reported measurement below comes from the saved runs listed in the repository.')
    text(f'Release decision: release the bounded top-k 3 candidate. Recall@5 is {cm["recall@5"]:.2f}; answerable answer rate is {cm["answerable_answer_rate"]:.0%}, versus {bm["answerable_answer_rate"]:.0%} at baseline. The bad top-k 1 candidate is rejected for recall regression. Passing an automated gate does not establish full answer correctness.')
    text('NEEDS HUMAN', 'Heading2')
    text(f'FILL: eight genuinely group-written questions (currently {sum(q["origin"] == "human" for q in golden)}); hand-review at least eight synthetic questions; both students review code/report; capture the screenshot appendix and attend the Kubernetes demo. Generated text has not been falsely labelled human-written.')
    table([['Figure 3 stage', 'What it does / file', 'Missing or limited'],
           ['Ingest', 'indexer/pipeline/extract.py: extract pages; Job reads a manifest.', 'No streaming or external format validator.'],
           ['Verify', 'indexer/pipeline/ragops.py: four checks and per-run JSON.', 'No general semantic contradiction detector.'],
           ['Update data lake', 'indexer/pipeline/ragops.py: persistent active/archive/quarantine/state.', 'No atomic multi-document transaction.'],
           ['Update retrieval sources', 'indexer/pipeline/ragops.py: upsert and prune stale IDs.', 'Isolation requires a candidate collection.'],
           ['Offline testing', 'eval/ragops_suite.py: module, retrieval, e2e, repeat/noise.', 'Human-written/reviewed questions pending.'],
           ['Live testing', 'scripts/release_ragops.py: gated Deployment rollout and undo.', 'Demo traffic; not production A/B traffic.'],
           ['Check coverage', 'ragops/coverage.py: nearest golden and six additions.', 'Threshold not population-calibrated.']], [95, 235, 175])
    page('A / Verify and incrementally update data')
    failures = Counter(k for d in planted['documents'] for k, check in d['checks'].items() if not check['pass'])
    table([['Check', 'Failed documents', 'Observed cause'],
           ['Quality', failures['quality'], 'The planted truncated notice contains insufficient readable text.'],
           ['Completeness', failures['completeness'], 'Truncation/expected extent and a missing title.'],
           ['Recency', failures['recency'], 'New December library notice supersedes the November notice.'],
           ['Uniqueness', failures['uniqueness'], 'Two exact copies and one embedding near-copy.']], [95, 100, 310])
    text('Batch B contributes 12 new synthetic documents, not official university rules. The verification run also includes the existing old library notice, so the report has 13 rows. Seven accepted new notices are indexed. The injected notice passes these four data-quality checks; the retrieval rail, not this verifier, is responsible for excluding its instructions.')
    rows = [['Experiment', 'Chunks embedded', 'Evidence']]
    names = [('First real corpus', 'ingest-first.txt'), ('Real corpus unchanged', 'ingest-unchanged.txt'),
             ('Batch B', 'demo-b.txt'), ('Batch B unchanged', 'demo-unchanged.txt'),
             ('One changed document', 'demo-change.txt'), ('One deleted document', 'demo-delete.txt')]
    for label, filename in names:
        lines = (ROOT/'docs/evidence/ragops'/filename).read_text(encoding='utf-8-sig').splitlines()
        obj = next(json.loads(s) for s in reversed(lines) if s.startswith('{'))
        rows.append([label, obj['chunks_embedded'], filename])
    table(rows, [160, 105, 240])
    text('Counts by document show lab.md has zero chunks after deletion, while other accepted documents retain their IDs. Changing library-new.md embeds only its own one chunk. The restore Job reloads the archived library-old.md snapshot (one chunk) and removes its newer family version from the active collection. Snapshots include text, metadata and vectors; retired metadata is marked superseded.')
    text('Chunk embeddings and document-verification fingerprints are separate counters. The unchanged official corpus has 0 chunk embeddings and 1 verification fingerprint; the rejected historical file was reverified. This is reported explicitly, not hidden as a zero-total-embedding claim. Upstream raw input is retained; quarantined copies never enter Chroma.')
    text('Limits: completeness depends on expected page count/minimum extent, not a guarantee that every word is present. Near-duplicate threshold .985 catches the planted near-copy but is not a calibrated universal duplicate detector. Journalling and a single-writer lock support retries; multi-document updates are not atomic. Candidate collections isolate release experiments.')
    page('B / Three levels of measured offline testing')
    m = baseline['module']
    table([['Module metric', 'Measured baseline'], ['Paraphrase / unrelated pairs', f'{m["pair_count_each"]} / {m["pair_count_each"]}'],
           ['Mean paraphrase cosine', fmt(m['paraphrase_cosine'])], ['Mean unrelated cosine', fmt(m['unrelated_cosine'])],
           ['Cosine gap', fmt(m['gap'])], ['Embedding seconds per input chunk', fmt(m['embedding_seconds_per_chunk'])],
           ['Largest repeated-vector difference', fmt(m['determinism_max_difference'])]], [290, 215])
    rows = [['Metric', 'Baseline k=5', 'Candidate k=3', 'Bad k=1']]
    for key in ('recall@3', 'recall@5', 'mrr', 'ndcg@5', 'faithfulness_proxy', 'citation_validity',
                'abstention_correctness', 'answerable_answer_rate', 'latency_p50_seconds', 'latency_p95_seconds'):
        rows.append([key, *[fmt(r['run1']['metrics'][key]) for r in (baseline, candidate, bad)]])
    table(rows, [190, 105, 105, 105])
    text('The 25-question set contains 20 answerable questions with source/page labels and 5 unanswerable questions. Hard questions include paraphrases and older-version requests. The two historical questions deliberately expose the exclusion of archived documents. All origins currently remain synthetic; human authorship/review is unfinished.')
    text('Faithfulness method: fraction of distinct answer tokens appearing in the actual supplied context, averaged only over answered cases. It can miss negation, wrong numeric associations and incorrect reasoning. Citation validity checks that a citation really names retrieved evidence; it does not establish factual truth. No LLM judge is used, so no invented human/judge agreement is reported.')
    text('Fixed seed 42, temperature 0 and a 512-token output cap are used in both controlled runs. Each suite repeats all questions twice, then tests query typos. Both retrieval rankings and quality metrics are retained per question; the bad candidate omits only the optional repeated noise experiment, which is already measured on baseline and passing candidate.')
    page('B-C / Stability, noise and release decision')
    table([['Metric', 'Baseline run2 minus run1', 'Candidate run2 minus run1', 'Baseline typo delta'],
           *[[key, fmt(baseline['stochasticity_delta'][key]), fmt(candidate['stochasticity_delta'][key]),
              fmt(baseline['noise_delta'][key])] for key in ('recall@3', 'recall@5', 'mrr', 'ndcg@5')]], [155, 115, 120, 115])
    text(f'Baseline faithfulness-proxy repeat difference: {baseline["stochasticity_delta"]["faithfulness_proxy"]:.6f}; candidate: {candidate["stochasticity_delta"]["faithfulness_proxy"]:.6f}. Latency differs between repetitions. Fixed seeds do not establish bitwise model/runtime reproducibility; warm model/query-vector caches and scheduling can affect timing. We have not proved the cause of every output variation.')
    table([['Gate rule', 'Reason / outcome'], ['Recall@5 drop <= .02', 'Preserve retrieval against the measured baseline; k=1 drops .10 and fails.'],
           ['Text support >= .80; citation validity >= .95', 'Reject weakly supported/invalid references while acknowledging proxy limitations.'],
           ['Abstention and answerable rate do not regress', 'Do not trade fewer answers for a deceptively high support score.'],
           ['p95 <= 15 seconds', 'Headroom over measured baseline; a demo-specific budget, not a production SLO.']], [215, 290])
    text('The exploratory six-passage candidate initially passed the permissive proxy-only gate but answered 8 questions versus 10 at baseline. We added answerable answer rate, retained the exploratory evidence and rejected it. An unbounded three-passage run timed out and was aborted; it has partial logs, not fabricated aggregate results. The final controlled baseline and candidate both use bounded generation.')
    text('ConfigMap test: using the same evaluation image and stored measured candidate, a .001-second p95 maximum fails; restoring 15 seconds passes. This re-applies the gate to fixed measurements, not a claim that the suite was remeasured. Both Jobs have identical image digests, recorded in eval-image-identities.txt.')
    text('Kubernetes release: candidate has a separate Deployment, Service and collection. The failed k=1 release script exits before kubectl patches live state. The passing k=3 candidate rolls out with maxUnavailable=0. A deliberate nonexistent collection/model prevents readiness; rollout undo restores the previous pod-template values. A subsequent trace records the restored collection and actual model digests. The initial state is not silently changed by ConfigMap rollback.')
    page('D / Observability and trace-only diagnosis')
    table([['Paper Table 2 quality', 'Measure / threshold / evidence'],
           ['Adaptability', 'Changed document embeds only its own chunks; unchanged chunks=0; verification reports.'],
           ['Monitorability', 'Recall budget .02, p95 <=15s, abstention/answerable non-regression; suite and gate JSON.'],
           ['Observability', 'Top-1 scores, cache/abstention rates and stage p95; planted injection exclusions >=1; trace summaries and /metrics.'],
           ['Traceability', 'Successful-query required-field completeness=100% in saved traces; inputs, versions/digests, chunks, filters, actual context/prompt/hash, attempts, output and cache source.'],
           ['Reliability', 'Sampled memory below limits; PVC survival, exclusive writer, readiness, isolated candidate, maxUnavailable=0 and tested undo.']], [100, 405])
    text('The retrieval rail excludes text matching simple injected-instruction patterns before building the prompt. It logs the action and chunk ID. It does not claim to detect every attack. Trace JSONL goes to stdout and persistent storage. The trace command reconstructs recorded context and messages, including retries, rather than regenerating them from the current prompt template. Cache hits reference their source trace.')
    text('Trace-only root cause (five lines)', 'Heading2')
    text('1. The academic-warning question retrieves current evidence, with the highest score above .8.\n2. Its trace shows current-version filtering and relevant CGPA context; retrieval is not empty.\n3. The model replies 2.00 but cites section 5.4 instead of the section label attached to the retrieved chunk.\n4. Both recorded attempts fail citation validation with UngroundedAnswer.\n5. The service returns the safe fallback: the immediate cause is citation-label mismatch, not an unavailable index.')
    text('This diagnosis uses only the trace record and its actual inputs/attempts. The raw answer could be numerically correct while still violating the citation contract. High module cosine scores therefore coexist with end-to-end failure. See root-cause-trace-only.txt and the full baseline trace sample.')
    text('Trace inspection is an unauthenticated local-demo endpoint. Traces contain user questions and document excerpts; keep the demo local. The metrics script counts injection exclusions separately from generation retries, so retry events are not misreported as attacks.')
    page('E-F / Coverage, drift and Kubernetes operations')
    table([['Coverage experiment', 'Measured share', 'Gate'], ['Before six additions', f'{before["coverage"]:.1%}', before['pass']],
           ['After six additions', f'{after["coverage"]:.1%}', after['pass']]], [255, 125, 125])
    text('The same 40 live-style queries contain 28 university queries and 12 transport/housing/food queries. Similarity >= .85 defines a covered query; the minimum covered share is .85, following the paper example. This is a conservative demo choice, not a statistically calibrated threshold. The before set fails and the expanded set passes. Added questions expect abstention: test coverage improves without inventing missing domain knowledge.')
    text('The controlled comparison retains its original 25-question version in golden.initial.jsonl. The active golden.jsonl now contains all 31 cases (20 answerable and 11 unanswerable); a complete expanded-set suite is saved separately, rather than silently overwriting the earlier experiment.')
    table([['Data-drift metric', 'Before Batch B', 'After Batch B', 'Difference'],
           *[[k, fmt(cm[k]), fmt(dm[k]), fmt(dm[k]-cm[k])] for k in ('recall@3', 'recall@5', 'mrr', 'ndcg@5',
                   'abstention_correctness', 'answerable_answer_rate')]], [205, 100, 100, 100])
    text('Batch B adds seven accepted chunks; duplicates, incomplete notices and the archived historical version are excluded. The same top-k 3/API/model/generation settings are used before/after. Per-question results and trace chunk IDs explain any rank changes; the injected notice is excluded from generation when retrieved. No aggregate is substituted for an unsuccessful run.')
    table([['Component', 'Request / limit', 'Measurement evidence'],
           ['API', '100m / 500m CPU; 160Mi / 384Mi RAM', 'resources-evaluation.txt; includes headroom above measured resident usage.'],
           ['Chroma', '100m / 500m; 256Mi / 512Mi', 'Same file; separate persistent volume.'],
           ['Ingestion Job', '500m / 1 CPU; 384Mi / 1Gi', 'resources-ingestion.txt; extraction/OCR bursts require more headroom.'],
           ['Evaluation Job', '50m / 500m; 64Mi / 256Mi', 'resources-evaluation.txt; HTTP client uses host Ollama, not an in-pod model.']], [115, 195, 195])
    text('Resource evidence is sampled, not a claimed instantaneous peak. Ollama host/GPU memory is outside these pod figures. All workloads are in rahbar. The data lake, quarantine, archives, results and traces share a PVC; Chroma and Redis have dedicated PVCs. The verified ingestion CronJob is scheduled weekly; the old unverified schedule remains suspended. Fresh-cluster instructions and extra image/data commands are in k8s/README.md.')
    text('Maximum observed samples: '+ '; '.join(f'{name}: {resources[name]["max_observed_cpu_m"]}m CPU / {resources[name]["max_observed_memory_mi"]}Mi RAM' for name in ('api', 'chroma', 'ingestion', 'evaluation'))+'. See resource-summary.json for sample counts. Limits retain headroom; these samples do not prove an OOM-free peak.')
    page('G / Interpretation, contributions and limitations')
    answers = [
        ('(a) Verification', f'Uniqueness caught the most planted problems ({failures["uniqueness"]}). The injection was not caught by the four data checks; a dedicated semantic/instruction detector or human review is needed, with the tested retrieval rail providing a limited downstream defence.'),
        ('(b) Metric disagreement', 'Module cosine separation is strong while the CGPA answer falls back because its section citation is invalid. Embedding quality alone does not establish a correct, usable answer.'),
        ('(c) Archive vs delete', 'We retain versioned snapshots and source copies, then remove retired chunks from the active collection. Deleting all history would prevent the demonstrated rollback and diagnosis of past answers.'),
        ('(d) Least trusted metric', 'The lexical faithfulness proxy: word overlap can remain high for a wrong association or negation. We pair it with answerable coverage and expose actual responses; manual semantic review remains necessary.'),
        ('(e) Hardest adaptation', 'Reconciling mutable data with reproducible tests: we used per-collection journals and candidate isolation rather than claiming atomic global swaps or rebuilding every document on each run.'),
        ('(f) Object responsibilities', 'Deployment/Service serve API versions; StatefulSet/PVC persist Chroma; PVC persists lake and evidence; Job performs ingestion and is the sole vector writer; CronJob schedules it; eval Job measures/gates; ConfigMap supplies thresholds; readiness and rolling Deployment/undo control exposure. NetworkPolicy alone cannot distinguish HTTP reads from writes.')]
    for title, answer in answers:
        text(title, 'Heading2')
        text(answer)
    table([['Authorized account / area', 'AI-assisted work committed under that identity'],
           ['Aoun Muhammad / data and evaluation', 'Verification, incremental journal, Batch B, evaluation/gate/coverage/trace tools and synthetic test data; PR #17.'],
           ['Nofal Zaman / API and cluster', 'Trace instrumentation, bounded seeded generation, cache provenance, Kubernetes Jobs/storage/releases, measurements, security repair, automation and report assembly; PR #18.']], [185, 320])
    text('AI statement: Codex assisted with code, tests, synthetic data and report prose; saved measurements came from executed runs. Account attribution and automated reviews were authorized by the students. Human authorship/review and screenshots remain pending.')
    text('Reference: Xu et al., RAGOps: Operating and Managing Retrieval-Augmented Generation Pipelines, arXiv:2506.03401 (v1), sections 3.2, 4.2, 5.1 and 6.2; Tables 1-2 and Figure 3. https://arxiv.org/abs/2506.03401. Requirements crosschecked against the provided five-page CS4032 Assignment 03 PDF.')
    screenshots = sorted(p for p in (OUT/'screenshots').glob('*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg'))
    if not screenshots:
        page('Appendix / Manual screenshots pending')
        text('FILL: screenshots must be captured by the students from their own terminal/cluster, showing each command and its complete output. No terminal screenshots have been manufactured. Student-supplied images are read from docs/report/screenshots. The seven main pages remain below the eight-page limit; screenshot appendix pages do not count.')
    for path in screenshots:
        page('Appendix / '+path.stem)
        img = Image(str(path))
        scale = min(493/img.imageWidth, 680/img.imageHeight)
        img.drawWidth, img.drawHeight = img.imageWidth*scale, img.imageHeight*scale
        story.append(img)
    def footer(canvas, doc):
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#536574'))
        canvas.drawString(18*mm, 12*mm, 'RAHBAR Assignment 03 - measured review draft')
        canvas.drawRightString(192*mm, 12*mm, str(doc.page))
    path = OUT/'RAHBAR_Assignment03_Generated_Draft.pdf'
    SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                      topMargin=16*mm, bottomMargin=18*mm).build(story, onFirstPage=footer, onLaterPages=footer)
    print(path)


if __name__ == '__main__':
    main()
