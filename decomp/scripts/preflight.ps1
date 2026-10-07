# Native Windows preflight for environments where Python is not yet available.
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Get-Executable([string[]] $Names) {
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            $path = $cmd.Source
            if ($path -and $path -notmatch "\\WindowsApps\\") {
                return $path
            }
        }
    }
    return $null
}

$python = Get-Executable @("py", "python", "python3")
$git = Get-Executable @("git", "git.exe")
$ninja = Get-Executable @("ninja", "ninja.exe")
$objdiff = Get-Executable @("objdiff", "objdiff.exe")
$objdiffCli = Get-Executable @("objdiff-cli", "objdiff-cli.exe")
$pwsh = Get-Executable @("pwsh", "pwsh.exe")
$powershell = Get-Executable @("powershell", "powershell.exe")

$inputProject = if ($args.Count -gt 0) { $args[0] } else { "." }
$resolvedProject = Resolve-Path $inputProject -ErrorAction SilentlyContinue
if (-not $resolvedProject) {
    [ordered]@{
        format = "decomp-preflight-windows-v1"
        status = "blocked"
        project = [ordered]@{ path = $inputProject; exists = $false }
        blockers = @("Target project does not exist: $inputProject")
    } | ConvertTo-Json -Depth 6
    exit 1
}
$project = $resolvedProject.Path
$required = @(
    (Join-Path $project "objdiff.json"),
    (Join-Path $project "build.ninja"),
    (Join-Path $project "tools\configure.py")
)

$missing = @($required | Where-Object { -not (Test-Path $_) })

$result = [ordered]@{
    format = "decomp-preflight-windows-v1"
    platform = [ordered]@{
        os = "windows"
        powershell = $powershell
        pwsh = $pwsh
    }
    tools = [ordered]@{
        python = $python
        git = $git
        ninja = $ninja
        objdiff = $objdiff
        objdiff_cli = $objdiffCli
    }
    project = [ordered]@{
        path = $project
        required_files = $required
        missing_files = $missing
    }
    status = if ($python -and $missing.Count -eq 0) { "ready" } else { "blocked" }
    blockers = @(
        $(if (-not $python) { "No usable Python interpreter found (check py, python or python3)." })
        $(if ($missing.Count -gt 0) { "Missing project files: " + ($missing -join ", ") })
    )
}

$result | ConvertTo-Json -Depth 6
if ($result.status -eq "blocked") { exit 1 } else { exit 0 }
