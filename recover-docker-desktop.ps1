[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-DockerDaemon {
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker version --format "{{.Server.Version}}" 2>&1 | Out-Null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $oldPreference
    }
}

function Get-DockerDesktopPath {
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path $env:LocalAppData 'Programs\Docker\Docker\Docker Desktop.exe')
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Wait-Until {
    param(
        [scriptblock]$Condition,
        [string]$Description,
        [int]$TimeoutSeconds = 240,
        [int]$DelaySeconds = 3
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) {
            Write-Host "Ready: $Description" -ForegroundColor Green
            return
        }
        Start-Sleep -Seconds $DelaySeconds
    }

    throw "Timed out waiting for: $Description"
}

$desktopPath = Get-DockerDesktopPath
if (-not $desktopPath) {
    throw "Docker Desktop executable could not be found."
}

Write-Step "Shutting down WSL"
try {
    wsl --shutdown | Out-Null
} catch {
    Write-Host "Warning: WSL shutdown did not complete cleanly." -ForegroundColor Yellow
}

Write-Step "Stopping Docker Desktop"
try {
    Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue
} catch {
    Write-Host "Warning: Docker Desktop process could not be stopped cleanly." -ForegroundColor Yellow
}

Write-Step "Restarting Docker service"
$dockerService = Get-Service -Name "com.docker.service" -ErrorAction SilentlyContinue
if ($null -ne $dockerService) {
    try {
        if ($dockerService.Status -eq "Running") {
            Restart-Service -Name "com.docker.service" -ErrorAction Stop
        } else {
            Start-Service -Name "com.docker.service" -ErrorAction Stop
        }
    } catch {
        Write-Host "Warning: Docker service restart failed. If Docker does not recover, rerun this script from an Administrator PowerShell session." -ForegroundColor Yellow
    }
} else {
    Write-Host "Warning: com.docker.service was not found." -ForegroundColor Yellow
}

Write-Step "Starting Docker Desktop"
Start-Process -FilePath $desktopPath | Out-Null

Wait-Until -Description "Docker daemon" -Condition {
    Test-DockerDaemon
}

Write-Host ""
Write-Host "Docker Desktop recovered." -ForegroundColor Green
Write-Host "Next step:"
Write-Host "  .\start-platform.ps1"
