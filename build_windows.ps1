$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$compilerCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$compiler = $compilerCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (!$compiler) {
    $compilerCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($compilerCommand) {
        $compiler = $compilerCommand.Source
    }
}
if (!$compiler) {
    throw "Inno Setup 6 is required. Install it with: winget install --id JRSoftware.InnoSetup --exact"
}

$pythonCandidates = @(
    (Join-Path $projectRoot ".venv\Scripts\python.exe"),
    (Join-Path $projectRoot "venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (!$python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (!$pythonCommand) {
        throw "Python was not found. Install Python 3.11 and the requirements-build.txt dependencies."
    }
    $python = $pythonCommand.Source
}

Push-Location $projectRoot
try {
    & $python -m PyInstaller --clean --noconfirm .\CYRUS.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $outputDirectory = Join-Path $projectRoot "dist\CYRUS"
    Copy-Item ".env.example" $outputDirectory -Force
    Copy-Item "config\api_keys.example.json" $outputDirectory -Force
    Copy-Item "README.md" $outputDirectory -Force
    Copy-Item "download_ollama_model.ps1" $outputDirectory -Force
    Copy-Item "download_alan_voice.ps1" $outputDirectory -Force
    New-Item -ItemType Directory -Path (Join-Path $projectRoot "dist\installer") -Force | Out-Null

    & $compiler ".\installer.iss" "/DBuildDir=$outputDirectory"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE."
    }
    $installerPath = Join-Path $projectRoot "dist\installer\CYRUS-Setup.exe"
    if (!(Test-Path $installerPath)) {
        throw "Inno Setup completed without creating $installerPath."
    }

    Write-Output "Portable CYRUS build created at $outputDirectory"
    Write-Output "Windows installer created at $installerPath"
    Write-Output "Keep the portable folder when sharing CYRUS; do not share personal .env or API key files."
}
finally {
    Pop-Location
}
