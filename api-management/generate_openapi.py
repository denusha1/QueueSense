"""Generate the partner publication contract and optional staff preview."""

import argparse
import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import yaml

from backend.api.errors import INTEGRATION_PREFIX
from backend.app import create_app
from backend.core.choreo import ChoreoSettings
from backend.core.config import Settings

BASE = '/api/v1/analytics'
PATH = '/waiting-time'
SCHEMA_PREFIX = '#/components/schemas/'
STAFF_BEARER = 'QueueSenseAccessJWT'
STAFF_OUTPUT = Path(__file__).with_name('staff-preview.openapi.yaml')
GATEWAY_OUTPUT = Path(__file__).with_name('openapi.yaml')
GATEWAY_PATH = '/wait-time-summary'
POSTMAN_OUTPUT = Path(__file__).with_name('queuesense.postman_collection.json')


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
            if '$ref' in non_null:
                out['anyOf'] = [
                    non_null,
                    {'type': 'object', 'nullable': True, 'enum': [None]},
                ]
                continue
            if non_null.get('type') not in ('string', 'integer', 'number', 'boolean'):
                raise ValueError(
                    'Review new nullable schema before exporting to OpenAPI 3.0'
                )
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
            schema.update(
                next(branch for branch in branches if branch != {'type': 'null'})
            )
    operation['responses']['200']['headers'] = deepcopy(
        operation['responses']['401']['headers']
    )
    operation['responses']['401']['headers']['WWW-Authenticate'] = {
        'schema': {'type': 'string'},
        'example': 'Bearer',
    }
    operation['responses']['200']['content']['application/json']['example'] = {
        'data': {
            'measured_waits': 42,
            'average_wait': 14.2,
            'median_wait': 12,
            'p90_wait': 25,
        }
    }

    return openapi_30(
        {
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
            'servers': [
                {
                    'url': BASE,
                    'description': 'Relative private FastAPI origin base path',
                }
            ],
            'paths': {PATH: {'get': operation}},
            'components': {
                'securitySchemes': {
                    STAFF_BEARER: native['components']['securitySchemes'][STAFF_BEARER]
                },
                'schemas': collect_schemas(native, operation),
            },
        }
    )


def collect_schemas(native, operation):
    schemas = {}
    pending = set(schema_references(operation))
    while pending:
        name = min(pending)
        pending.remove(name)
        schema = native['components']['schemas'][name]
        schemas[name] = schema
        pending.update(set(schema_references(schema)) - schemas.keys())

    return {name: schemas[name] for name in sorted(schemas)}


