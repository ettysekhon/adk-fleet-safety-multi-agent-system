# Deployment Guide

This document covers the deployment architecture for the Fleet Safety system and the lessons learned from getting it production-ready.

Two distinct deployment targets are involved:

1. **Vertex AI Agent Engine** — the multi-agent system itself
2. **GKE** — the Google Maps MCP server (external dependency)

---

## TL;DR

| Component | Platform | Why |
|-----------|----------|-----|
| Fleet Safety Agent | Vertex AI Agent Engine | Serverless, managed scaling, built-in ADK support |
| Google Maps MCP Server | GKE | Agent Engine blocks subprocess spawning; MCP needs long-lived SSE connections |

---

## Prerequisites

Before deploying, enable these APIs:

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=YOUR_PROJECT_ID
```

> **Gotcha:** The `cloudresourcemanager.googleapis.com` API is often missed but required at runtime.

---

## Vertex AI Agent Engine vs Kubernetes

Both are Google Cloud. Both run containers. The similarities end there.

### Agent Engine: Serverless Agents

Agent Engine is purpose-built for ADK agents. You give it Python code and a requirements file; it handles containerisation, scaling, and the ADK runtime.

**What you provide:**

- Source packages (`./app`)
- Requirements file (`app/app_utils/requirements-deploy.txt`)
- Entrypoint module and object
- Environment variables

**What it handles:**

- Container build
- Cold start management
- Request routing
- Scaling (1-10 instances by default)
- Service account auth (no API keys needed)

**Key constraints:**

- **No subprocess spawning** — this breaks stdio-based MCP servers
- **Python 3.12** — check your dependencies support it
- **Reserved env vars** — `GOOGLE_CLOUD_PROJECT`, `GOOGLE_API_KEY` are managed by the platform
- **Startup time** — first request can take 30-60s (cold start)
- **Import-time code runs during build** — env checks at module level will fail

### GKE: Full Control

Kubernetes gives you a container runtime with no opinions about what's inside. You're responsible for everything.

**What you provide:**

- Dockerfile
- Kubernetes manifests (Deployment, Service)
- Health probes
- Resource limits

**What you handle:**

- Container building and pushing
- Scaling configuration
- Load balancer setup
- Secret management
- Rolling updates

**Why we use it for MCP:**

- MCP servers maintain long-lived SSE connections
- The server needs to spawn and manage sessions
- We need direct control over networking (LoadBalancer service type)

---

## Architecture: Why Two Platforms?

```text
┌─────────────────────────────────────────────────────────────────────┐
│  Client (ADK Web UI / GCP Console / Your App)                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Vertex AI Agent Engine                                             │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Fleet Safety Agent (ADK)                                     │  │
│  │  • Orchestrator + 5 specialist agents                         │  │
│  │  • LLM reasoning via Gemini                                   │  │
│  │  • Service account auth (no GOOGLE_API_KEY needed)            │  │
│  └───────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP/SSE (MCP_SERVER_URL)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GKE Cluster                                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Google Maps MCP Server                                       │  │
│  │  • /sse endpoint (GET) — SSE streaming                        │  │
│  │  • /messages endpoint (POST) — tool calls                     │  │
│  │  • /health endpoint (GET) — k8s probes                        │  │
│  └───────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Google Maps Platform APIs                                          │
│  (Places, Directions, Geocoding, Distance Matrix, Roads, Elevation) │
└─────────────────────────────────────────────────────────────────────┘
```

**The subprocess problem:**

Locally, ADK can spawn MCP servers as subprocesses (stdio transport). Agent Engine's container environment blocks this. The workaround is deploying MCP servers separately and connecting via SSE.

This is actually better for production anyway—you get independent scaling, easier debugging, and cleaner separation of concerns.

---

## Deployment Mechanics

### Agent Engine Deployment

The `deploy.py` script wraps the Vertex AI SDK:

```bash
make deploy
# or
uv run python -m app.app_utils.deploy \
  --project=YOUR_PROJECT \
  --location=europe-west2 \
  --display-name="fleet-safety-agent" \
  --env-file=.env
