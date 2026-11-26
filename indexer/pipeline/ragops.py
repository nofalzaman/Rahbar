"""Verified incremental ingestion. Only this Job writes retrieval sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import copy
import time
import uuid
from pathlib import Path
from typing import Any

from .chunk import chunk
from .clean import clean
from .config import IndexerSettings, get_settings
from .embed import embed
from .extract import extract
from .store import get_client


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x*y for x, y in zip(a, b)) / max(
        math.sqrt(sum(x*x for x in a) * sum(x*x for x in b)), 1e-15)


def ingest(settings: IndexerSettings, lake: Path, client: Any = None) -> dict[str, Any]:
    """Reconcile an authoritative manifest; journal makes interrupted writes retryable."""
    root = Path(settings.corpus_dir)
    entries = json.loads((root / '_index.json').read_text(encoding='utf-8'))
    if len({e['file'] for e in entries}) != len(entries):
        raise ValueError('manifest contains duplicate file identifiers')
    state_path = lake / 'state' / f'{settings.collection}.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    signature = [settings.embed_model, settings.embed_doc_prefix,
                 settings.chunk_size, settings.chunk_overlap]
    if state and state.get('signature') != signature:
        raise ValueError('use a separate collection for a different embedding/chunk configuration')
    client = client or get_client(settings)
    collection = client.get_or_create_collection(settings.collection, metadata={
        'hnsw:space': 'cosine', 'embed_model': settings.embed_model, 'index_id': uuid.uuid4().hex})
    old = state.get('documents', {})
    new: dict[str, Any] = {}
    reports = []
    seen: dict[str, str] = {}
    representatives: list[tuple[str, str, list[float]]] = []
    embedded = verification_embeddings = 0
    run_id = time.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    for entry in entries:
        source = entry['file']
        path = root / source
        if path.resolve().parent != root.resolve():
            raise ValueError('manifest path must be a direct child of corpus directory')
        family = str(entry.get('family', source))
        version = str(entry.get('doc_version', ''))
        newer = [e for e in entries if e.get('family', e['file']) == family
                 and str(e.get('doc_version', '')) > version]
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ''
        staged = lake / 'staging' / run_id / source
        if path.is_file():
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, staged)
        checks: dict[str, dict[str, Any]] = {}
        checks['recency'] = {'pass': not newer, 'reason':
                             'newer family version exists; archive old version' if newer else 'current version'}
        document = None
        error = ''
        previous = old.get(source, {})
        unchanged = previous.get('hash') == digest and previous.get('entry') == entry
        try:
            if unchanged:
                text = previous['text']
                pages = previous['pages']
            else:
                document = clean(extract(str(path), version, False))
                text = '\n'.join(p.text for p in document.pages)
                pages = len(document.pages)
        except Exception as exc:
            text, pages, error = '', 0, type(exc).__name__ + ': ' + str(exc)
        quality = len(text.strip()) >= 30 and text.count('\ufffd') / max(len(text), 1) < .01
        checks['quality'] = {'pass': quality, 'reason': error or ('readable extraction' if quality else 'empty/garbled text')}
        complete = all(entry.get(k) for k in ('file', 'title', 'doc_version', 'page_count'))
        complete = bool(complete and pages == entry.get('page_count')
                        and len(text) >= entry.get('min_chars', 30))
        checks['completeness'] = {'pass': complete, 'reason': 'metadata and expected extent match' if complete
                                  else 'missing metadata or extracted extent differs from expected extent'}
        fingerprint: list[float] = []
        duplicate = seen.get(digest) if digest else None
        near = None
        if quality and complete and not duplicate:
            if unchanged:
                fingerprint = previous['fingerprint']
            else:
                fingerprint = embed([text[:6000]], settings)[0]
                verification_embeddings += 1
            near = next((s for s, f, v in representatives
                         if f != family and cosine(v, fingerprint) >= .985), None)
        unique = duplicate is None and near is None
        checks['uniqueness'] = {'pass': unique, 'reason':
                                f'exact duplicate of {duplicate}' if duplicate else
                                f'near duplicate of {near} (cosine >= 0.985)' if near else 'distinct content'}
        accepted = all(c['pass'] for c in checks.values())
        reports.append({'source': source, 'accepted': accepted, 'checks': checks})
        if digest and unique and quality and complete and not newer:
            seen[digest] = source
        if fingerprint and unique and quality and complete and not newer:
            representatives.append((source, family, fingerprint))
        if not accepted:
            destination = lake / ('archive' if newer else 'quarantine') / run_id / source
            destination.parent.mkdir(parents=True, exist_ok=True)
            if staged.exists():
                shutil.move(str(staged), destination)
            continue
        if unchanged:
            row = previous
        else:
            assert document is not None
            pieces = chunk(document, settings.chunk_size, settings.chunk_overlap)
            vectors = embed([p.text for p in pieces], settings)
            embedded += len(pieces)
            row = {'hash': digest, 'entry': entry, 'text': text, 'pages': pages,
                   'fingerprint': fingerprint, 'ids': [p.id for p in pieces],
                   'documents': [p.text for p in pieces], 'embeddings': vectors,
                   'metadatas': [{**p.metadata(), 'document_id': source} for p in pieces]}
        # Upsert even cached vectors: a lost Chroma PVC can be recovered without re-embedding.
        for start in range(0, len(row['ids']), 200):
            collection.upsert(**{k: row[k][start:start+200] for k in
                                 ('ids', 'documents', 'embeddings', 'metadatas')})
        new[source] = row
        dump(lake / 'archive' / settings.collection / source / f'{digest}.json', row)
        target = lake / 'active' / settings.collection / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), target)
    wanted = {i for row in new.values() for i in row['ids']}
    actual = collection.get(include=[])['ids']
    stale = [i for i in actual if i not in wanted]
    for start in range(0, len(stale), 200):
        collection.delete(ids=stale[start:start+200])
    changed = old != new or bool(stale)
    # The curated lake mirrors accepted documents; upstream raw inputs remain immutable.
    for source, previous in old.items():
        if source not in new or previous['hash'] != new[source]['hash']:
            archived = copy.deepcopy(previous)
            for meta in archived['metadatas']:
                meta['superseded'] = True
            dump(lake / 'archive' / settings.collection / source / f'{previous["hash"]}.json', archived)
            active = lake / 'active' / settings.collection / source
            if source not in new and active.exists():
                destination = lake / 'archive' / 'raw' / run_id / source
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(active), destination)
    metadata = dict(collection.metadata or {})
    metadata.pop('hnsw:space', None)
    metadata.update(embed_model=settings.embed_model)
    if changed:
        metadata['index_id'] = uuid.uuid4().hex
    collection.modify(metadata=metadata)
    dump(state_path, {'signature': signature, 'documents': new})
    counts = {source: len(collection.get(where={'document_id': source}, include=[])['ids'])
              for source in sorted(set(old) | {e['file'] for e in entries})}
    result = {'run_id': run_id, 'collection': settings.collection, 'documents': reports,
              'chunks_embedded': embedded, 'verification_embeddings': verification_embeddings,
              'chunks_deleted': len(stale), 'count_by_document': counts, 'total_chunks': collection.count()}
    dump(lake / 'reports' / f'verification-{run_id}.json', result)
    print(json.dumps(result), flush=True)
    return result


def restore(settings: IndexerSettings, lake: Path, source: str, digest: str) -> None:
    """Restore an archived version from the ingestion Job, excluding its current family."""
    snapshot = lake / 'archive' / settings.collection / source / f'{digest}.json'
    if not snapshot.exists():
        snapshot = lake / 'archive' / source / f'{digest}.json'  # migrate the first run's journal
    row = json.loads(snapshot.read_text())
    collection = get_client(settings).get_collection(settings.collection)
    state_path = lake / 'state' / f'{settings.collection}.json'
    state = json.loads(state_path.read_text())
    family = row['entry'].get('family', source)
    for other, current in list(state['documents'].items()):
        if current['entry'].get('family', other) == family:
            collection.delete(where={'document_id': other})
            del state['documents'][other]
    for meta in row['metadatas']:
        meta['superseded'] = False
    collection.upsert(**{k: row[k] for k in ('ids', 'documents', 'embeddings', 'metadatas')})
    metadata = {k: v for k, v in collection.metadata.items() if k != 'hnsw:space'}
    collection.modify(metadata={**metadata, 'index_id': uuid.uuid4().hex})
    state['documents'][source] = row
    dump(state_path, state)
    print(json.dumps({'restored': source, 'hash': digest, 'chunks': len(row['ids'])}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--lake', type=Path, default=Path('/data/lake'))
    parser.add_argument('--restore', nargs=2, metavar=('SOURCE', 'HASH'))
    args = parser.parse_args()
    args.lake.mkdir(parents=True, exist_ok=True)
    lock = args.lake / 'ingestion.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.close(fd)
        if args.restore:
            restore(get_settings(), args.lake, *args.restore)
        else:
            ingest(get_settings(), args.lake)
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
