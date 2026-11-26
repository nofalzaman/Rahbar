"""Real filesystem, fake vector store: unchanged, replacement, deletion and quarantine."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline import ragops
from pipeline.config import IndexerSettings


class Collection:
    metadata: dict[str, Any] = {'embed_model': 'fake'}

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def upsert(self, **fields: Any) -> None:
        for i, chunk_id in enumerate(fields['ids']):
            self.rows[chunk_id] = {k: v[i] for k, v in fields.items()}

    def get(self, include: Any = None, where: Any = None) -> dict[str, Any]:
        return {'ids': [k for k, v in self.rows.items() if not where or
                        all(v['metadatas'][key] == value for key, value in where.items())]}

    def delete(self, ids: Any = None, where: Any = None) -> None:
        for key in ids if ids is not None else self.get(where=where)['ids']:
            self.rows.pop(key, None)

    def modify(self, metadata: Any) -> None:
        assert 'hnsw:space' not in metadata
        self.metadata = metadata

    def count(self) -> int:
        return len(self.rows)


class Client:
    def __init__(self) -> None:
        self.collection = Collection()

    def get_or_create_collection(self, *args: Any, **kwargs: Any) -> Collection:
        return self.collection


def test_incremental_replace_delete_and_quarantine(tmp_path: Path, monkeypatch: Any) -> None:
    corpus, lake = tmp_path/'input', tmp_path/'lake'
    corpus.mkdir()
    def manifest(entries: list[dict[str, Any]]) -> None:
        (corpus/'_index.json').write_text(json.dumps(entries))
    entry = {'file': 'test.md', 'title': 'Test', 'doc_version': '2026', 'page_count': 1}
    (corpus/'test.md').write_text('# Test\nStudents must register before the end of the semester.')
    manifest([entry])
    calls = []
    def embedding(texts: list[str], settings: Any) -> list[list[float]]:
        calls.extend(texts)
        return [[1.0, 0.0] for t in texts]
    monkeypatch.setattr(ragops, 'embed', embedding)
    settings = IndexerSettings('fake', 'chroma', 8000, 'test', str(corpus), 100, 10, '')
    client = Client()
    first = ragops.ingest(settings, lake, client)
    assert first['chunks_embedded'] > 0
    calls.clear()
    second = ragops.ingest(settings, lake, client)
    assert second['chunks_embedded'] == second['verification_embeddings'] == 0
    assert calls == []
    (corpus/'test.md').write_text('# Revised\nStudents must now register at least two weeks before semester end.')
    third = ragops.ingest(settings, lake, client)
    assert third['chunks_embedded'] > 0
    assert len(list((lake/'archive/test.md').glob('*.json'))) == 2
    manifest([])
    deleted = ragops.ingest(settings, lake, client)
    assert deleted['count_by_document']['test.md'] == 0
    assert client.collection.count() == 0
    manifest([{**entry, 'title': ''}])
    rejected = ragops.ingest(settings, lake, client)
    assert not rejected['documents'][0]['checks']['completeness']['pass']
    assert list((lake/'quarantine').rglob('test.md'))


def test_cosine_and_malicious_manifest(tmp_path: Path) -> None:
    import pytest
    assert ragops.cosine([1, 0], [0, 1]) == 0
    (tmp_path/'_index.json').write_text('[{"file":"../escape.md"}]')
    settings = IndexerSettings('fake', '', 8000, 'test', str(tmp_path), 100, 10, '')
    with pytest.raises(ValueError, match='direct child'):
        ragops.ingest(settings, tmp_path/'lake', Client())
