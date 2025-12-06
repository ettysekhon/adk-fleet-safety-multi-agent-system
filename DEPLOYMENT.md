# Deployment Guide

This document covers the deployment architecture for the Fleet Safety system. Two distinct deployment targets are involved:

1. **Vertex AI Agent Engine** — the multi-agent system itself
2. **GKE** — the Google Maps MCP server (external dependency)

Understanding why each component lives where it does matters for debugging and future architecture decisions.

---

## TL;DR

| Component | Platform | Why |
|-----------|----------|-----|
| Fleet Safety Agent | Vertex AI Agent Engine | Serverless, managed scaling, built-in ADK support |
| Google Maps MCP Server | GKE | Agent Engine blocks subprocess spawning; MCP needs long-lived SSE connections |

---

## Vertex AI Agent Engine vs Kubernetes

Both are Google Cloud. Both run containers. The similarities end there.

### Agent Engine: Serverless Agents

Agent Engine is purpose-built for ADK agents. You give it Python code and a requirements file; it handles containerisation, scaling, and the ADK runtime.

**What you provide:**

- Source packages (`./app`)
- Requirements file
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

### GKE Deployment (MCP Server)

See [HANDOVER_GOOGLE_MAPS_MCP.md](HANDOVER_GOOGLE_MAPS_MCP.md) for the full setup. Key points:

```bash
# Create cluster (one-time)
gcloud container clusters create-auto google-maps-cluster \
  --location=europe-west2

# Create secret for Maps API key
kubectl create secret generic google-maps-api-key \
  --from-literal=key=YOUR_KEY

# Deploy (via GitHub Actions or manually)
kubectl apply -f k8s/deployment.yaml
```

**Critical gotchas:**

- Use `pip install uv` in Dockerfile, not `COPY --from=ghcr.io/astral-sh/uv` (DNS failures)
- Add liveness/readiness probes (k8s can't detect unhealthy pods otherwise)
- Use commit SHA tags, not just `latest` (otherwise pods won't update)

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

### Reusing WIF Across Repos

If your WIF is configured with `attribute.repository_owner == 'YOUR_USERNAME'`, any repo under that account can authenticate. No per-repo setup.

**GitHub secrets needed (same for all repos):**

| Secret | Description |
|--------|-------------|
| `GCP_PROJECT_ID` | Your GCP project ID |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/PROJECT_NUM/locations/global/workloadIdentityPools/POOL/providers/PROVIDER` |
| `GCP_SERVICE_ACCOUNT` | `sa-name@project.iam.gserviceaccount.com` |

### Workflow Comparison

| Aspect | Agent Engine (`deploy.yml`) | GKE (MCP Server) |
|--------|----------------------------|------------------|
| **Build step** | None (Agent Engine builds) | Docker build + push |
| **Deploy step** | `deploy.py` script | `kubectl apply` |
| **Secrets passed** | Via `--set-env-vars` | Via k8s Secret |
| **Health check** | Managed by Agent Engine | Your responsibility |
| **Rollback** | Redeploy previous version | `kubectl rollout undo` |

---

## Debugging Production Issues

### Agent Engine Logs & Issues

**Logs:**

```bash
# Via gcloud
gcloud logging read "resource.type=aiplatform.googleapis.com/ReasoningEngine" \
  --project=YOUR_PROJECT --limit=50

# Or use Cloud Console → Logs Explorer
# Filter: resource.type="aiplatform.googleapis.com/ReasoningEngine"
```

**Common issues:**

| Symptom | Likely cause |
|---------|--------------|
| Cold start timeout | Dependencies too heavy; check requirements |
| `GOOGLE_API_KEY not set` | You're using API key auth; switch to `vertexai.init()` |
| `Connection closed` to MCP | MCP server down or `MCP_SERVER_URL` wrong |
| `subprocess blocked` | You're trying to spawn a process; use SSE transport |

### GKE (MCP Server)

**Logs:**

```bash
kubectl logs -l app=google-maps-mcp-server --tail=100 -f
```

**Common issues:**

| Symptom | Likely cause |
|---------|--------------|
| Pod `CrashLoopBackOff` | Missing secret, bad health endpoint, or crash on startup |
| 307 redirect on `/sse` | ASGI middleware misconfigured |
| `ImagePullBackOff` | Wrong image path or missing push |
| No external IP | LoadBalancer provisioning (wait 2-3 mins) |

---

## Cost Considerations

### Agent Engine Costs

- Billed per vCPU-hour and memory-hour while instances are running
- `min_instances=1` means you pay 24/7 for at least one instance
- Cold starts are free but add latency

**Recommendation:** Set `min_instances=0` for dev/staging, `min_instances=1` for prod.

### GKE Autopilot

- Billed per pod resource request
- No cluster management fee
- Scales to zero if no pods

**Recommendation:** Use resource requests that match actual usage. Don't over-provision.

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

**Tip:** Always test with `MCP_SERVER_URL` locally before deploying. This catches MCP connectivity issues early.

```bash
# Local with remote MCP (mirrors production)
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
- [ ] **MCP server not public** — consider VPC peering for production

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

### View MCP Logs

```bash
kubectl logs -l app=google-maps-mcp-server -f
```

### Restart MCP Server

```bash
kubectl rollout restart deployment/google-maps-mcp-server
```
