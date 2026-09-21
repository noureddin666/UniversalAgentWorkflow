param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,

    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $PSScriptRoot
$templateRoot = Join-Path $packageRoot 'template'
$resolvedProject = Resolve-Path -LiteralPath $ProjectPath
$agentTarget = Join-Path $resolvedProject '.agent'
$vendorTarget = Join-Path $agentTarget 'vendor\universal-agent-workflow'
$agentsTarget = Join-Path $resolvedProject 'AGENTS.md'

if ((Test-Path -LiteralPath $agentsTarget) -and -not $Force) {
    throw "AGENTS.md already exists at $resolvedProject. Re-run with -Force only if replacement is intended."
}

if ((Test-Path -LiteralPath $agentTarget) -and -not $Force) {
    throw ".agent already exists at $resolvedProject. Re-run with -Force only if replacement is intended."
}

New-Item -ItemType Directory -Path $agentTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $templateRoot 'AGENTS.md') -Destination $agentsTarget -Force:$Force
Copy-Item -Path (Join-Path $templateRoot '.agent\*') -Destination $agentTarget -Recurse -Force:$Force
New-Item -ItemType Directory -Path $vendorTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $packageRoot 'core') -Destination $vendorTarget -Recurse -Force
Copy-Item -LiteralPath (Join-Path $packageRoot 'workflows') -Destination $vendorTarget -Recurse -Force
Copy-Item -LiteralPath (Join-Path $packageRoot 'profiles') -Destination $vendorTarget -Recurse -Force
Copy-Item -LiteralPath (Join-Path $packageRoot 'tooling') -Destination $vendorTarget -Recurse -Force
Get-ChildItem -LiteralPath (Join-Path $vendorTarget 'tooling') -Recurse -Force -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force
Copy-Item -LiteralPath (Join-Path $packageRoot 'VERSION') -Destination $vendorTarget -Force
Copy-Item -LiteralPath (Join-Path $packageRoot 'LICENSE') -Destination $vendorTarget -Force
Copy-Item -LiteralPath (Join-Path $packageRoot 'MANUAL.md') -Destination $vendorTarget -Force
Copy-Item -LiteralPath (Join-Path $packageRoot 'GUIDE.ar.md') -Destination $vendorTarget -Force

$githubWorkflows = Join-Path $resolvedProject '.github\workflows'
New-Item -ItemType Directory -Path $githubWorkflows -Force | Out-Null
$workflowTarget = Join-Path $githubWorkflows 'agent-workflow.yml'
if (-not (Test-Path -LiteralPath $workflowTarget)) {
    Copy-Item -LiteralPath (Join-Path $templateRoot '.github\workflows\agent-workflow.yml') -Destination $workflowTarget
}

Write-Host "Installed Universal Agent Workflow into $resolvedProject"
Write-Host "Next: cd $resolvedProject"
Write-Host '      .agent\workflow.cmd setup --ask   (fills what the repository proves, asks you the rest)'
Write-Host 'Optional: .agent\workflow.cmd install-hooks   (keep .agent/INDEX.json current)'
