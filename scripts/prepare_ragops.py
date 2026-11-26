"""Prepare manifest metadata from downloaded sources, retaining original bytes."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from pypdf import PdfReader


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--raw', type=Path, default=Path('corpus/raw'))
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    entries = json.loads((args.raw/'_index.json').read_text())
    for entry in entries:
        source = args.raw/entry['file']
        shutil.copy2(source, args.output/source.name)
        entry['title'] = entry['name']
        entry['page_count'] = len(PdfReader(source).pages) if source.suffix == '.pdf' else 1
        entry['family'] = 'academic-rules' if entry['file'].startswith(('undergraduate-academic', 'academic-rules-handbook')) else entry['file']
        entry['min_chars'] = 100
    (args.output/'_index.json').write_text(json.dumps(entries, indent=2))
    print(json.dumps({'prepared': len(entries), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
