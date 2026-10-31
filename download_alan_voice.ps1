param(
    [string]$VoiceDirectory = (Join-Path $env:LOCALAPPDATA "CYRUS\voices")
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$modelName = "en_GB-alan-medium.onnx"
$configName = "$modelName.json"
$modelUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/$modelName?download=true"
$configUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/$configName?download=true"
$expectedModelSha256 = "0a309668932205e762801f1efc2736cd4b0120329622adf62be09e56339d3330"

Write-Output "This downloads the Alan voice files directly from the Hugging Face model host."
Write-Output "The upstream model card points to a source marked All Rights Reserved."
Write-Output "Review the model card and source terms before continuing:"
Write-Output "https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/alan/medium"
if ((Read-Host "Continue with the optional 63 MB download? (Y/N)") -notmatch "^(y|yes)$") {
    Write-Output "Download cancelled."
    exit 0
}

$modelPath = Join-Path $VoiceDirectory $modelName
$configPath = Join-Path $VoiceDirectory $configName
if ((Test-Path $modelPath) -and (Test-Path $configPath)) {
    Write-Output "Both Alan voice files are already installed in $VoiceDirectory."
    exit 0
}

$temporaryDirectory = Join-Path $env:TEMP "CYRUS-AlanVoice-$PID"
New-Item -ItemType Directory -Path $temporaryDirectory -Force | Out-Null
try {
    $temporaryModel = Join-Path $temporaryDirectory $modelName
    $temporaryConfig = Join-Path $temporaryDirectory $configName
    Invoke-WebRequest -Uri $modelUrl -OutFile $temporaryModel -MaximumRedirection 10 -TimeoutSec 900
    Invoke-WebRequest -Uri $configUrl -OutFile $temporaryConfig -MaximumRedirection 10 -TimeoutSec 120

    $actualModelSha256 = (Get-FileHash -Path $temporaryModel -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualModelSha256 -ne $expectedModelSha256) {
        throw "The downloaded Alan voice model failed its SHA-256 integrity check."
    }

    $voiceConfig = Get-Content -Path $temporaryConfig -Raw | ConvertFrom-Json
    if ($voiceConfig.language.code -ne "en_GB" -or $voiceConfig.dataset -ne "alan") {
        throw "The downloaded voice configuration did not match the expected Alan en_GB voice."
    }

    New-Item -ItemType Directory -Path $VoiceDirectory -Force | Out-Null
    Move-Item -Path $temporaryModel -Destination $modelPath -Force
    Move-Item -Path $temporaryConfig -Destination $configPath -Force
    Write-Output "Alan voice files were downloaded and verified in $VoiceDirectory."
    Write-Output "Restart CYRUS to use the voice."
}
finally {
    if (Test-Path $temporaryDirectory) {
        Remove-Item -Path $temporaryDirectory -Recurse -Force
    }
}
