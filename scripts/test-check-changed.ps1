#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$originalLocation = (Get-Location).Path
$fixtureParent = Split-Path -Parent $PSScriptRoot
$fixtureRoot = Join-Path $fixtureParent ('.pytest-tmp-check-script-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path (Join-Path $fixtureRoot 'scripts'), (Join-Path $fixtureRoot 'backend'), (Join-Path $fixtureRoot 'apps/desktop/src') | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'check-changed.ps1') -Destination (Join-Path $fixtureRoot 'scripts/check-changed.ps1')

function Assert-Result([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Invoke-Git([string[]]$GitArgs) {
    & git @GitArgs *> $null
    if ($LASTEXITCODE -ne 0) { throw "fixture Git 失败：$($GitArgs -join ' ')" }
}

Push-Location $fixtureRoot
try {
    Invoke-Git @('init')
    Invoke-Git @('config', 'user.name', 'Check fixture')
    Invoke-Git @('config', 'user.email', 'fixture@example.invalid')
    Set-Content -LiteralPath README.md -Value 'fixture'
    Invoke-Git @('add', '.')
    Invoke-Git @('commit', '-m', 'fixture')
    $initial = & git rev-parse HEAD
    $output = (& pwsh -NoProfile -File scripts/check-changed.ps1 -ListOnly *>&1) -join "`n"
    Assert-Result ($LASTEXITCODE -eq 0 -and $output.Contains('未调用检查器')) '空改动必须停止，不能扩大到全仓。'

    Set-Content -LiteralPath 'backend/中文 名称.py' -Value 'value = 1'
    Set-Content -LiteralPath 'apps/desktop/src/sample.ts' -Value 'export const value = 1;'
    Invoke-Git @('add', 'backend')
    $output = (& pwsh -NoProfile -File scripts/check-changed.ps1 -ListOnly *>&1) -join "`n"
    Assert-Result ($LASTEXITCODE -eq 0 -and $output.Contains('./中文 名称.py') -and $output.Contains('./src/sample.ts')) '暂存/未跟踪路径必须完整保留空格和中文。'
    Assert-Result ($output.Contains('ruff check ./中文 名称.py') -and $output.Contains('pnpm build')) '检查器必须收到明确范围。'
    Invoke-Git @('add', '.')
    Invoke-Git @('commit', '-m', 'sources')
    Push-Location backend
    try {
        $output = (& pwsh -NoProfile -File ../scripts/check-changed.ps1 -Base $initial -ListOnly *>&1) -join "`n"
        Assert-Result ($LASTEXITCODE -eq 0 -and $output.Contains('./中文 名称.py')) '从子目录调用仍须相对仓库根收集提交差异。'
    } finally { Pop-Location }

    $output = (& pwsh -NoProfile -File scripts/check-changed.ps1 -Base 'missing-ref' -ListOnly *>&1) -join "`n"
    Assert-Result ($LASTEXITCODE -ne 0 -and -not $output.Contains('ruff check')) '无效基点必须失败，不能触发检查器。'

    Invoke-Git @('rm', 'apps/desktop/src/sample.ts')
    $output = (& pwsh -NoProfile -File scripts/check-changed.ps1 -ListOnly *>&1) -join "`n"
    Assert-Result ($LASTEXITCODE -eq 0 -and $output.Contains('pnpm build') -and -not $output.Contains('eslint')) '仅删除文件时仍须检查类型，不能给 ESLint 传空清单。'

    Invoke-Git @('restore', '--staged', '--worktree', 'apps/desktop/src/sample.ts')
    New-Item -ItemType Directory -Path 'packages/api-types' | Out-Null
    Set-Content -LiteralPath 'packages/api-types/schema.d.ts' -Value 'export type Value = string;'
    $output = (& pwsh -NoProfile -File scripts/check-changed.ps1 -ListOnly *>&1) -join "`n"
    Assert-Result ($LASTEXITCODE -eq 0 -and $output.Contains('pnpm build')) '仅改 API 类型也必须检查前端消费。'
    Invoke-Git @('add', '.')
    Invoke-Git @('commit', '-m', 'contract')
    Set-Content -LiteralPath 'backend/pyproject.toml' -Value '[project]'
    $output = (& pwsh -NoProfile -File scripts/check-changed.ps1 -ListOnly *>&1) -join "`n"
    Assert-Result ($LASTEXITCODE -eq 0 -and $output.Contains('ruff check .')) '配置变化必须显式检查整个域。'
    Invoke-Git @('add', '.')
    Invoke-Git @('commit', '-m', 'config')
    Invoke-Git @('rm', 'backend/中文 名称.py')
    $output = (& pwsh -NoProfile -File scripts/check-changed.ps1 -ListOnly *>&1) -join "`n"
    Assert-Result ($LASTEXITCODE -eq 0 -and $output.Contains('pyright') -and -not $output.Contains('ruff check')) '仅删除 Python 文件时检查类型，不向 Ruff 传空清单。'
    Invoke-Git @('restore', '--staged', '--worktree', 'backend/中文 名称.py')
    Set-Content -LiteralPath 'backend/中文 名称.py' -Value 'value = 2'
    $shimDirectory = Join-Path $fixtureRoot 'bin'
    New-Item -ItemType Directory -Path $shimDirectory | Out-Null
    Set-Content -LiteralPath (Join-Path $shimDirectory 'uv.cmd') -Value '@exit /b 9'
    $originalPath = $env:PATH
    try {
        $env:PATH = $shimDirectory + [System.IO.Path]::PathSeparator + $originalPath
        $output = (& pwsh -NoProfile -File scripts/check-changed.ps1 *>&1) -join "`n"
        Assert-Result ($LASTEXITCODE -ne 0 -and $output.Contains('退出码 9')) '原生命令失败必须传播，不能被后续命令覆盖。'
    } finally { $env:PATH = $originalPath }
    Write-Host '9 项检查脚本自检通过。'
} catch {
    Write-Host $_.Exception.Message
    throw
} finally {
    Pop-Location
    Set-Location -LiteralPath $originalLocation
    $resolvedFixture = [System.IO.Path]::GetFullPath($fixtureRoot)
    $expectedPrefix = Join-Path $fixtureParent '.pytest-tmp-check-script-'
    if (-not $resolvedFixture.StartsWith($expectedPrefix)) { throw 'fixture 清理路径失配。' }
    try {
        Remove-Item -LiteralPath $resolvedFixture -Recurse -Force
    } catch {
        Write-Warning "自检 fixture 未清理：$resolvedFixture；$($_.Exception.Message)"
    }
}
exit 0