```

**What happens:**

1. Agent code is packaged (everything under `./app`)
2. Uploaded to a GCS staging bucket
3. Agent Engine builds a container with your requirements
4. Container is deployed with your env vars
5. `deployment_metadata.json` is generated with the Agent Engine ID

**Environment variable handling:**

The deploy script filters certain variables:

| Variable | Behaviour |
|----------|-----------|
| `GOOGLE_API_KEY` | **Filtered out** — Agent Engine uses service account auth |
| `GOOGLE_CLOUD_*` | **Filtered out** — Reserved by platform |
| `MCP_SERVER_URL` | **Passed through** — Needed for MCP connection |
| Everything else | **Passed through** |

### Requirements File

The deployment requirements are in `app/app_utils/requirements-deploy.txt` (not `.requirements.txt` which is gitignored).

Key packages that must be included:

```text
google-cloud-aiplatform[adk,agent_engines]>=1.118.0
vertexai>=1.0.0
google-adk[eval]>=1.15.0
mcp>=1.22.0
```

> **Gotcha:** The `vertexai` package must be explicitly listed even though it's part of `google-cloud-aiplatform`. The Agent Engine container doesn't always resolve it correctly.

---

## CI/CD: GitHub Actions with Workload Identity Federation

Both deployments use WIF for keyless authentication. No service account JSON files.

### How WIF Works

Instead of storing a JSON key as a GitHub secret, WIF lets GitHub Actions request short-lived tokens by proving its identity to Google Cloud.

```text
GitHub Actions                    Google Cloud
     │                                 │
     │  1. "I am repo ettysekhon/xyz"  │
     ├────────────────────────────────►│
     │                                 │
     │  2. Validates via OIDC          │
     │◄────────────────────────────────┤
     │                                 │
     │  3. Issues short-lived token    │
     │◄────────────────────────────────┤
     │                                 │
     │  4. Use token for gcloud/kubectl│
     ├────────────────────────────────►│
```

### GitHub Secrets Required

| Secret | Description | Example |
|--------|-------------|---------|
| `GCP_PROJECT_ID` | Your GCP project ID | `my-project-123` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full provider path | `projects/123456789/locations/global/workloadIdentityPools/github-pool-v2/providers/github-provider-v2` |
| `GCP_SERVICE_ACCOUNT` | Service account email | `github-actions-sa@my-project.iam.gserviceaccount.com` |
| `MCP_SERVER_URL` | Remote MCP server endpoint | `http://XX.XX.X.XXX/sse` |

> **Critical:** The `GCP_WORKLOAD_IDENTITY_PROVIDER` must use the **project number** (e.g., `123456789`), not the project ID.

### WIF Setup

```bash
PROJECT_ID=your-project-id
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
POOL_NAME=github-pool
PROVIDER_NAME=github-provider
SA_NAME=github-actions-sa

# Create pool
gcloud iam workload-identity-pools create $POOL_NAME \
  --location="global" \
  --project=$PROJECT_ID

# Create provider
gcloud iam workload-identity-pools providers create-oidc $PROVIDER_NAME \
  --location="global" \
  --workload-identity-pool=$POOL_NAME \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository_owner=assertion.repository_owner,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository_owner == 'YOUR_GITHUB_USERNAME'" \
  --project=$PROJECT_ID

# Create service account
gcloud iam service-accounts create $SA_NAME \
  --display-name="GitHub Actions" \
  --project=$PROJECT_ID

# Grant required roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"
```

### Service Account Binding (Per-Repo)

This is the step most people miss. The service account needs to allow the WIF pool to impersonate it:

```bash
# Option A: Allow specific repo
gcloud iam service-accounts add-iam-policy-binding \
  $SA_NAME@$PROJECT_ID.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_NAME/attribute.repository/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME" \
  --project=$PROJECT_ID

# Option B: Allow all repos under your account
gcloud iam service-accounts add-iam-policy-binding \
  $SA_NAME@$PROJECT_ID.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_NAME/attribute.repository_owner/YOUR_GITHUB_USERNAME" \
  --project=$PROJECT_ID
```

### Verify WIF Setup

```bash
# List pools
gcloud iam workload-identity-pools list --location=global --project=$PROJECT_ID

# Check pool status (watch for DELETED state!)
gcloud iam workload-identity-pools describe $POOL_NAME \
  --location=global --project=$PROJECT_ID

# List providers
gcloud iam workload-identity-pools providers list \
  --workload-identity-pool=$POOL_NAME \
  --location=global --project=$PROJECT_ID

# Check service account bindings
gcloud iam service-accounts get-iam-policy \
  $SA_NAME@$PROJECT_ID.iam.gserviceaccount.com \
  --project=$PROJECT_ID
```

---

## Common Deployment Errors

### "invalid_target" WIF Error

```text
failed to generate Google Cloud federated token: {"error":"invalid_target"}
```

