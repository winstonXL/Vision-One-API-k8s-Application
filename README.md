# Vision One Workbench Dashboard

A Flask-based web dashboard for TrendAI Vision One that displays workbench alerts and critical detection models, with on-demand AI-powered alert summarization via Amazon Bedrock.

---

## Features

- **Alerts tab** — displays all open workbench alerts from the past 7 days, ordered by severity. Includes summary statistics (total alerts, high severity count, affected accounts, common source IP), per-account filtering, and sort controls.
- **Detection Models tab** — displays the top 10 critical detection models from the Detection Model Management API, showing availability status, description, last updated date, and MITRE ATT&CK technique tags.
- **AI Summarization** — each alert card includes an AI Summary button that invokes Amazon Bedrock (amazon.nova-lite-v1:0) to generate a plain-English security summary covering what happened, why it is concerning, and recommended immediate actions.
- **Refresh button** — reloads both alerts and detection models simultaneously without a full page reload.
- **Dark mode** — automatically follows the system's color scheme preference.

---

## Project Structure

```
v1-workbench/
├── app.py                  # Flask backend — API routes and Bedrock integration
├── requirements.txt        # Python dependencies
├── Dockerfile              # Multi-stage Docker build
├── deployment.yaml         # Kubernetes Deployment and NodePort Service
├── app-secrets.yaml        # Kubernetes Secret manifest (Commited here for education)
└── templates/
    └── index.html          # Single-page frontend
```

---

## Prerequisites

- Python 3.12+
- Docker
- A Kubernetes cluster with `kubectl` configured
- TrendAI Vision One account with API access
- AWS account with Amazon Bedrock enabled in your target region and access to `amazon.nova-lite-v1:0`

---

## API Tokens Required

| Secret | Description |
|---|---|
| `TOKEN_ALERTS` | Vision One API token scoped to `/v3.0/workbench/alerts` |
| `TOKEN_MODELS` | Vision One API token scoped to `/v3.0/dmm/models` |
| `AWS_ACCESS_KEY_ID` | AWS IAM access key with `bedrock:InvokeModel` permission |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM secret access key |
| `AWS_REGION` | AWS region where Bedrock is enabled (e.g. `us-east-1`) |

Vision One API tokens can be generated from the Vision One console under **Administration → API Keys**.

---

## Docker

**Build the image:**
```bash
docker build -t <image_name:tag> .
```

**Run the container locally:**
```bash
docker run -p 8080:8080 \
  -e TOKEN_ALERTS="your-alerts-token" \
  -e TOKEN_MODELS="your-models-token" \
  -e AWS_ACCESS_KEY_ID="your-access-key-id" \
  -e AWS_SECRET_ACCESS_KEY="your-secret-access-key" \
  -e AWS_REGION="us-east-1" \
  your-registry.io/<image_name:tag>
```

**Push to your registry:**
```bash
docker push your-registry.io/<image_name:tag>
```

---

## Kubernetes Deployment

### 1. Populate app-secrets.yaml

All secret values must be base64-encoded. Encode each value with:
```bash
echo -n 'your-value-here' | base64
```

Open `app-secrets.yaml` and replace each `<...>` placeholder with the encoded value.

### 2. Update the image tag

In `deployment.yaml`, ensure the correct image name and tag matches your full image reference (in the :
```yaml
image: your-registry.io/<image_name:tag>
imagePullPolicy: <Never/Always>  # Dependant on if image is in local or remote poliy
```

### 3. Apply the manifests

```bash
kubectl apply -f app-secrets.yaml
kubectl apply -f deployment.yaml
```

### 4. Access the app

The app is exposed via NodePort on port **30100**. Access it at:
```
http://<node-ip>:30100
```

To find a node IP:
```bash
kubectl get nodes -o wide
```

---

## Kubernetes Resources

| Resource | Name | Description |
|---|---|---|
| `Secret` | `v1-workbench-secrets` | Holds all API tokens and AWS credentials |
| `Deployment` | `v1-workbench` | Instructions needed for app to run. Supports replication if desired |
| `Service` | `v1-workbench-svc` | NodePort service on port 30100 |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves the dashboard UI |
| `GET` | `/api/alerts` | Fetches open workbench alerts for the past 7 days |
| `GET` | `/api/models` | Fetches the top 10 critical detection models |
| `POST` | `/api/summarize` | Invokes Bedrock to summarize a single alert |

---

## Security Notes

- The container runs as a non-root user (`UID 1000`).
- All secrets are injected as environment variables from a Kubernetes `Secret` object — no plaintext credentials exist anywhere in the codebase.
- All secret values are `.strip()`-ed on read to prevent issues with trailing newlines introduced during base64 encoding.
- The app uses `gunicorn` as the production WSGI server with 2 workers. Scale horizontally by increasing the Deployment replica count rather than adding workers per pod.
