"""Summarize observed kubectl-top samples, not unobserved instantaneous peaks."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    result: dict[str, dict[str, float | int]] = {}
    for path in Path('docs/evidence/ragops').glob('resources-*.txt'):
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            fields = line.split()
            if len(fields) != 3 or not fields[1].endswith('m') or not fields[2].endswith('Mi'):
                continue
            name, cpu, memory = fields
            group = next((g for g in ('api', 'chroma', 'redis', 'ui', 'data-shell')
                          if name.startswith(g+'-')), None)
            if group is None:
                group = 'evaluation' if name.startswith(('ragops-eval-', 'ragops-coverage-', 'ragops-gate-')) else 'ingestion'
            row = result.setdefault(group, {'samples': 0, 'max_observed_cpu_m': 0, 'max_observed_memory_mi': 0})
            row['samples'] += 1
            row['max_observed_cpu_m'] = max(row['max_observed_cpu_m'], int(cpu[:-1]))
            row['max_observed_memory_mi'] = max(row['max_observed_memory_mi'], int(memory[:-2]))
    Path('eval/results/resource-summary.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
