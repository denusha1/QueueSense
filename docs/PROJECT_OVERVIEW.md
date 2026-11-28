# QueueSense Enterprise project overview

Queues change when a clinician goes on break, a patient misses a call, or arrivals concentrate in one department. QueueSense gives patients a private status view, gives staff a shared queue, and lets managers analyze what happened using the same source of truth.

| Objective | Implemented outcome |
| --- | --- |
| Make queues visible | Staff coordinate through the live queue, and a patient can follow one visit from check-in through completion. |
| Protect queue correctness | PostgreSQL transactions allocate tokens and record lifecycle events. Role and resource checks constrain staff actions. |
| Explain operational waits | Dashboards show waiting-time distributions, peak hours and workload. Staffing simulations and model monitoring support planning. |
| Prepare a consumer API | The partner contract exposes one weekly aggregate. The origin implements signed-assertion checks, department restrictions, suppression and quotas. |
| Make releases testable | Versioned migrations, Docker, CI workflows, synthetic fixtures, load reports and health probes support reproducible review. |

QueueSense targets a single clinic installation with multiple departments. The web UI serves patients, receptionists, doctors, managers and administrators. An external application can use the proposed Choreo partner API after subscription and hosted verification. It receives only aggregate waiting-time fields for the authorized department and reporting week.

## Review sequence

1. Open the local walkthrough or run the synthetic demo.
2. Issue a token as a receptionist or administrator. Open the private tracker and complete the visit from an authorized clinician station.
3. Review how the recorded wait contributes to analytics and compare it with the retained check-in estimate.
4. Inspect the partner OpenAPI operation, its HTTPS origin tests, and the handoff steps for Choreo.
5. Review measured local performance and the staging deployment checklist.

The dataset contains 15,265 synthetic visits across 90 calendar days. The model and simulator support operational exploration. Real-clinic accuracy, patient-data retention and clinical deployment require separate evaluation and approval. [Data dictionary](../data/data_dictionary.md) · [Model methodology](../ml/README.md) · [Production guide](PRODUCTION_DEPLOYMENT.md)
