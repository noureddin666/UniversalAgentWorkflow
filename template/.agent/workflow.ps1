$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'workflow.py'
foreach ($candidate in @($env:UAW_PYTHON, 'python', 'python3', 'py')) {
  if (-not $candidate) { continue }
  if (Get-Command $candidate -ErrorAction SilentlyContinue) {
    & $candidate $script @args
    exit $LASTEXITCODE
  }
}
Write-Error 'No Python interpreter found; set UAW_PYTHON to one.'
exit 127
