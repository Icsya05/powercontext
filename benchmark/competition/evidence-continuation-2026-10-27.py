"""Independent constructed evidence intervals; not SciFact or official grading."""
from collections import Counter
import json
from pathlib import Path
import re
import statistics
import sys
import time

mirror = Path(sys.argv[1])
sys.path.insert(0, str(mirror / 'src'))
from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory import MemoryHit
from powercontext.builtin.runtime import PrepareContextRequest
from powercontext.builtin.runtime import prepared_context as module

native = module._extend_evidence_continuations
builder = module.PreparedContextBuilder()
triples = [('copper', 'pressure', 'flux'), ('neuron', 'signal', 'timing'),
           ('router', 'packet', 'latency'), ('protein', 'channel', 'calcium'),
           ('battery', 'thermal', 'voltage'), ('photon', 'laser', 'frequency'),
           ('enzyme', 'binding', 'substrate'), ('water', 'filter', 'turbidity')]
continuations = [
    ('These measurements remained stable across every repeated trial.', True, ' '),
    ('This response persisted after the apparatus was recalibrated.', True, '\n'),
    ('Therefore the observed effect cannot be explained by random drift.', True, ' '),
    ('It remained reproducible despite independent changes in ambient temperature.', True, ' '),
    ('These observations include "重复" measurements 🌊 with unchanged values.', True, '\n'),
    ('Warehouse inventory follows an unrelated reporting schedule.', False, ' '),
]

def tokens(value):
    return Counter(re.findall(r'[a-z]+|\d+', value.lower()))

def address_key(fragment):
    address = fragment.address
    return (address.memory.scope_id, address.memory.artifact.model_dump_json(), address.entry_id, address.entry_version_id)

def intervals_preserved(before, after):
    for fragment in before.fragments:
        candidates = sorted((item.start, item.end) for item in after.fragments if address_key(item) == address_key(fragment))
        end = fragment.start
        for left, right in candidates:
            if left <= end:
                end = max(end, right)
        assert end >= fragment.end, (fragment, after.fragments)

rows = []
times = {'before': [], 'after': []}
for index, words in enumerate(triples):
    for continuation, relevant, separator in continuations:
        first = f'The {words[0]} {words[1]} {words[2]} observations establish a reproducible effect.'
        prefix = 'Routine apparatus records are archived. '
        text = prefix + first + separator + continuation + ' Inventory procedures remain independent.'
        gold = first + separator + continuation if relevant else first
        gold_end = len(prefix) + len(gold)
        reference = ArtifactRef(family='memory', artifact_id=f'development-{index}', revision=7)
        groups = []
        for scope, entry, body in [('local', 'evidence', text),
                                   ('shared', 'distractor-one', f'The {words[0]} protocol follows routine warehouse administration.'),
                                   ('local', 'distractor-two', f'Independent {words[1]} bookkeeping uses a separate maintenance schedule.')]:
            hit = MemoryHit(memory_ref=reference, entry_id=entry, entry_version_id='original', text=body,
                            score=1.0, matched_by=('fts',))
            groups.append(module.PreparedMemoryCandidates(scope_id=scope, memory_ref=reference, hits=(hit,)))
        for budget in (1400, 1800):
            outputs = {}
            for label, extender in [('before', lambda selected, sources, max_bytes: selected), ('after', native)]:
                module._extend_evidence_continuations = extender
                start = time.perf_counter()
                result = builder.build_scopes_result(request=PrepareContextRequest(query=' '.join(words), max_bytes=budget,
                    evidence_selection=True), current_scope_id='local', memory_candidates=tuple(groups))
                times[label].append((time.perf_counter() - start) * 1000)
                assert result.context.content_bytes == len((result.context.content or '').encode('utf-8')) <= budget
                assert tuple(fragment.address for fragment in result.fragments) == result.origins
                fragments = [fragment for fragment in result.fragments if fragment.address.entry_id == 'evidence']
                for fragment in fragments:
                    assert fragment.text == text[fragment.start:fragment.end]
                selected = tokens(' '.join(fragment.text for fragment in fragments))
                recall = sum((selected & tokens(gold)).values()) / sum(tokens(gold).values())
                covered_to = len(prefix)
                for fragment in sorted(fragments, key=lambda item: item.start):
                    if fragment.start <= covered_to or not text[covered_to:fragment.start].strip():
                        covered_to = max(covered_to, fragment.end)
                outputs[label] = {'recall': recall, 'complete': covered_to >= gold_end, 'bytes': result.context.content_bytes}
                outputs[label + '_result'] = result
            intervals_preserved(outputs['before_result'], outputs['after_result'])
            assert outputs['after']['recall'] >= outputs['before']['recall']
            assert outputs['after']['complete'] >= outputs['before']['complete']
            rows.append({'budget': budget, 'anaphoric': relevant, 'before': outputs['before'], 'after': outputs['after']})

module._extend_evidence_continuations = native
report = {'dataset': '96 independently constructed requests; 3 entries per request, no official corpus or labels',
          'limitation': 'Deliberately tests anaphoric continuation behavior; not representative hidden quality or a platform score.',
          'requests': len(rows), 'all_original_intervals_preserved': True,
          'summary': {label: {'mean_evidence_token_recall': statistics.mean(row[label]['recall'] for row in rows),
              'complete_requests': sum(row[label]['complete'] for row in rows),
              'p50_ms': statistics.median(times[label]), 'p95_ms': sorted(times[label])[int(len(rows)*.95)-1]}
              for label in ('before', 'after')}, 'cases': rows}
Path(__file__).with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in report.items() if key != 'cases'}, ensure_ascii=False))
