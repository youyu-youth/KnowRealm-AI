$ErrorActionPreference = "Stop"

# 月末构建保留两年；普通每日构建仅保留 14 天。
$archiveName = "ffmpeg-n8.1.2-50-g1a748fe2cd-win64-lgpl-shared-8.1.zip"
$archiveSha256 = "e9712ffbdb03ef71bbab660c75b835bfe698ef6fad0247c76d8d394a39a3db63"
$releaseUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-08-31-13-27/$archiveName"
$desktopRoot = Split-Path -Parent $PSScriptRoot
$binaryRoot = Join-Path $desktopRoot "src-tauri\binaries"
$runtimeRoot = Join-Path $binaryRoot "ffmpeg-runtime"
$targetExe = Join-Path $binaryRoot "ffmpeg-x86_64-pc-windows-msvc.exe"
$sourceMarker = Join-Path $runtimeRoot "SOURCE.txt"

if (
    (Test-Path -LiteralPath $targetExe) -and
    (Test-Path -LiteralPath $sourceMarker) -and
    $null -ne (Get-ChildItem -LiteralPath $binaryRoot -File -Filter "*.dll" -ErrorAction SilentlyContinue | Select-Object -First 1)
) {
    $installedSource = Get-Content -LiteralPath $sourceMarker -Raw
    if ($installedSource.Contains($archiveSha256)) {
        exit 0
    }
}

$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("knowrealm-ffmpeg-" + [guid]::NewGuid())
$archivePath = Join-Path $temporaryRoot $archiveName
$extractRoot = Join-Path $temporaryRoot "extracted"
New-Item -ItemType Directory -Path $temporaryRoot, $extractRoot -Force | Out-Null

try {
    Invoke-WebRequest -Uri $releaseUrl -OutFile $archivePath -UseBasicParsing
    $actualSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $archiveSha256) {
        throw "FFmpeg archive checksum mismatch: $actualSha256"
    }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot
    $ffmpeg = Get-ChildItem -LiteralPath $extractRoot -Recurse -File -Filter "ffmpeg.exe" | Select-Object -First 1
    $license = Get-ChildItem -LiteralPath $extractRoot -Recurse -File -Filter "LICENSE.txt" | Select-Object -First 1
    if ($null -eq $ffmpeg -or $null -eq $license) {
        throw "FFmpeg archive is missing ffmpeg.exe or LICENSE.txt"
    }
    $dlls = Get-ChildItem -LiteralPath $ffmpeg.DirectoryName -File -Filter "*.dll"
    if ($dlls.Count -eq 0) {
        throw "FFmpeg shared archive contains no runtime DLLs"
    }

    New-Item -ItemType Directory -Path $binaryRoot, $runtimeRoot -Force | Out-Null
    Copy-Item -LiteralPath $ffmpeg.FullName -Destination $targetExe -Force
    foreach ($dll in $dlls) {
        Copy-Item -LiteralPath $dll.FullName -Destination $binaryRoot -Force
    }
    Copy-Item -LiteralPath $license.FullName -Destination (Join-Path $runtimeRoot "LICENSE.txt") -Force
    @(
        "source=$releaseUrl"
        "archive_sha256=$archiveSha256"
        "upstream_commit=8267213e26c1031621e6e1210fe3aa4867214f6a"
        "ffmpeg_version=n8.1.2-50-g1a748fe2cd"
        "variant=win64-lgpl-shared-8.1"
    ) | Set-Content -LiteralPath $sourceMarker -Encoding utf8
}
finally {
    $resolvedTemporaryRoot = [System.IO.Path]::GetFullPath($temporaryRoot)
    $resolvedSystemTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    if ($resolvedTemporaryRoot.StartsWith($resolvedSystemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
