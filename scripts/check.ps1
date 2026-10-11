# Local quality gate. Run before every commit. No CI runs in the cloud.
# Each step must exit 0 on its own; the script stops at the first failure.
$ErrorActionPreference = "Stop"

$steps = @(
    "ruff format --check .",
    "ruff check .",
    "mypy --strict src tests",
    "pytest"
)
foreach ($step in $steps) {
    $words = $step -split " "
    $rest = @($words | Select-Object -Skip 1)
    & $words[0] @rest
    if ($LASTEXITCODE -ne 0) {
        Write-Error "failed: $step"
        exit $LASTEXITCODE
    }
}
