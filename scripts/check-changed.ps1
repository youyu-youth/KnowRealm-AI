#Requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$Base = 'HEAD',
    [switch]$ListOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Read-GitPaths([string[]]$GitArgs) {
    $output = & git -c core.quotepath=false @GitArgs
    if ($LASTEXITCODE -ne 0) { throw '无法收集 Git 改动路径。' }
    (($output -join "`n") -split "`0") | Where-Object { $_ }
}

function Invoke-Check([string]$Directory, [string]$Command, [string[]]$CheckArgs) {
    Write-Host "[$Directory] $Command $($CheckArgs -join ' ')"
    if ($ListOnly) { return }
    Push-Location (Join-Path $repoRoot $Directory)
    try {
        & $Command @CheckArgs
        if ($LASTEXITCODE -ne 0) { throw "$Command 检查失败（退出码 $LASTEXITCODE）。" }
    } finally {
        Pop-Location
    }
}

Push-Location $repoRoot
try {
    & git rev-parse --verify --end-of-options "$Base^{commit}" *> $null
    if ($LASTEXITCODE -ne 0) { throw "基点不存在或不是提交：$Base" }
    $changed = @(
        Read-GitPaths @('diff', '--name-only', '-z', "$Base...HEAD", '--')
        Read-GitPaths @('diff', '--name-only', '-z', 'HEAD', '--')
        Read-GitPaths @('ls-files', '--others', '--exclude-standard', '-z', '--')
    ) | Sort-Object -Unique
    $files = @($changed | Where-Object {
        $path = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $_))
        if (-not $path.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar)) {
            throw "改动路径超出仓库：$_"
        }
        Test-Path -LiteralPath $path -PathType Leaf
    })
    $frontend = @($files | Where-Object { $_ -match '^apps/desktop/.*\.(ts|tsx|js|mjs|json|css)$' })
    $backend = @($files | Where-Object { $_ -match '^backend/.*\.py$' })
    $frontendConfig = @($changed | Where-Object {
        $_ -in @('pnpm-lock.yaml', 'pnpm-workspace.yaml', 'apps/desktop/package.json') -or
        $_ -match '^apps/desktop/(eslint\.config\.|tsconfig|vite\.config\.)'
    })
    $backendConfig = @($changed | Where-Object {
        $_ -in @('backend/pyproject.toml', 'backend/pyrightconfig.json', 'backend/uv.lock')
    })
    $frontendTypes = @($changed | Where-Object { $_ -match '^apps/desktop/.*\.(ts|tsx)$|^packages/api-types/' })
    $deletedPython = @($changed | Where-Object { $_ -match '^backend/.*\.py$' -and $_ -notin $files })
    if ($frontend.Count + $backend.Count + $frontendConfig.Count + $backendConfig.Count + $frontendTypes.Count + $deletedPython.Count -eq 0) {
        Write-Host '没有适用的前端或后端检查文件；未调用检查器。'
        return
    }
    Write-Host "检查范围（基点 $Base + 暂存/工作区/未跟踪文件）："
    $files | ForEach-Object { Write-Host "  $_" }
    if ($frontendConfig.Count -gt 0) {
        Invoke-Check 'apps/desktop' 'pnpm' @('lint')
        Invoke-Check 'apps/desktop' 'pnpm' @('exec', 'prettier', '--check', '--end-of-line', 'auto', 'src')
    } elseif ($frontend.Count -gt 0) {
        $lintFiles = @($frontend | Where-Object { $_ -match '\.(ts|tsx|js|mjs)$' } | ForEach-Object { './' + $_.Substring(13) })
        if ($lintFiles.Count -gt 0) {
            Invoke-Check 'apps/desktop' 'pnpm' (@('exec', 'eslint', '--max-warnings', '0') + $lintFiles)
        }
        $formatFiles = @($frontend | ForEach-Object { './' + $_.Substring(13) })
        Invoke-Check 'apps/desktop' 'pnpm' (@('exec', 'prettier', '--check', '--end-of-line', 'auto') + $formatFiles)
    }
    if ($frontend.Count -gt 0 -or $frontendConfig.Count -gt 0 -or $frontendTypes.Count -gt 0) {
        Invoke-Check 'apps/desktop' 'pnpm' @('build')
    }
    if ($backendConfig.Count -gt 0) {
        Invoke-Check 'backend' 'uv' @('run', '--frozen', 'ruff', 'check', '.')
        Invoke-Check 'backend' 'uv' @('run', '--frozen', 'ruff', 'format', '--check', '.')
        Invoke-Check 'backend' 'uv' @('run', '--frozen', 'pyright')
    } elseif ($backend.Count -gt 0) {
        $pythonFiles = @($backend | ForEach-Object { './' + $_.Substring(8) })
        Invoke-Check 'backend' 'uv' (@('run', '--frozen', 'ruff', 'check') + $pythonFiles)
        Invoke-Check 'backend' 'uv' (@('run', '--frozen', 'ruff', 'format', '--check') + $pythonFiles)
        Invoke-Check 'backend' 'uv' (@('run', '--frozen', 'pyright') + $pythonFiles)
    }
    if ($deletedPython.Count -gt 0 -and $backendConfig.Count -eq 0) {
        Invoke-Check 'backend' 'uv' @('run', '--frozen', 'pyright')
    }
} finally {
    Pop-Location
}
