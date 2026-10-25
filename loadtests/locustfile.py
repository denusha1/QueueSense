"""Synthetic public user traffic for QueueSense's health and token status API."""
import os

from locust import HttpUser, between, task


class QueueSenseVisitor(HttpUser):
    # Approximate patient-page refresh cadence while staying within the API's
    # documented per-process cap of 600 public token reads per minute.
    wait_time = between(12, 18)

    def on_start(self):
        self.patient_key = os.environ.get('QUEUESENSE_PATIENT_KEY', '')
        if not 30 <= len(self.patient_key) <= 80:
            raise RuntimeError('Set QUEUESENSE_PATIENT_KEY to a synthetic demo token key.')

    @task(1)
    def check_service_health(self):
        self.client.get('/health', name='GET /health', timeout=15)

    @task(4)
    def refresh_patient_status(self):
        self.client.get(
            f'/patient/{self.patient_key}',
            name='GET /patient/:key',
            headers={'Referer': ''},
            timeout=15,
        )
