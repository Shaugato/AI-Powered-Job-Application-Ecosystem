[CmdletBinding()]
param(
    [switch]$RunSmokeTest,
    [switch]$NoBuild,
    [switch]$StartDockerDesktop,
    [switch]$RecoverDocker
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvPath = Join-Path $RepoRoot ".env"
$EnvExamplePath = Join-Path $RepoRoot ".env.example"

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Default = ""
    )

    if (-not (Test-Path $Path)) {
        return $Default
    }

    $match = Select-String -Path $Path -Pattern "^$Key=(.*)$" | Select-Object -First 1
    if ($null -eq $match) {
        return $Default
    }

    return $match.Matches[0].Groups[1].Value.Trim()
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-Docker {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & docker @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
    }

    foreach ($line in $output) {
        if ($null -ne $line) {
            $text = "$line"
            if (-not [string]::IsNullOrWhiteSpace($text)) {
                Write-Host $text
            }
        }
    }

    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "docker $($Arguments -join ' ') failed with exit code $exitCode"
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = @($output | ForEach-Object { "$_" })
    }
}

function Wait-Until {
    param(
        [scriptblock]$Condition,
        [string]$Description,
        [int]$TimeoutSeconds = 120,
        [int]$DelaySeconds = 2
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

function Test-DockerDaemon {
    try {
        $result = Invoke-Docker -Arguments @("version", "--format", "{{.Server.Version}}") -AllowFailure
        return $result.ExitCode -eq 0
    } catch {
        return $false
    }
}

function Get-ComposeProjectName {
    $name = Split-Path -Leaf $RepoRoot
    return ($name -replace '[^a-zA-Z0-9]', '').ToLowerInvariant()
}

function Test-LocalAppImagesAvailable {
    $projectName = Get-ComposeProjectName
    $images = @(
        "$projectName-api",
        "$projectName-worker",
        "$projectName-frontend"
    )

    foreach ($image in $images) {
        $result = Invoke-Docker -Arguments @("image", "inspect", $image) -AllowFailure
        if ($result.ExitCode -ne 0) {
            return $false
        }
    }

    return $true
}

function Test-BuildNetworkFailure {
    param([string[]]$Output)

    $joined = ($Output -join "`n").ToLowerInvariant()
    $patterns = @(
        "registry-1.docker.io",
        "failed to resolve source metadata",
        "no such host",
        "dial tcp",
        "https proxy",
        "failed to do request"
    )

    foreach ($pattern in $patterns) {
        if ($joined.Contains($pattern)) {
            return $true
        }
    }

    return $false
}

function Start-ApplicationServices {
    param([switch]$SkipBuild)

    $appArgs = @("compose", "up", "-d")
    if (-not $SkipBuild) {
        $appArgs += "--build"
    }
    $appArgs += @("api", "worker", "frontend")

    $result = Invoke-Docker -Arguments $appArgs -AllowFailure
    if ($result.ExitCode -eq 0) {
        return
    }

    if (-not $SkipBuild -and (Test-BuildNetworkFailure -Output $result.Output) -and (Test-LocalAppImagesAvailable)) {
        Write-Host ""
        Write-Host "Build failed because Docker could not reach the registry. Falling back to existing local images." -ForegroundColor Yellow
        Invoke-Docker -Arguments @("compose", "up", "-d", "api", "worker", "frontend") | Out-Null
        return
    }

    throw "docker $($appArgs -join ' ') failed with exit code $($result.ExitCode)"
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

function Get-PythonLauncher {
    foreach ($name in @('py', 'python')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $command.Source
        }
    }

    return $null
}

function Test-BrowserBridge {
    param([int]$Port)

    try {
        $response = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/health" -f $Port) -Method Get -TimeoutSec 2
        return $response.status -eq 'ok'
    } catch {
        return $false
    }
}

function Ensure-BrowserBridge {
    param([int]$Port)

    if (Test-BrowserBridge -Port $Port) {
        Write-Host "Ready: Browser bridge" -ForegroundColor Green
        return
    }

    $launcher = Get-PythonLauncher
    if (-not $launcher) {
        Write-Host "Warning: Python launcher not found. Guided sign-in will fall back to the manual helper." -ForegroundColor Yellow
        return
    }

    $bridgeScript = Join-Path $RepoRoot 'host-browser-bridge.py'
    if (-not (Test-Path $bridgeScript)) {
        Write-Host "Warning: Browser bridge script is missing. Guided sign-in will fall back to the manual helper." -ForegroundColor Yellow
        return
    }

    Write-Step "Starting browser bridge"
    if ([System.IO.Path]::GetFileName($launcher).ToLowerInvariant() -eq 'py.exe' -or [System.IO.Path]::GetFileName($launcher).ToLowerInvariant() -eq 'py') {
        Start-Process -FilePath $launcher -ArgumentList @('-3', $bridgeScript, '--port', $Port, '--repo-root', $RepoRoot) -WindowStyle Hidden | Out-Null
    } else {
        Start-Process -FilePath $launcher -ArgumentList @($bridgeScript, '--port', $Port, '--repo-root', $RepoRoot) -WindowStyle Hidden | Out-Null
    }

    try {
        Wait-Until -Description 'Browser bridge' -TimeoutSeconds 20 -DelaySeconds 1 -Condition {
            Test-BrowserBridge -Port $Port
        }
    } catch {
        Write-Host "Warning: Browser bridge did not come online. Guided sign-in will fall back to the manual helper." -ForegroundColor Yellow
    }
}

function Recover-DockerDesktop {
    $desktopPath = Get-DockerDesktopPath
    if (-not $desktopPath) {
        throw "Docker Desktop executable could not be found. Start Docker Desktop manually, wait for it to finish loading, then rerun the script."
    }

    Write-Step "Recovering Docker Desktop"

    try {
        wsl --shutdown | Out-Null
    } catch {
        Write-Host "Warning: WSL shutdown did not complete cleanly." -ForegroundColor Yellow
    }

    try {
        Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Host "Warning: Docker Desktop process could not be stopped cleanly." -ForegroundColor Yellow
    }

    $dockerService = Get-Service -Name "com.docker.service" -ErrorAction SilentlyContinue
    if ($null -ne $dockerService) {
        try {
            if ($dockerService.Status -eq "Running") {
                Restart-Service -Name "com.docker.service" -ErrorAction Stop
            } else {
                Start-Service -Name "com.docker.service" -ErrorAction Stop
            }
        } catch {
            Write-Host "Warning: Docker Desktop Windows service could not be restarted automatically. If the next step fails, rerun PowerShell as Administrator and try again." -ForegroundColor Yellow
        }
    }

    Write-Step "Starting Docker Desktop"
    Start-Process -FilePath $desktopPath | Out-Null

    Wait-Until -Description "Docker daemon" -TimeoutSeconds 240 -Condition {
        Test-DockerDaemon
    }
}

function Ensure-DockerDaemon {
    param(
        [switch]$StartDesktop,
        [switch]$RecoverDesktop
    )

    if (Test-DockerDaemon) {
        Write-Host "Ready: Docker daemon" -ForegroundColor Green
        return
    }

    if ($RecoverDesktop) {
        Recover-DockerDesktop
        return
    }

    if ($StartDesktop) {
        $desktopPath = Get-DockerDesktopPath
        if (-not $desktopPath) {
            throw "Docker Desktop is not running, and the Docker Desktop executable could not be found. Start Docker Desktop manually, wait for it to finish loading, then rerun the script."
        }

        Write-Step "Starting Docker Desktop"
        Start-Process -FilePath $desktopPath | Out-Null

        Wait-Until -Description "Docker daemon" -TimeoutSeconds 180 -Condition {
            Test-DockerDaemon
        }
        return
    }

    $message = "Docker Desktop is installed, but the Docker Linux engine is not running.`n`nFix:`n1. Start Docker Desktop.`n2. Wait until Docker finishes loading.`n3. Make sure it is using Linux containers.`n4. Rerun: .\start-platform.ps1`n`nOr let the script try to open Docker Desktop for you:`n  .\start-platform.ps1 -StartDockerDesktop`n`nIf the engine pipe keeps disappearing, use the repo recovery flow:`n  .\start-platform.ps1 -RecoverDocker"
    throw $message
}

Assert-Command "docker"

Write-Step "Checking Docker Compose"
Invoke-Docker -Arguments @("compose", "version") | Out-Null

Write-Step "Checking Docker daemon"
Ensure-DockerDaemon -StartDesktop:$StartDockerDesktop -RecoverDesktop:$RecoverDocker

if (-not (Test-Path $EnvPath)) {
    Write-Step "Creating .env from .env.example"
    Copy-Item $EnvExamplePath $EnvPath
}

$ApiHostPort = Get-EnvValue -Path $EnvPath -Key "API_HOST_PORT" -Default (Get-EnvValue -Path $EnvPath -Key "API_PORT" -Default "8000")
$FrontendHostPort = Get-EnvValue -Path $EnvPath -Key "FRONTEND_HOST_PORT" -Default (Get-EnvValue -Path $EnvPath -Key "FRONTEND_PORT" -Default "5173")
$TemporalUiHostPort = Get-EnvValue -Path $EnvPath -Key "TEMPORAL_UI_HOST_PORT" -Default "8080"
$MinioConsoleHostPort = Get-EnvValue -Path $EnvPath -Key "MINIO_CONSOLE_HOST_PORT" -Default "9001"
$BrowserBridgePort = [int](Get-EnvValue -Path $EnvPath -Key "BROWSER_BRIDGE_PORT" -Default "8877")
$HealthUrl = "http://localhost:$ApiHostPort/api/v1/health"

Ensure-BrowserBridge -Port $BrowserBridgePort

Push-Location $RepoRoot
try {
    Write-Step "Starting infrastructure services"
    Invoke-Docker -Arguments @("compose", "up", "-d", "postgres", "minio", "temporal", "temporal-ui") | Out-Null

    Wait-Until -Description "Postgres container readiness" -TimeoutSeconds 120 -Condition {
        try {
            $result = Invoke-Docker -Arguments @("compose", "exec", "-T", "postgres", "pg_isready", "-U", "postgres", "-d", "job_ecosystem") -AllowFailure
            return $result.ExitCode -eq 0
        } catch {
            return $false
        }
    }

    Write-Step "Ensuring pgvector extension exists"
    Invoke-Docker -Arguments @("compose", "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "job_ecosystem", "-c", "CREATE EXTENSION IF NOT EXISTS vector;") | Out-Null

    Write-Step "Starting application services"
    Start-ApplicationServices -SkipBuild:$NoBuild

    Wait-Until -Description "API health endpoint" -TimeoutSeconds 180 -Condition {
        try {
            $response = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 5
            return $response.status -eq "ok"
        } catch {
            return $false
        }
    }

    Write-Host ""
    Write-Host "Platform is up." -ForegroundColor Green
    Write-Host "Dashboard:    http://localhost:$FrontendHostPort"
    Write-Host "API docs:     http://localhost:$ApiHostPort/docs"
    Write-Host "Temporal UI:  http://localhost:$TemporalUiHostPort"
    Write-Host "MinIO:        http://localhost:$MinioConsoleHostPort"
    Write-Host ""
    Write-Host "Smoke test command:"
    Write-Host "  .\smoke-test.ps1"

    if ($RunSmokeTest) {
        Write-Step "Running smoke test"
        & (Join-Path $RepoRoot "smoke-test.ps1")
    }
} finally {
    Pop-Location
}
