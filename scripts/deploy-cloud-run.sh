#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-me-central2}"
REGISTRY_REGION="${REGISTRY_REGION:-me-central1}"
SERVICE="${SERVICE:-hardware-intelligence-api}"
FRONTEND_URL="${FRONTEND_URL:-}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
REPOSITORY="pc-builder"

if [[ -z "$PROJECT_ID" || -z "$FRONTEND_URL" ]]; then
  echo "Usage: PROJECT_ID=... FRONTEND_URL=https://... $0" >&2
  exit 2
fi
command -v gcloud >/dev/null || { echo "gcloud CLI is required" >&2; exit 2; }
gcloud config set project "$PROJECT_ID" >/dev/null
gcloud artifacts repositories describe "$REPOSITORY" --location="$REGISTRY_REGION" --project="$PROJECT_ID" >/dev/null

IMAGE="$REGISTRY_REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$SERVICE:$IMAGE_TAG"
gcloud builds submit backend --project="$PROJECT_ID" --tag="$IMAGE"
RUNTIME_SERVICE_ACCOUNT="pc-builder-runtime@$PROJECT_ID.iam.gserviceaccount.com"
gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" --image="$IMAGE" \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" --port=8080 --cpu=1 --memory=512Mi \
  --min=0 --max=1 --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production,MARKET_DATA_MODE=free,FRONTEND_URL=$FRONTEND_URL,CORS_ORIGINS=$FRONTEND_URL,BACKEND_VERSION=0.1.0,API_CONTRACT_VERSION=1,PRICING_SCHEDULER_ENABLED=false,AUTONOMOUS_AGENTS_ENABLED=false,CPU_SPECS_SEED_ON_START=false" \
  --set-secrets="NEO4J_URI=NEO4J_URI:latest,NEO4J_USER=NEO4J_USER:latest,NEO4J_PASSWORD=NEO4J_PASSWORD:latest,NEO4J_DATABASE=NEO4J_DATABASE:latest,ANALYST_API_KEY=ANALYST_API_KEY:latest,ADMIN_API_KEY=ADMIN_API_KEY:latest,SUPER_ADMIN_API_KEY=SUPER_ADMIN_API_KEY:latest"

SERVICE_URL="$(gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')"
gcloud run services update "$SERVICE" --project="$PROJECT_ID" --region="$REGION" --update-env-vars="BACKEND_URL=$SERVICE_URL"
echo "Cloud Run service URL: $SERVICE_URL"
