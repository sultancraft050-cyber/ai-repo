param(
  [Parameter(Mandatory = $true)]
  [string]$DumpFile,
  [string]$ContainerName = "start-clean-project-neo4j-1",
  [string]$Database = "neo4j"
)

$resolved = Resolve-Path -LiteralPath $DumpFile
docker exec $ContainerName mkdir -p /tmp/neo4j-restore
docker cp $resolved.Path "$ContainerName:/tmp/neo4j-restore/$Database.dump"
docker exec $ContainerName neo4j-admin database load $Database --from-path=/tmp/neo4j-restore --overwrite-destination=true
