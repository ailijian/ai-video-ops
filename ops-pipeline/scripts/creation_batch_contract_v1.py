"""Strict adapters for the approved C04-C08 vocabulary; no business grants."""
from pathlib import Path

from human_review_operations_v1 import read
from profile_compatibility_contract_v1_1 import validate

CONTRACTS = Path(__file__).with_name('creation_batch_contracts_v1.json')


class BatchError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def check(value, name):
    schema = read(CONTRACTS)[name]

    def expand(node):
        if '$ref' in node:
            prefix = '#/$defs/'
            if not node['$ref'].startswith(prefix):
                raise ValueError('External schema reference')
            return expand(schema['$defs'][node['$ref'][len(prefix):]])
        if 'anyOf' in node:
            return {'oneOf': [expand(v) for v in node['anyOf']]}
        if 'oneOf' in node:
            return {'oneOf': [expand(v) for v in node['oneOf']]}
        allowed = {'$schema', '$defs', 'type', 'properties', 'required', 'additionalProperties',
                   'items', 'minItems', 'maxItems', 'minLength', 'pattern', 'const', 'enum', 'minimum'}
        if set(node) - allowed:
            raise ValueError('Unsupported schema vocabulary')
        result = {k: v for k, v in node.items() if k not in {'$schema', '$defs'}}
        if 'properties' in result:
            result['properties'] = {k: expand(v) for k, v in result['properties'].items()}
        if 'items' in result:
            result['items'] = expand(result['items'])
        return result

    try:
        validate(value, expand(schema))
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        raise BatchError('CREATION_BATCH_SCHEMA_INVALID', f'Invalid {name} contract') from exc
    return value
