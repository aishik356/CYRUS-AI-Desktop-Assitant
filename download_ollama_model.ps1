$ErrorActionPreference = "Stop"

$ollama = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
if ($ollama) {
    $ollamaPath = $ollama.Source
}
else {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Ollama\ollama.exe")
    )
    $ollamaPath = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

if (!$ollamaPath) {
    Write-Output "Ollama is not installed. Install it from https://ollama.com/download/windows, then run this script again."
    Start-Process "https://ollama.com/download/windows"
    Read-Host "Press Enter to close"
    exit 1
}

Write-Output "Downloading the CYRUS local AI model. This may take several gigabytes."
& $ollamaPath pull "llama3.2:3b"
if ($LASTEXITCODE -ne 0) {
    throw "Ollama could not download llama3.2:3b (exit code $LASTEXITCODE)."
}

Write-Output "The CYRUS local AI model is ready."
Read-Host "Press Enter to close"
