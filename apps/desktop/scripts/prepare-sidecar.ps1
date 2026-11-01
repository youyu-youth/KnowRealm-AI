$ErrorActionPreference = "Stop"

$backendRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../../../backend"))
$binaryRoot = Join-Path $PSScriptRoot "../src-tauri/binaries"
$buildRoot = Join-Path $backendRoot "build/sidecar"

& uv run --frozen --group build --directory $backendRoot pyinstaller `
    --noconfirm --onedir --name knowrealm-sidecar `
    --distpath $binaryRoot --workpath $buildRoot --specpath $buildRoot `
    --paths $backendRoot --add-data "${backendRoot}/migrations:migrations" `
    --collect-data jieba --collect-data deepagents --collect-data langchain_openai `
    --collect-submodules tiktoken_ext `
    --recursive-copy-metadata deepagents --recursive-copy-metadata langchain-openai `
    --hidden-import app.core.loop `
    (Join-Path $backendRoot "app/server.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$sidecarRoot = Join-Path $binaryRoot "knowrealm-sidecar"
$executable = Join-Path $sidecarRoot "knowrealm-sidecar.exe"
if (-not (Test-Path -LiteralPath $executable) -or
    -not (Test-Path -LiteralPath (Join-Path $sidecarRoot "_internal/migrations/0001_courses.sql"))) {
    throw "Sidecar bundle is missing its executable or database migrations"
}
Copy-Item -LiteralPath $executable `
    -Destination (Join-Path $binaryRoot "knowrealm-sidecar-x86_64-pc-windows-msvc.exe") -Force
