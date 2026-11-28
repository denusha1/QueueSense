# QueueSense Choreo internship contribution report

**Portfolio project status · 28 November 2026**

QueueSense is a working synthetic clinic application. The Choreo work consists of designing, implementing, and locally verifying a narrowly scoped API integration and preparing its hosted rollout. This report distinguishes implementation evidence from platform activity so a reviewer can reproduce the former and assess the remaining work.

## Choreo products and actual activity

| Product or capability | Activity and status |
| --- | --- |
| WSO2 Developer Platform / Choreo Console | The project consulted the official Service, API Proxy, OAuth, quota, lifecycle and monitoring documentation. During an earlier Console attempt, organization creation was restricted. The later CLI check reported no active session in either supported region. |
| Choreo CLI | Checked the release archive and deployment command flags locally. The repository contains an optional manual GitHub Actions workflow for deploying an existing build to Development after access and configuration are approved. |
| Choreo Service | Prepared the Docker image, private service topology, health probes, and Console instructions. FastAPI ran in local containers against restricted PostgreSQL. A hosted Service deployment remains pending. |
| Choreo API Gateway and API Proxy | Prepared the contract, Git-backed component metadata, secure Target mapping, OAuth and quota plan. Implemented the Nginx mTLS ingress and FastAPI verification of the signed proxy context and department. The origin was tested using a synthetic HTTPS JWKS server and assertion. |
| Choreo Developer Portal | Prepared API documentation, Postman collection and publisher/subscriber instructions. A listing, subscription, live client credentials and portal invocation remain pending. |
| Choreo Insights and observability | Documented the supported views and configuration for managed traffic. Request logs, health probes and private Prometheus metrics were tested locally. Hosted dashboards and alert delivery remain pending. |

**Deployment and publication record:** Next.js, FastAPI and PostgreSQL ran locally, including disposable Docker staging. The partner HTTPS origin also ran locally. The only planned Choreo resource is `GET /wait-time-summary`. Hosted API publication and production promotion have yet to occur. The repository provides engineering evidence for this project. It establishes no upstream Choreo contribution, contribution points, certification, or internship affiliation.

## Engineering work and reviewable evidence

| Work | Evidence |
| --- | --- |
| Narrowed the external API to a weekly wait summary with small-cohort suppression and a department grant. | [OpenAPI](../api-management/openapi.yaml) · [Proxy component metadata](../api-management/.choreo/component.yaml) · [Partner route](../backend/api/choreo.py) · [Gateway design](../api-management/gateway-design.md) |
| Bound the integration to a trusted upstream certificate and signed assertion. | [Nginx config](../api-management/integration-ingress.conf) · [Assertion validation](../backend/core/choreo.py) · [Local gateway smoke](../scripts/smoke_gateway_tls.py) |
| Implemented application-side budgets and separated clinic credentials from partner credentials. | [Traffic policy](TRAFFIC_MANAGEMENT.md) · [JWT guide](JWT_AUTHENTICATION.md) · [Traffic tests](../backend/tests/test_traffic.py) |
| Prepared reproducible rollout and API consumption. | [Portal guide](DEVELOPER_PORTAL_GUIDE.md) · [Postman](../api-management/queuesense.postman_collection.json) · [Release checklist](DEPLOYMENT_CHECKLIST.md) |
| Verified the application under ordinary and failure conditions. | [Testing report](TESTING_REPORT.md) · [End-to-end results](END_TO_END_TEST_REPORT.md) · [Performance comparison](PERFORMANCE_REPORT.md) |

The local origin test included absent and invalid assertions, successful signed access, HTTPS client certificate enforcement, route/method restrictions, 429 and Retry-After propagation, and upstream outage recovery. Browser tests exercised clinic registration and token issuance through Next.js, distinct staff roles and private patient tracking. This evidence supports the application and origin behavior. A managed gateway test must additionally verify OAuth admission, subscription policy, signed claim values and the live gateway's response.

## Outstanding rollout

1. Obtain access to an approved Choreo organization and target project.
2. Deploy the private Service and dedicated HTTPS origin against disposable staging data.
3. Create the API Proxy and verify its versioned HTTPS route, OAuth, assertion claims, TLS trust, scope and actual traffic policies.
4. With owner approval, verify the Developer Portal listing, subscription plan and one approved application invocation.
5. Review operational dashboards, alert routing, and rollback and release evidence before any production promotion.

[Production deployment](PRODUCTION_DEPLOYMENT.md) · [Official API Proxy workflow](https://wso2.com/engineering-platform/developer-platform/docs/develop-components/develop-proxy/develop-an-api-proxy-from-an-open-api-specification/) · [Official consumer workflow](https://wso2.com/engineering-platform/developer-platform/docs/tutorials/consume-an-api-hosted-in-choreo/)
