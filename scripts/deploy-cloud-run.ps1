param(
    [Parameter(Mandatory = $true)] [string]$ProjectId,
    [string]$Region = "me-central2",
    [string]$Service = "hardware-intelligence-api",
    [Parameter(Mandatory = $true)] [string]$FrontendUrl,
    [string]$ImageTag = ""
)

$ErrorActionPreference = "Stop"
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI is required. Install it or run this script from Google Cloud Shell."
}
if ([string]::IsNullOrWhiteSpace($ImageTag)) { $ImageTag = (git rev-parse --short HEAD).Trim() }
if ([string]::IsNullOrWhiteSpace($ImageTag)) { throw "Could not determine a Git commit tag." }

$Repository = "pc-builder"
$Image = "$Region-docker.pkg.dev/$ProjectId/$Repository/$Service`:$ImageTag"
$RuntimeServiceAccount = "pc-builder-runtime@$ProjectId.iam.gserviceaccount.com"

gcloud config set project $ProjectId | Out-Host
gcloud artifacts repositories describe $Repository --location=$Region --project=$ProjectId | Out-Null
gcloud builds submit backend --project=$ProjectId --tag=$Image

gcloud run deploy $Service `
    --project=$ProjectId --region=$Region --image=$Image `
    --service-account=$RuntimeServiceAccount --port=8080 --cpu=1 --memory=512Mi `
    --min=0 --max=1 --allow-unauthenticated `
    --set-env-vars="ENVIRONMENT=production,MARKET_DATA_MODE=free,FRONTEND_URL=$FrontendUrl,CORS_ORIGINS=$FrontendUrl,BACKEND_VERSION=0.1.0,API_CONTRACT_VERSION=1,PRICING_SCHEDULER_ENABLED=false,AUTONOMOUS_AGENTS_ENABLED=false,CPU_SPECS_SEED_ON_START=false" `
    --set-secrets="NEO4J_URI=NEO4J_URI:latest,NEO4J_USER=NEO4J_USER:latest,NEO4J_PASSWORD=NEO4J_PASSWORD:latest,NEO4J_DATABASE=NEO4J_DATABASE:latest,ANALYST_API_KEY=ANALYST_API_KEY:latest,ADMIN_API_KEY=ADMIN_API_KEY:latest,SUPER_ADMIN_API_KEY=SUPER_ADMIN_API_KEY:latest" | Out-Host

$ServiceUrl = (gcloud run services describe $Service --project=$ProjectId --region=$Region --format="value(status.url)").Trim()
if ([string]::IsNullOrWhiteSpace($ServiceUrl)) { throw "Cloud Run returned no service URL." }
gcloud run services update $Service --project=$ProjectId --region=$Region --update-env-vars="BACKEND_URL=$ServiceUrl" | Out-Host
Write-Host "Cloud Run service URL: $ServiceUrl"
