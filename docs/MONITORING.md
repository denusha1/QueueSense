# QueueSense monitoring

The application exposes a private Prometheus scrape and emits correlated JSON request and error events to its runtime log stream. Choreo has separate views for component health and API gateway traffic. A gateway rejection can appear only in its own analytics, since FastAPI never received the request.

## Application signals

| Signal | Source |
| --- | --- |
| Requests, successes, failures | `queuesense_http_requests_total` with method, route template and HTTP status. Select 2xx for successes or 4xx and 5xx for failures. |
| Mean response time | Divide the five-minute sum rate of `queuesense_http_request_duration_seconds_sum` by the sum rate of `queuesense_http_request_duration_seconds_count`. |
| P95 response time | `histogram_quantile(0.95, sum by (le) (rate(queuesense_http_request_duration_seconds_bucket[5m])))`. Add `route` to the grouping for per-route panels. |
| Client errors, server errors and throttling | Filter the request counter on `status=~"4.."`, `status=~"5.."` or `status="429"`. Track 429 separately so intentional protection is visible. |
| Readiness | Probe private `GET /health`. HTTP 200 means the API runtime account can perform its PostgreSQL readiness query. Database unavailability returns a sanitized 503 with a correlation ID. |
| Liveness | Probe private `GET /health/live`. This checks the process independently of PostgreSQL. |
| Scrape availability | Prometheus `up{job="queuesense-api"}`. An unavailable scrape may also mean a scraper credential or network issue. Cross-check the liveness probe. |

Latency measures time to response headers. For live SSE connections, it measures establishment time. Aggregate counter rates and histogram buckets across individual replica targets. The configuration expects **one Uvicorn worker per container**. Linux process metrics are available from the Prometheus process collector.

Set `METRICS_BEARER_TOKEN` to at least 32 random characters in the private API runtime. Set the same value in a read-only secret file on the scraper host. With the variable unset, the scrape route is absent. Scrape `/internal/metrics` with `Authorization: Bearer …` over the private network or private TLS. [Prometheus scrape configuration](../monitoring/prometheus.yml) · [Prometheus authorization configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)

The example uses Compose's `api:8001` service address and expects the secret at `/run/secrets/queuesense_metrics_token`. Attach a self-managed scraper to that network, or substitute one private target per replica. Mount the configuration and [alert rules](../monitoring/alerts.yml) together and connect an approved Alertmanager receiver if notifications are required. The checked-in thresholds are staging starting points. Tune them once there is a representative baseline. Compare application, gateway and database signals before diagnosing an incident.

## Choreo Console setup

1. On the FastAPI **Service**, open **DevOps → Health Checks → Create**. Use HTTP port 8001 and `/health/live` for liveness. Use `/health` for readiness. Select an appropriate startup allowance for model warmup, then verify that an unhealthy disposable replica stops receiving traffic. [Official health checks](https://wso2.com/engineering-platform/developer-platform/docs/devops-and-ci-cd/set-up-health-checks/)
2. Use the Service's **Observability** dashboard for throughput, latency, diagnostics and runtime logs. Select Development and the deployed component. Use the correlation ID in a QueueSense JSON event to investigate a request. [Official observability dashboard](https://wso2.com/engineering-platform/developer-platform/docs/monitoring-and-insights/observability-overview/)
3. Open **Insights → Usage** and select the QueueSense API Proxy, environment, and time range. Verify Traffic, Errors and Latency with a synthetic subscribed client. Compare the gateway's count against origin traffic and check 429 responses independently. [Official API Insights](https://wso2.com/engineering-platform/developer-platform/docs/monitoring-and-insights/insights-overview/)
4. In the component's **Alerts**, create Development latency, status-code and availability-oriented rules using the options offered for the component. Use the track for the Service or the version for the Proxy. Add approved recipients and exercise an alert against a disposable origin. [Official alert setup](https://wso2.com/engineering-platform/developer-platform/docs/monitoring-and-insights/alerts-overview/)

The scrape configuration and all five alert rules passed local validation with Prometheus 3.10.0 `promtool`. The local fault smoke also verified authenticated scraping, a database readiness failure and recovery, and request correlation through Next.js. Hosted dashboards, alert delivery and actual gateway telemetry require organization access. [Staging evidence](END_TO_END_TEST_REPORT.md)
