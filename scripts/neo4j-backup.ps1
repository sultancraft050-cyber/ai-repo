param(
  [Parameter(Mandatory = $true)]
  [string]$OutputDirectory,
  [string]$ContainerName = "start-clean-project-neo4j-1",
  [string]$Database = "neo4j"
)

$resolved = Resolve-Path -LiteralPath $OutputDirectory -ErrorAction SilentlyContinue
if (-not $resolved) {
  New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
  $resolved = Resolve-Path -LiteralPath $OutputDirectory
}

if ($resolved.Path -like "$PSScriptRoot*") {
  throw "Backup output must be outside the app source folder."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpName = "$Database-$timestamp.dump"
docker exec $ContainerName mkdir -p /tmp/neo4j-backup
docker exec $ContainerName neo4j-admin database dump $Database --to-path=/tmp/neo4j-backup --overwrite-destination=true
docker cp "$ContainerName:/tmp/neo4j-backup/$Database.dump" (Join-Path $resolved.Path $dumpName)
