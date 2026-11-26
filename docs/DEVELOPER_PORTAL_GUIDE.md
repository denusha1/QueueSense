# QueueSense Developer Portal guide

## Status and prerequisites

The publication artifacts are ready for review. The Console currently blocks organization creation for the available account, and the live Choreo gateway and Developer Portal listing remain unverified. Obtain access to an approved organization before this workflow. The owner must approve the HTTPS target, client credentials, audience, and publication. [Deployment status](../api-management/proxy-configuration.md#hosted-deployment-status)

Use the [partner OpenAPI file](../api-management/openapi.yaml), which exposes a single weekly waiting-time resource. Prepare the environment's private FastAPI service, secured HTTPS ingress, gateway assertion settings, and Development smoke test before publishing. Use the [proxy runbook](../api-management/proxy-configuration.md) and [gateway verification checklist](../api-management/gateway-testing.md).

## Publisher workflow

1. Deploy and verify the approved API Proxy. Confirm **Develop → Resources** shows only `GET /wait-time-summary`. Verify subscribed access, rejected credentials, department restrictions, retry behavior and the origin's mTLS boundary in Development. [Official managed API workflow](https://wso2.com/engineering-platform/developer-platform/docs/tutorials/expose-a-service-as-a-managed-api/)
2. In **Manage → API Info → Developer Portal**, set **Visibility** to **Restricted** for the approved publisher and consumer roles, then save. Check the organization's **Settings → API Management → Developer Portal → Environments** setting to confirm the portal exposes the intended environment. Portal visibility controls discovery. Subscription, gateway authentication and the QueueSense department grant control invocations. [Official visibility settings](https://wso2.com/engineering-platform/developer-platform/docs/api-management/control-api-visibility/) · [Official environment exposure settings](https://wso2.com/engineering-platform/developer-platform/docs/administer/configure-exposed-environments-to-developer-portal/)
3. Add a usage note in **Manage → Documents**. Include the partner operation, required parameters, synthetic examples, suppression behavior, quota guidance and version history. Source that content from the partner section of the [API documentation](API_DOCUMENTATION.md). Assign the approved subscription plan and validate it in the matching environment. [Official API documents](https://wso2.com/engineering-platform/developer-platform/docs/api-management/documents/) · [QueueSense quota proposal](../api-management/rate-limiting.md)
4. For the standard Production-visible catalog workflow, use **Deploy → Development → Promote** after approval. Verify the Production endpoint, certificate, audience and lifecycle candidate. In **Manage → Lifecycle**, select **Publish** and review the display name before **Confirm**. Open **Go to DevPortal** and verify the listing, version, documentation and invocation base as a user with the approved role. Verify an unauthorized role cannot discover the listing. [Official lifecycle](https://wso2.com/engineering-platform/developer-platform/docs/api-management/lifecycle-management/) · [Official publishing tutorial](https://wso2.com/engineering-platform/developer-platform/docs/tutorials/expose-a-service-as-a-managed-api/)

## Application developer workflow

1. Sign in to the Developer Portal. Choose **Applications → + Create**, fill in the application name and description, and select **Create**. Select the application, open **Subscriptions → + Add APIs**, choose QueueSense and select the approved usage plan. If a plan needs approval, wait for it to become active. [Official OAuth consumption workflow](https://wso2.com/engineering-platform/developer-platform/docs/tutorials/consume-an-api-hosted-in-choreo/)
2. Open the application's **Credentials** tab for the target environment and generate credentials. Store the consumer secret in the approved vault or a private client environment. Read the token endpoint displayed for the selected key manager. Use the credentials to request an OAuth access token with the `client_credentials` grant. Portal test tokens are intended for testing. [Official token and credential workflow](https://wso2.com/engineering-platform/developer-platform/docs/tutorials/consume-an-api-hosted-in-choreo/)
3. On the API overview, copy the versioned invocation base for that environment. Use the bearer token and the allocated department UUID to invoke the documented GET operation. Compare the response with the OpenAPI examples. If a quota is reached, follow the [retry rules](TRAFFIC_MANAGEMENT.md#http-429-and-retry-behavior). [Invocation example](API_DOCUMENTATION.md#partner-api)
4. Record the environment, API version, subscription approval status, test timestamp and the request ID if present. Capture the listing and one approved invocation. Keep OAuth tokens, client secrets and complete assertions out of the verification record.

## Postman

Import the [generated Postman collection](../api-management/queuesense.postman_collection.json). Set `gateway_url` to the portal's versioned invocation base with no trailing slash. Set the approved `department_id`, and enter a Monday of a completed week in `week_start`. Set `access_token` in a private environment. The collection's committed token and URL values are empty. [Official Postman OpenAPI documentation](https://learning.postman.com/docs/integrations/available-integrations/working-with-openAPI)

Regenerate or check the collection from the gateway contract using the [OpenAPI tooling setup](../api-management/choreo-integration-plan.md#repository-work-completed).

```sh
PYTHONPATH=. python api-management/generate_openapi.py --check
PYTHONPATH=. python api-management/generate_openapi.py --postman --check
```
