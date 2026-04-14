param(
    [Parameter(Mandatory = $true)]
    [string]$ConnectionId,

    [Parameter(Mandatory = $true)]
    [string]$LoginUrl,

    [Parameter(Mandatory = $true)]
    [int]$Port
)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$profileDir = Join-Path $repoRoot ("private-data\integrations\{0}\browser-profile" -f $ConnectionId)
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

$browserCandidates = @(
    "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:LocalAppData\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
)

$browserExe = $browserCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browserExe) {
    throw "Could not find Microsoft Edge or Google Chrome. Install one of them, then run this helper again."
}

$args = @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$profileDir",
    "--no-first-run",
    "--new-window",
    $LoginUrl
)

Start-Process -FilePath $browserExe -ArgumentList $args | Out-Null
Write-Host "Opened guided sign-in browser on port $Port"
Write-Host "1. Complete sign-in in the new browser window."
Write-Host "2. Return to the platform."
Write-Host "3. Click 'Finish connection' in the Connections page."
