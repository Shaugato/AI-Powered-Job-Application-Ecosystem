[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ApiBase = "http://localhost:8013/api/v1"
$CorpusPathInContainer = "/workspace/sample-data/corpus"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Yellow
}

function Wait-ForApi {
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri "$ApiBase/health" -Method Get -TimeoutSec 5
            if ($health.status -eq "ok") {
                return
            }
        } catch {
        }
        Start-Sleep -Seconds 2
    }
    throw "API did not become healthy in time."
}

function Get-StatusCode {
    param($ErrorRecord)
    try {
        return [int]$ErrorRecord.Exception.Response.StatusCode
    } catch {
        return $null
    }
}

Push-Location $RepoRoot
try {
    Write-Step "Waiting for API"
    Wait-ForApi

    Write-Step "Ingesting sample corpus from $CorpusPathInContainer"
    $ingestBody = @{
        path = $CorpusPathInContainer
        role_hint = @("Cloud", "DevOps")
        source_document_glob = "**/*"
    } | ConvertTo-Json

    $ingestResult = Invoke-RestMethod `
        -Uri "$ApiBase/corpus/ingest" `
        -Method Post `
        -ContentType "application/json" `
        -Body $ingestBody

    Write-Host ("Documents: {0}, fragments: {1}, prompts: {2}" -f `
        $ingestResult.ingested_documents, `
        $ingestResult.created_fragments, `
        $ingestResult.created_prompts)

    Write-Step "Approving pending evidence fragments from the sample corpus"
    $pendingEvidence = @(Invoke-RestMethod -Uri "$ApiBase/corpus/evidence?truth_status=pending" -Method Get | ForEach-Object { $_ })
    $sampleEvidence = @($pendingEvidence | Where-Object { $_.source_document -like "$CorpusPathInContainer*" } | ForEach-Object { $_ })
    foreach ($fragment in $sampleEvidence) {
        $fragmentIds = @($fragment.id)
        if ($fragmentIds.Count -eq 1 -and $fragmentIds[0] -is [string] -and $fragmentIds[0] -match '\s') {
            $fragmentIds = @($fragmentIds[0] -split '\s+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        }
        if ($fragmentIds.Count -eq 0) {
            Write-Host "Skipping fragment with missing id." -ForegroundColor DarkYellow
            continue
        }

        foreach ($fragmentId in $fragmentIds) {
            $approveBody = @{ approved = $true; reviewer_notes = "Approved by smoke-test" } | ConvertTo-Json
            $approveUri = "$ApiBase/corpus/evidence/$([uri]::EscapeDataString([string]$fragmentId))/approve"
            try {
                Invoke-RestMethod `
                    -Uri $approveUri `
                    -Method Post `
                    -ContentType "application/json" `
                    -Body $approveBody | Out-Null
            } catch {
                $statusCode = Get-StatusCode $_
                if ($statusCode -eq 404) {
                    Write-Host "Skipping stale fragment id: $fragmentId" -ForegroundColor DarkYellow
                    continue
                }
                throw
            }
        }
    }
    Write-Host ("Approved sample fragments: {0}" -f $sampleEvidence.Count)

    Write-Step "Creating or updating a sample job"
    $jobBody = @{
        source = "company_portal"
        external_id = "smoke-job-001"
        source_url = "https://example.com/jobs/cloud-devops-engineer"
        company = "ExampleCo"
        title = "Cloud DevOps Engineer"
        location = "Melbourne, VIC"
        work_mode = "hybrid"
        description_text = "Looking for AWS, Terraform, Kubernetes, CI/CD, Linux, and cloud operations experience. Must be comfortable with security controls, monitoring, and platform reliability."
        classification_labels = @()
        eligibility_flags = @()
        risk_flags = @()
        metadata_json = @{
            test_run = $true
        }
    } | ConvertTo-Json -Depth 4

    $job = Invoke-RestMethod `
        -Uri "$ApiBase/jobs" `
        -Method Post `
        -ContentType "application/json" `
        -Body $jobBody

    Write-Host ("Job id: {0}" -f $job.id)

    Write-Step "Generating resume and cover letter"
    $generationBody = @{
        job_id = $job.id
        template_variant_name = "default-resume"
        cover_template_variant_name = "default-cover-letter"
        force_regenerate = $false
    } | ConvertTo-Json

    try {
        $generation = Invoke-RestMethod `
            -Uri "$ApiBase/generation/requests" `
            -Method Post `
            -ContentType "application/json" `
            -Body $generationBody
    } catch {
        $statusCode = Get-StatusCode $_
        if ($statusCode -ge 500) {
            Write-Host "Generation request failed with server error. Check API logs with: docker compose logs api --tail 200" -ForegroundColor Red
        }
        throw
    }

    Write-Host ("Generation result id: {0}" -f $generation.id)
    Write-Host ("Compile status: {0}" -f $generation.compile_status)
    Write-Host ("Grounding notes: {0}" -f $generation.grounding_notes)

    Write-Step "Creating application plan"
    $planBody = @{
        job_id = $job.id
        generation_result_id = $generation.id
    } | ConvertTo-Json

    $plan = Invoke-RestMethod `
        -Uri "$ApiBase/applications/plans" `
        -Method Post `
        -ContentType "application/json" `
        -Body $planBody

    Write-Host ("Plan id: {0}" -f $plan.id)
    Write-Host ("Plan mode: {0}" -f $plan.mode)

    Write-Step "Starting application run"
    $runBody = @{ plan_id = $plan.id } | ConvertTo-Json
    $run = Invoke-RestMethod `
        -Uri "$ApiBase/applications/runs" `
        -Method Post `
        -ContentType "application/json" `
        -Body $runBody

    Write-Host ("Run id: {0}" -f $run.id)
    Write-Host ("Run status: {0}" -f $run.status)

    Write-Step "Fetching dashboard overview"
    $dashboard = Invoke-RestMethod -Uri "$ApiBase/dashboard/overview" -Method Get
    Write-Host ("Dashboard totals: jobs={0}, drafts={1}, applications={2}, pending_approvals={3}" -f `
        $dashboard.totals.jobs, `
        $dashboard.totals.drafts, `
        $dashboard.totals.applications, `
        $dashboard.totals.pending_approvals)

    Write-Host ""
    Write-Host "Smoke test completed." -ForegroundColor Green
    Write-Host "Open http://localhost:5183 to inspect the dashboard."
} finally {
    Pop-Location
}