**Causes:**

1. Wrong project number (using project ID instead)
2. Pool or provider is DELETED (check with `describe` command)
3. Pool/provider name typo
4. Missing service account binding for this repo

**Fix:**

```bash
# Verify the full path
gcloud iam workload-identity-pools providers describe $PROVIDER_NAME \
  --workload-identity-pool=$POOL_NAME \
  --location=global \
  --project=$PROJECT_ID \
  --format="value(name)"
```

### "No module named 'vertexai'"

The Agent Engine container couldn't find the `vertexai` package.

**Fix:** Add `vertexai>=1.0.0` to `app/app_utils/requirements-deploy.txt`.

### "GOOGLE_API_KEY is not set"

Your code has import-time env checks that fail during the deploy script's import phase.

**Fix:** Add dummy env vars to the CI workflow:

```yaml
env:
  GOOGLE_API_KEY: "placeholder-for-import"
  GOOGLE_MAPS_API_KEY: "placeholder-for-import"
```

### "GOOGLE_MAPS_API_KEY is not set but required"

The env check doesn't know you're using a remote MCP server.

**Fix:** Update env check logic to skip if `MCP_SERVER_URL` is set (already done in this codebase).

### "Cloud Resource Manager API has not been used"

Missing API enablement.

**Fix:**

```bash
gcloud services enable cloudresourcemanager.googleapis.com --project=$PROJECT_ID
```

### "The Reasoning Engine failed to be updated"

Generic error. Check Cloud Logs for the real issue:

```bash
gcloud logging read \
  "resource.type=aiplatform.googleapis.com/ReasoningEngine" \
  --project=$PROJECT_ID \
  --limit=20 \
  --format="table(timestamp,textPayload)" \
  --freshness=10m
```

---

## Debugging Production Issues

### Agent Engine Logs

```bash
# Via gcloud
gcloud logging read "resource.type=aiplatform.googleapis.com/ReasoningEngine" \
  --project=YOUR_PROJECT --limit=50

# Or use Cloud Console → Logs Explorer
# Filter: resource.type="aiplatform.googleapis.com/ReasoningEngine"
```

### GKE (MCP Server)

```bash
kubectl logs -l app=google-maps-mcp-server --tail=100 -f
```

---

## Cost Considerations

### Agent Engine

- Billed per vCPU-hour and memory-hour while instances are running
- `min_instances=1` means you pay 24/7 for at least one instance
- Cold starts are free but add latency

**Recommendation:** Set `min_instances=0` for dev/staging, `min_instances=1` for prod.

### GKE Autopilot

- Billed per pod resource request
- No cluster management fee
- Scales to zero if no pods

### Google Maps APIs

- $200/month free credit
- ~28k geocoding requests or ~40k directions requests per month free
- Enable billing alerts

---

## Local Development vs Production

| Aspect | Local (`make playground`) | Production (Agent Engine) |
|--------|--------------------------|---------------------------|
| **MCP transport** | stdio (subprocess) or SSE | SSE only |
| **Auth** | `GOOGLE_API_KEY` env var | Service account |
| **Scaling** | Single process | 1-10 instances |
| **Cold start** | None | 30-60s first request |
| **Debugging** | Full traces in Web UI | Cloud Logging |

**Tip:** Always test with `MCP_SERVER_URL` locally before deploying:

```bash
export MCP_SERVER_URL=http://XX.XX.X.XXX/sse
make playground
```

---

## Security Checklist

- [ ] **No API keys in code** — use env vars or secrets
- [ ] **WIF configured** — no JSON key files in CI/CD
- [ ] **API key restrictions** — restrict Maps key to specific APIs and IPs
- [ ] **Least privilege** — service accounts have only required roles
- [ ] **Secrets in k8s** — not in manifests or env vars

---

## Quick Reference

### Deploy Agent Engine

```bash
make deploy
```

### Check Agent Engine Status

```bash
gcloud ai agent-engines list --project=YOUR_PROJECT --location=europe-west2
```

### Query Deployed Agent

```bash
uv run python scripts/query_deployed_agent.py --query "Fleet status?"
```

### Check MCP Server

```bash
curl http://YOUR_MCP_IP/health
```

### View Logs

```bash
# Agent Engine
gcloud logging read "resource.type=aiplatform.googleapis.com/ReasoningEngine" \
  --project=YOUR_PROJECT --limit=20 --freshness=10m

# MCP Server
kubectl logs -l app=google-maps-mcp-server -f
```
