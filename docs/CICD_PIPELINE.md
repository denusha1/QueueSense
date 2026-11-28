# QueueSense CI/CD

[Continuous Integration](../.github/workflows/ci.yml) runs for pull requests, pushes to `main`, and manual runs in GitHub Actions. It calls reusable workflows so the same checks run when a developer requests an individual validation workflow. Validation jobs use read-only repository permissions and ephemeral synthetic fixtures.

| Workflow | Checks | Downloadable artifacts |
| --- | --- | --- |
| [Backend validation](../.github/workflows/backend.yml) | Applies migrations to PostgreSQL 17, checks SQL integrity, runs Pytest and generator tests, validates both OpenAPI contracts and checks generated OpenAPI and Postman files for drift. Scans Python dependencies with pip-audit. A parallel job verifies the migrations with PGlite and audits that npm lockfile. | Pytest JUnit XML, dependency audit JSON and migration logs |
| [Frontend validation](../.github/workflows/frontend.yml) | Installs from the npm lockfile. Runs ESLint, a production Next.js build and TypeScript checks. Starts FastAPI and Next.js against synthetic PostgreSQL data and runs Chromium browser tests. Runs npm audit. | Browser JUnit XML, synthetic screenshots, local service logs and dependency audit JSON |
| [Deployment preparation](../.github/workflows/deployment-preparation.yml) | Builds the migration, FastAPI and Next.js images, then tests the full Compose stack against a fresh PostgreSQL volume, including database and API outage recovery. | Compose smoke output and the gateway OpenAPI contract |

CI enforces the lint baseline per file and rule. [The baseline](../frontend/eslint-suppressions.json) records pre-existing errors per file and rule, and the command currently allows up to 13 existing warnings. Reduce those counts as each issue is fixed. npm checks fail on high or critical findings. pip-audit fails on any reported advisory. Audit JSON records the result observed during that run.

Open **Actions → Continuous Integration** to find the jobs and their artifacts. The CI pull-request and push triggers build and test locally on a hosted runner. They use no deployment credentials and publish no registry image.

## Optional Choreo Development deployment

The [manual workflow](../.github/workflows/choreo-development.yml) invokes the official WSO2 Developer Platform CLI to deploy an existing successful build for a configured Service to its `Development` environment. It uses a pinned CLI release and checks the download digest.

1. In Choreo, confirm that your organization has a project, a Git-backed Service, a deployment track, a Development environment and a successful build on that track. Record the organization handle and build ID.
2. In GitHub repository settings, create the `choreo-development` environment. Restrict deployment branches to `main` and configure required reviewers where supported by your GitHub plan.
3. Add environment variables `CHOREO_ORG`, `CHOREO_PROJECT`, `CHOREO_COMPONENT` and `CHOREO_DEPLOYMENT_TRACK`. Set `CHOREO_REGION` to `EU` for an EU organization. The workflow defaults to `US`. Give a Choreo account with Development deployment permission a personal access token and add it as the `CHOREO_PAT` environment secret.
4. In GitHub Actions, open **Deploy an existing build to Choreo Development**, select `main` and enter the build ID. Approve the GitHub environment request if required.
5. Check the Choreo Console for rollout success and test its configured health endpoint. The workflow result confirms that the CLI accepted the deployment request.

See the official instructions for [setting up the CLI](https://wso2.com/engineering-platform/developer-platform/docs/choreo-cli/get-started-with-the-choreo-cli/), [using a personal access token](https://wso2.com/engineering-platform/developer-platform/docs/choreo-cli/manage-authentication-with-personal-access-tokens/) and [managing deployment tracks](https://wso2.com/engineering-platform/developer-platform/docs/develop-components/manage-deployment-tracks-for-choreo-components/).

The optional workflow requires access to an existing Choreo organization. Local validation covers workflow syntax and checks executed outside GitHub Actions. GitHub-hosted runs and Choreo rollout verification require those environments.
