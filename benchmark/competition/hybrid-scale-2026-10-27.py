"""Real seekdb, independently generated 173x384 corpus; no official qrels."""
import asyncio
import json
import math
from pathlib import Path
import random
import re
import statistics
import sys
import tempfile
import time

mirror = Path(sys.argv[1])
sys.path.insert(0, str(mirror / 'src'))
from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput, MemorySearchChannels
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.memory_index import CompositeMemoryIndex
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from sqlalchemy import Engine, event

profile = EmbeddingProfile(profile_id='independent-scale-384', model='generated-topic-vectors', dimension=384,
                           distance='l2', normalization='unit')


class Embedding:
    def __init__(self):
        self.profile = profile

    async def embed(self, texts, /):
        vectors = []
        for text in texts:
            topic = int(re.search(r'topic(\d+)', text)[1])
            document = re.search(r'document(\d+)', text)
            rng = random.Random(int(document[1]) if document else 100000 + topic)
            vector = [rng.uniform(-.015, .015) for _ in range(384)]
            vector[topic] = 1.0
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append(tuple(value / norm for value in vector))
        return EmbeddingResult(vectors=tuple(vectors))


native = CompositeMemoryIndex.search


async def separated(self, connection, scope_id, request, /):
    if request.mode != 'hybrid':
        return await native(self, connection, scope_id, request)
    fts, vector = (), ()
    for index in self.indexes:
        mode = 'fts' if index.capabilities.fts else 'vector'
        channels = await index.search(connection, scope_id, request.model_copy(update={'mode': mode}))
        fts += channels.fts
        vector += channels.vector
    return MemorySearchChannels(fts=fts, vector=vector)


def identity(result):
    return [(hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id, hit.text,
             tuple(hit.matched_by)) for hit in result.hits]


async def main():
    root = Path(tempfile.mkdtemp(prefix='hybrid-scale-', dir=str(mirror.parent)))
    rows = []
    statements = []
    def record(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)
    event.listen(Engine, 'before_cursor_execute', record)
    try:
        async with open_builtin_contexts(BuiltinConfig(database=SeekDBConfig(path=root / 'db')),
                                         embedding_model=Embedding()) as contexts:
            texts = tuple(f'topic{index % 20:02d} calibrated apparatus records a stable controlled response '
                          f'with repeat measurements document{index:04d}.' for index in range(173))
            for scope_index in range(3):
                scope = f'independent-scope-{scope_index}'
                memory = (await contexts.get(scope)).artifacts.memory
                head = await memory.remember(memory=None, entries=tuple(MemoryEntryInput(kind='fact', text=text)
                                                                       for text in texts), mode='append')
                assert head is not None
                for method in (native, separated):
                    CompositeMemoryIndex.search = method
                    await memory.search('topic00 calibrated apparatus response', memories=(head,), mode='hybrid', limit=10)
                for topic in range(20):
                    query = f'topic{topic:02d} calibrated apparatus response'
                    results, latencies, candidate_sql = {}, {}, {}
                    order = [('candidate', native), ('control', separated)]
                    if (topic + scope_index) % 2:
                        order.reverse()
                    for label, method in order:
                        CompositeMemoryIndex.search = method
                        statements.clear()
                        start = time.perf_counter()
                        results[label] = await memory.search(query, memories=(head,), mode='hybrid', limit=10)
                        latencies[label] = (time.perf_counter() - start) * 1000
                        candidate_sql[label] = sum('AGAINST' in statement.upper() or 'l2_distance' in statement.lower()
                                                   for statement in statements)
                    assert candidate_sql == {'candidate': 1, 'control': 2}, candidate_sql
                    for label, result in results.items():
                        seen = set()
                        for hit in result.hits:
                            assert hit.memory_ref == head.as_ref()
                            assert hit.text in texts and set(hit.matched_by) <= {'fts', 'vector'} and hit.matched_by
                            key = (hit.entry_id, hit.entry_version_id)
                            assert key not in seen
                            seen.add(key)
                    relevant_count = sum(index % 20 == topic for index in range(173))
                    recalls, mrrs = {}, {}
                    for label, result in results.items():
                        relevance = [f'topic{topic:02d} ' in hit.text for hit in result.hits]
                        recalls[label] = sum(relevance) / relevant_count
                        mrrs[label] = next((1 / rank for rank, value in enumerate(relevance, 1) if value), 0.0)
                    assert recalls['candidate'] >= recalls['control'], (scope, topic, recalls)
                    assert mrrs['candidate'] >= mrrs['control'], (scope, topic, mrrs)
                    CompositeMemoryIndex.search = native
                    repeated = await memory.search(query, memories=(head,), mode='hybrid', limit=10)
                    assert identity(repeated) == identity(results['candidate'])
                    rows.append({'scope': scope, 'topic': topic, 'latency_ms': latencies, 'recall': recalls, 'mrr': mrrs,
                                 'same_order': identity(results['candidate']) == identity(results['control'])})
                print(f'Completed {scope}: 173 entries and 20 paired searches', flush=True)
    finally:
        CompositeMemoryIndex.search = native
        event.remove(Engine, 'before_cursor_execute', record)
    report = {'status': 'real embedded seekdb with generated corpus and topic vectors', 'documents_per_scope': 173,
              'dimension': 384, 'scopes': 3, 'queries': 60, 'seed': 'document index and topic-derived seeds',
              'control': 'current independent fts/vector statements, shared fusion; not claimed as full frozen product',
              'limitations': 'Synthetic topic relevance, not SciFact semantic quality, not official acceptance or score.',
              'summary': {label: {'p50_ms': statistics.median(row['latency_ms'][label] for row in rows),
                                  'p95_ms': sorted(row['latency_ms'][label] for row in rows)[56],
                                  'mean_recall_at_10': statistics.mean(row['recall'][label] for row in rows),
                                  'mean_mrr_at_10': statistics.mean(row['mrr'][label] for row in rows)}
                          for label in ('candidate', 'control')},
              'same_order_queries': sum(row['same_order'] for row in rows), 'cases': rows}
    Path(__file__).with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'cases'}, ensure_ascii=False))


asyncio.run(main())
