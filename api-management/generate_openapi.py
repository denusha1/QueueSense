"""Export the private analytics operation for Choreo import review."""

import argparse
from copy import deepcopy
from pathlib import Path

import yaml

from backend.app import create_app
from backend.core.config import Settings

BASE = '/api/v1/analytics'
PATH = '/waiting-time'
SCHEMA_PREFIX = '#/components/schemas/'
STAFF_BEARER = 'QueueSenseAccessJWT'
OUTPUT = Path(__file__).with_name('openapi.yaml')


def openapi_30(value):
    """Translate the nullable scalars and constants in this contract's schemas."""
    if isinstance(value, list):
        return [openapi_30(item) for item in value]
    if not isinstance(value, dict):
        return value

    out = {}
    for key, item in value.items():
        if key == 'const':
            out['enum'] = [item]
        elif key == 'anyOf' and len(item) == 2 and {'type': 'null'} in item:
            non_null = next(option for option in item if option != {'type': 'null'})
            if non_null.get('type') not in ('string', 'integer', 'number', 'boolean'):
                raise ValueError('Review new nullable schema before exporting to OpenAPI 3.0')
            out.update(openapi_30(non_null), nullable=True)
        else:
            out[key] = openapi_30(item)
    return out


def schema_references(node):
    if isinstance(node, dict):
        ref = node.get('$ref')
        if ref is not None:
            if not ref.startswith(SCHEMA_PREFIX):
                raise ValueError(f'Unhandled OpenAPI reference {ref}')
            yield ref.removeprefix(SCHEMA_PREFIX)
        for value in node.values():
            yield from schema_references(value)
    elif isinstance(node, list):
        for item in node:
            yield from schema_references(item)


def build_contract():
    native = create_app(Settings('unused', (), automation_enabled=False)).openapi()
    operation = deepcopy(native['paths'][BASE + PATH]['get'])
    if {STAFF_BEARER: []} not in operation['security']:
        raise ValueError('Review the waiting-time authentication change before export')
    operation['operationId'] = 'getWaitingTimeSummary'
    operation['summary'] = 'Get aggregate waiting-time statistics'
    operation['description'] = (
        'This private preview requires an Admin or Manager staff access JWT. Start and end '
        'are inclusive clinic dates, at most 366 days apart. Hours use department-local time '
        'and weekday uses ISO 1–7. Waiting times are minutes. When there are no measured waits, '
        'the count is zero and the statistics are null.'
    )
    operation['security'] = [{STAFF_BEARER: []}]
    for parameter in operation['parameters']:
        schema = parameter['schema']
        branches = schema.get('anyOf', [])
        if len(branches) == 2 and {'type': 'null'} in branches:
            # Omit optional query parameters. HTTP query strings have no JSON null value.
            schema.pop('anyOf')
            schema.update(next(branch for branch in branches if branch != {'type': 'null'}))
    operation['responses']['200']['headers'] = deepcopy(
        operation['responses']['401']['headers']
    )
    operation['responses']['401']['headers']['WWW-Authenticate'] = {
        'schema': {'type': 'string'}, 'example': 'Bearer'
    }
    operation['responses']['200']['content']['application/json']['example'] = {
        'data': {'measured_waits': 42, 'average_wait': 14.2, 'median_wait': 12, 'p90_wait': 25}
    }

    schemas = {}
    pending = set(schema_references(operation))
    while pending:
        name = min(pending)
        pending.remove(name)
        schema = native['components']['schemas'][name]
        schemas[name] = schema
        pending.update(set(schema_references(schema)) - schemas.keys())

    return openapi_30({
        'openapi': '3.0.3',
        'info': {
            'title': 'QueueSense Waiting Time — Private Preview',
            'version': '1.0.0',
            'description': (
                'Curated contract for import review and synthetic origin testing. '
                'Partner OAuth and gateway-to-origin authorization are pending. '
                'Keep this preview out of the Developer Portal.'
            ),
        },
        'servers': [{'url': BASE, 'description': 'Relative private FastAPI origin base path'}],
        'paths': {PATH: {'get': operation}},
        'components': {
            'securitySchemes': {STAFF_BEARER: native['components']['securitySchemes'][STAFF_BEARER]},
            'schemas': {name: schemas[name] for name in sorted(schemas)},
        },
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='check the committed YAML for drift')
    args = parser.parse_args()
    rendered = yaml.safe_dump(build_contract(), sort_keys=False, allow_unicode=True)
    if args.check:
        if OUTPUT.read_text(encoding='utf-8') != rendered:
            raise SystemExit('The contract has drifted. Review and regenerate the OpenAPI YAML.')
    else:
        OUTPUT.write_text(rendered, encoding='utf-8')


if __name__ == '__main__':
    main()
