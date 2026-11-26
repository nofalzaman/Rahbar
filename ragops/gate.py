"""Apply file/ConfigMap thresholds without rebuilding an image."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def evaluate(baseline: dict[str, Any], candidate: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    b, c = baseline['run1']['metrics'], candidate['run1']['metrics']
    tests = {}
    def number(value: Any) -> bool:
        return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)
    for metric, rule in thresholds.items():
        value, before = c.get(metric), b.get(metric)
        ok = number(value)
        if 'min' in rule:
            ok = ok and value >= rule['min']
        if 'max' in rule:
            ok = ok and value <= rule['max']
        if 'max_drop' in rule:
            ok = ok and number(before) and value >= before-rule['max_drop']
        tests[metric] = {'pass': bool(ok), 'candidate': value, 'baseline': before, 'rule': rule}
    return {'pass': bool(tests) and all(t['pass'] for t in tests.values()), 'checks': tests}


def main() -> None:
    p = argparse.ArgumentParser()
    for key in ('baseline', 'candidate', 'thresholds'):
        p.add_argument('--'+key, type=Path, required=True)
    args = p.parse_args()
    result = evaluate(*(json.loads(getattr(args, k).read_text()) for k in
                        ('baseline', 'candidate', 'thresholds')))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['pass'] else 1)


if __name__ == '__main__':
    main()
