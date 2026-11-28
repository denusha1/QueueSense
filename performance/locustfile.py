"""Closed-loop synthetic patient and clinic traffic launched by run.py."""

import itertools
import json
import os
from pathlib import Path

from locust import HttpUser, between, task

fixture = json.loads(Path(os.environ['QUEUESENSE_LOAD_FIXTURE']).read_text())
users = itertools.count()
mix = ('patient', 'reception', 'patient', 'doctor', 'manager',
       'patient', 'reception', 'patient', 'doctor', 'auth')
analytics = itertools.cycle(('waiting-time', 'peak-hours', 'queue-performance'))
prefix = '/api/v1'


class ClinicUser(HttpUser):
    wait_time = between(6, 10)

    def on_start(self):
        number = next(users)
        self.role = mix[number % len(mix)]
        self.patient_key = fixture['patient_keys'][number]
        self.department = fixture['department']
        self.sequence = 0
        self.number = number
        self.client.headers['Origin'] = fixture['origin']
        if self.role != 'patient':
            self.client.cookies.set('queuesense_session', fixture['staff'][str(number)])

    def request(self, method, path, name, expected=200, **kwargs):
        with self.client.request(
            method, path, name=name, timeout=10, catch_response=True, **kwargs
        ) as result:
            if result.status_code != expected:
                result.failure(f'HTTP {result.status_code or "transport failure"}')
                return None
            result.success()
            return result.json()

    @task
    def clinic_operation(self):
        if self.role == 'patient':
            self.request('GET', f'/patient/{self.patient_key}', '/patient/{key}')
        elif self.role == 'reception':
            self.sequence += 1
            registered = self.request(
                'POST', prefix + '/patients', '/api/v1/patients', 201,
                json={'external_id': f'LOAD-{self.number}-{self.sequence}'},
            )
            if registered:
                self.request(
                    'POST', prefix + '/queue', '/api/v1/queue', 201,
                    json={'department_id': self.department, 'patient_id': registered['data']['id']},
                )
        elif self.role == 'doctor':
            self.request('GET', prefix + '/queue', '/api/v1/queue',
                         params={'department_id': self.department, 'page_size': 10})
        elif self.role == 'manager':
            endpoint = prefix + '/analytics/' + next(analytics)
            self.request('GET', endpoint, endpoint, params=fixture['analytics_range'])
        else:
            self.request('GET', '/auth/me', '/auth/me')
