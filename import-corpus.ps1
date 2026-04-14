[CmdletBinding()]
param(
    [string]$HostPath = ".\private-data\corpus",
    [string[]]$RoleHint = @(),
    [string]$SourceDocumentGlob = "**/*"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ApiBase = "http://localhost:8013/api/v1"

function Convert-ToContainerPath {
    param([string]$Path)

    $resolved = (Resolve-Path $Path).Path
    $repoResolved = (Resolve-Path $RepoRoot).Path
    $relative = [System.IO.Path]::GetRelativePath($repoResolved, $resolved)
    if ($relative.StartsWith("..")) {
        throw "The path must be inside the repository so the API container can access it. Put your files under $repoResolved."
    }
    return "/workspace/" + ($relative -replace "\\", "/")
}

$containerPath = Convert-ToContainerPath -Path $HostPath
$body = @{
    path = $containerPath
    role_hint = $RoleHint
    source_document_glob = $SourceDocumentGlob
} | ConvertTo-Json

$result = Invoke-RestMethod `
    -Uri "$ApiBase/corpus/ingest" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body

Write-Host "Corpus ingested." -ForegroundColor Green
Write-Host ("Documents: {0}, fragments: {1}, prompts: {2}" -f $result.ingested_documents, $result.created_fragments, $result.created_prompts)
if ($result.warnings.Count -gt 0) {
    Write-Host "Warnings:" -ForegroundColor Yellow
    $result.warnings | ForEach-Object { Write-Host "- $_" }
}
