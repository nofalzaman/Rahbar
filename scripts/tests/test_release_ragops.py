"""A failing gate must never invoke kubectl, including malformed result values."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import release_ragops


def test_rejected_candidate_never_rolls_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = tmp_path/'baseline.json'
    candidate = tmp_path/'candidate.json'
    thresholds = tmp_path/'thresholds.json'
    baseline.write_text(json.dumps({'run1': {'metrics': {'recall@5': .9}}}))
    candidate.write_text(json.dumps({'run1': {'metrics': {'recall@5': .1}}}))
    thresholds.write_text(json.dumps({'recall@5': {'max_drop': .02}}))
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('rejected candidate attempted kubectl')
    monkeypatch.setattr(release_ragops.subprocess, 'run', forbidden)
    monkeypatch.setattr(sys, 'argv', ['release', '--baseline', str(baseline), '--candidate', str(candidate),
        '--thresholds', str(thresholds), '--collection', 'candidate'])
    with pytest.raises(SystemExit) as exc:
        release_ragops.main()
    assert exc.value.code == 1
