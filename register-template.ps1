[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [ValidateSet("resume", "cover_letter")]
    [string]$DocumentKind,
    [Parameter(Mandatory = $true)]
    [string]$HostPath
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
        throw "The template path must be inside the repository so the API container can access it. Put your template under $repoResolved."
    }
    return "/workspace/" + ($relative -replace "\\", "/")
}

$templatePath = Convert-ToContainerPath -Path $HostPath
$body = @{
    name = $Name
    document_kind = $DocumentKind
    template_path = $templatePath
    metadata_json = @{
        registered_from = $HostPath
    }
} | ConvertTo-Json -Depth 4

$result = Invoke-RestMethod `
    -Uri "$ApiBase/generation/templates" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body

Write-Host "Template registered." -ForegroundColor Green
Write-Host ("Name: {0}" -f $result.name)
Write-Host ("Kind: {0}" -f $result.document_kind)
Write-Host ("Container path: {0}" -f $result.template_path)
