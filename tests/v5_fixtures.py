"""Explicit business declarations for the arithmetic fixture's complete public journey."""
import copy


def coverage(level='journey'):
    return {'level': level, 'entrypoints': ['app.add'], 'environment': 'isolated-test',
            'substitutes': [], 'isolation': 'isolated', 'isolation_evidence': []}


def plan(value):
    value['schema_version'] = 5
    value.setdefault('issues', [])
    acceptance = [r for r in value['sections'] if r['type'] == 'acceptance']
    global_data = next(r['data'] for r in value['sections'] if r['id'] == 'scope-global')
    global_data.setdefault('requirement_acceptance', [r['id'] for r in acceptance])
    global_data.setdefault('impact', [{'repository': 'self', 'entrypoint': 'app.add',
        'operations': ['calculate'], 'producer': 'caller', 'consumer': 'caller',
        'commit_owner': 'arithmetic function', 'acceptance': [r['id'] for r in acceptance]}])
    for row in acceptance:
        row['data'].setdefault('scenario', {'actor': 'caller', 'initial_state': 'Fresh process',
            'steps': ['Call the public function with 1 and 2'], 'expected': row['body'],
            'negative_cases': ['Incorrect sums are rejected by the assertion']})
        row['data'].setdefault('verification', {'method': 'automatic', 'coverage': coverage(), 'cases': []})
    return value


def observation(ref, check='unit', cases=()):
    return {'kind': 'execution', 'run': copy.deepcopy(ref), 'check': check, 'cases': list(cases)}
