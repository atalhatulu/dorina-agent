# Dorina Agent — Windows tek komut kurulumu
# Usage: iex (irm https://raw.githubusercontent.com/atalhatulu/dorina-agent/main/scripts/install.ps1)

$Repo = "https://github.com/atalhatulu/dorina-agent"
$InstallDir = "$env:USERPROFILE\.dorina"
$BinDir = "$env:USERPROFILE\.local\bin"
$PythonCmd = "python"

Write-Host "==> Dorina Agent kuruluyor..." -ForegroundColor Cyan

# 1. Python kontrol
try {
    $PyVer = & $PythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    Write-Host "  Python $PyVer ✓"
} catch {
    Write-Host "HATA: Python bulunamadi. Python 3.10+ kurun:" -ForegroundColor Red
    Write-Host "  https://www.python.org/downloads/"
    exit 1
}

# 2. Git kontrol
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "HATA: git bulunamadi. Git indirin:" -ForegroundColor Red
    Write-Host "  https://git-scm.com/downloads"
    exit 1
}

# 3. Projeyi indir
$TmpDir = [System.IO.Path]::GetTempPath() + [System.IO.Path]::GetRandomFileName()
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null
Write-Host "==> Proje indiriliyor..."
git clone --depth 1 $Repo $TmpDir 2>&1 | Out-Null
if (-not (Test-Path "$TmpDir\main.py")) {
    Write-Host "HATA: Proje indirilemedi." -ForegroundColor Red
    Remove-Item -Recurse -Force $TmpDir -ErrorAction SilentlyContinue
    exit 1
}

# 4. Sanal ortam
Write-Host "==> Sanal ortam hazirlaniyor..."
& $PythonCmd -m venv "$InstallDir\venv"
& "$InstallDir\venv\Scripts\pip" install --quiet --upgrade pip 2>$null
& "$InstallDir\venv\Scripts\pip" install --quiet -r "$TmpDir\requirements.txt" 2>$null

# 5. Config
if (-not (Test-Path "$InstallDir\config.yaml")) {
    Copy-Item "$TmpDir\config.yaml.example" "$InstallDir\config.yaml"
    Write-Host "  Config: $InstallDir\config.yaml"
}

# 6. PATH'e ekle
New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
$BatContent = @"
@echo off
"%USERPROFILE%\.dorina\venv\Scripts\python" -m main %*
"@
Set-Content -Path "$BinDir\dorina.bat" -Value $BatContent

$CurrentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($CurrentPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$CurrentPath;$BinDir", "User")
    Write-Host "  PATH eklendi: $BinDir"
    Write-Host "  Terminali yeniden baslat veya 'refreshenv' yap."
}

# 7. Temizlik
Remove-Item -Recurse -Force $TmpDir -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "==> Dorina Agent kuruldu! 🚀" -ForegroundColor Green
Write-Host ""
Write-Host "  Kullanmak icin: dorina"
Write-Host "  API key eklemek icin: $InstallDir\keys.json"
Write-Host "  Config: $InstallDir\config.yaml"
