"""Per-query trace state shared across the request's async/thread boundaries."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prometheus_client import Counter, Histogram

current: ContextVar[dict[str, Any] | None] = ContextVar('ragops_trace', default=None)
INJECTIONS = Counter('rahbar_injection_attempts_total', 'Flagged retrieved instruction attempts')
TOP1 = Histogram('rahbar_top1_similarity', 'Top retrieval similarity', buckets=(0, .2, .4, .6, .8, .9, 1))
STAGES = Histogram('rahbar_stage_seconds', 'Trace stage latency', ['stage'])
_lock = threading.Lock()
_instruction = re.compile(r'ignore (?:all |any )?(?:previous |prior |your )?instructions|'
                          r'reveal (?:the |your )?system prompt|attendance is optional', re.I)


def update(**fields: Any) -> None:
    record = current.get()
    if record is not None:
        record.update(fields)


def stage(name: str, started: float) -> None:
    elapsed = time.perf_counter()-started
    record = current.get()
    if record is not None:
        record['latency_ms'][name] = record['latency_ms'].get(name, 0)+elapsed*1000
    STAGES.labels(name).observe(elapsed)


def flag(text: str, target: str) -> bool:
    if not _instruction.search(text):
        return False
    record = current.get()
    if record is not None:
        record['guardrail_actions'].append({'action': 'exclude_retrieved_instruction', 'target': target})
    INJECTIONS.inc()
    return True


def attempt(messages: list[dict[str, str]], model: str, parameters: dict[str, Any]) -> None:
    record = current.get()
    if record is not None:
        record['generation_attempts'].append({'messages': messages, 'model': model, 'parameters': parameters})
        record['prompt_hash'] = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()


def trace_path(trace_id: str) -> Path:
    return Path(os.environ.get('TRACE_DIR', '/tmp/rahbar-traces')) / (hashlib.sha256(trace_id.encode()).hexdigest()+'.json')


def read_trace(trace_id: str) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(trace_path(trace_id).read_text(encoding='utf-8'))
    if value['trace_id'] != trace_id:
        raise FileNotFoundError(trace_id)
    return value


def begin(trace_id: str) -> dict[str, Any]:
    return {'event': 'ragops_trace', 'schema_version': 1, 'trace_id': trace_id,
            'timestamp': datetime.now(timezone.utc).isoformat(), 'user_query': '',
            'rewritten_query': None, 'retrieved': [], 'context': [], 'filters': {},
            'reranked_order': [], 'generation_attempts': [], 'prompt_hash': None,
            'guardrail_actions': [], 'latency_ms': {}, 'cache': 'miss'}


def emit(record: dict[str, Any]) -> None:
    destination = trace_path(record['trace_id'])
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(record, ensure_ascii=True)
    with _lock:
        destination.write_text(text, encoding='utf-8')
        with (destination.parent / (os.environ.get('HOSTNAME', 'local')+'.jsonl')).open('a', encoding='utf-8') as stream:
            stream.write(text+'\n')
        print(text, flush=True)