def build_gateway_contract():
    # Building OpenAPI neither connects to this example issuer nor opens a database.
    fixture = ChoreoSettings(
        'https://gateway.example.invalid/.wellknown/jwks',
        'example-issuer',
        'example-integration-audience',
        '/example/context/v1.0',
        UUID(int=0),
    )
    native = create_app(
        Settings('unused', (), automation_enabled=False, choreo=fixture)
    ).openapi()
    operation = deepcopy(native['paths'][INTEGRATION_PREFIX + GATEWAY_PATH]['get'])
    operation['operationId'] = 'getWeeklyWaitingTimeSummary'
    operation['summary'] = 'Get the weekly waiting-time summary'
    operation['tags'] = ['Waiting time']
    operation['security'] = [{'ChoreoOAuthBearer': []}]
    operation['description'] = (
        'Supply the approved department and the Monday of a completed clinic week. '
        'Dates follow Asia/Colombo clinic time. Results are in minutes. Metrics are null when fewer than ten waits were measured. '
        'Responses generated by the gateway may differ from QueueSense origin responses.'
    )
    for status, description in {
        '401': 'Valid gateway assertion required at the origin',
        '403': 'Proxy context or department is outside the approved grant',
        '503': 'Database or gateway signing keys temporarily unavailable',
    }.items():
        operation['responses'][status]['description'] = description
    operation['responses']['200']['headers'] = deepcopy(
        operation['responses']['401']['headers']
    )
    department = '5853b5a7-cfa4-4c3d-9c06-e97ce42487a1'
    week = '2026-11-02'
    for parameter in operation['parameters']:
        if parameter['name'] == 'department_id':
            parameter.update(
                description='Department UUID assigned to the approved proxy.',
                example=department,
            )
        else:
            parameter.update(
                description='Monday of a completed clinic week, formatted YYYY-MM-DD.',
                example=week,
            )

    example = {'department_id': department, 'week_start': week}
    operation['responses']['200']['content']['application/json']['examples'] = {
        'measured': {
            'value': {
                'data': {
                    **example,
                    'suppressed': False,
                    'metrics': {
                        'measured_waits': 42,
                        'average_wait': 14.2,
                        'median_wait': 12.0,
                        'p90_wait': 25.0,
                    },
                }
            }
        },
        'suppressed': {
            'value': {'data': {**example, 'suppressed': True, 'metrics': None}}
        },
    }
    limited = operation['responses']['429']
    limited['description'] = (
        'QueueSense origin limit reached. Gateway-generated 429 responses may differ.'
    )
    limited['headers']['Retry-After']['description'] = (
        'Seconds before retrying an origin-rejected request.'
    )
    limited['content']['application/json']['example'] = {
        'success': False,
        'error': {
            'code': 'rate_limited',
            'message': 'Too many requests. Wait before retrying.',
            'details': [],
        },
        'request_id': '72697aba-156f-4bf1-994d-858372a876df',
    }

    return openapi_30(
        {
            'openapi': '3.0.3',
            'info': {
                'title': 'QueueSense Weekly Waiting Time',
                'version': '1.0.0',
                'description': 'Read-only partner analytics. Requests require an approved Choreo OAuth application and a department grant bound to the signed proxy context.',
            },
            'tags': [
                {
                    'name': 'Waiting time',
                    'description': 'Aggregated weekly clinic waiting-time statistics.',
                }
            ],
            'servers': [
                {
                    'url': INTEGRATION_PREFIX,
                    'description': 'Relative integration origin base path',
                }
            ],
            'paths': {GATEWAY_PATH: {'get': operation}},
            'components': {
                'securitySchemes': {
                    'ChoreoOAuthBearer': {
                        'type': 'http',
                        'scheme': 'bearer',
                        'description': 'OAuth 2.0 access token from the configured Choreo key manager.',
                    },
                },
                'schemas': collect_schemas(native, operation),
            },
        }
    )


def build_postman(contract):
    operation = contract['paths'][GATEWAY_PATH]['get']
    query = [
        {
            'key': param['name'],
            'value': '{{' + param['name'] + '}}',
            'description': param['description'],
        }
        for param in operation['parameters']
    ]
    return {
        'info': {
            'name': contract['info']['title'],
            'description': 'Set the Choreo invocation base URL and approved department. Provide a short-lived OAuth token in a private Postman environment.',
            'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
        },
        'variable': [
            {'key': 'gateway_url', 'value': ''},
            {'key': 'access_token', 'value': ''},
            *[
                {'key': param['name'], 'value': param['example']}
                for param in operation['parameters']
            ],
        ],
        'auth': {
            'type': 'bearer',
            'bearer': [{'key': 'token', 'value': '{{access_token}}', 'type': 'string'}],
        },
        'item': [
            {
                'name': operation['summary'],
                'request': {
                    'method': 'GET',
                    'description': operation['description'],
                    'header': [{'key': 'Accept', 'value': 'application/json'}],
                    'url': {
                        'raw': '{{gateway_url}}'
                        + GATEWAY_PATH
                        + '?'
                        + '&'.join(item['key'] + '=' + item['value'] for item in query),
                        'host': ['{{gateway_url}}'],
                        'path': [GATEWAY_PATH.lstrip('/')],
                        'query': query,
                    },
                },
            }
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--check', action='store_true', help='check the committed YAML for drift'
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--gateway',
        action='store_true',
        help='export the partner proxy contract (default)',
    )
    mode.add_argument(
        '--staff-preview', action='store_true', help='export the private staff preview'
    )
    mode.add_argument(
        '--postman',
        action='store_true',
        help='derive the Postman collection from the generated gateway contract',
    )
    args = parser.parse_args()
    if args.postman:
        output = POSTMAN_OUTPUT
        rendered = json.dumps(build_postman(build_gateway_contract()), indent=2) + '\n'
    else:
        output = STAFF_OUTPUT if args.staff_preview else GATEWAY_OUTPUT
        contract = build_contract() if args.staff_preview else build_gateway_contract()
        rendered = yaml.safe_dump(contract, sort_keys=False, allow_unicode=True)
    if args.check:
        if output.read_text(encoding='utf-8') != rendered:
            raise SystemExit(
                'The contract has drifted. Review and regenerate the OpenAPI YAML.'
            )
    else:
        output.write_text(rendered, encoding='utf-8')


if __name__ == '__main__':
    main()
