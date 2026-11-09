param(
    [string]$RequestPath = "C:\Output\build-request.json"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$outputDirectory = Split-Path -Parent $RequestPath
$successMarker = Join-Path $outputDirectory "build-success.txt"
$errorMarker = Join-Path $outputDirectory "build-error.txt"
$logPath = Join-Path $outputDirectory "sandbox-build.log"
$progressPath = Join-Path $outputDirectory "sandbox-progress.log"

# Step-level progress is appended immediately (the transcript is buffered), so the host can relay it.
function Write-Step([string]$Message) {
    $line = "[sandbox {0:HH:mm:ss}] {1}" -f (Get-Date), $Message
    Write-Host $line
    Add-Content -LiteralPath $progressPath -Value $line -Encoding UTF8
}
$buildRoot = "C:\Build\NTE-auto-fish"
$artifactNames = @()
$errorText = $null
$transcriptStarted = $false

try {
    Start-Transcript -LiteralPath $logPath -Force | Out-Null
    $transcriptStarted = $true
    $request = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
    if ($request.python_version -notmatch '^\d+\.\d+\.\d+$') {
        throw "Invalid Python version: $($request.python_version)"
    }

    Write-Step "Copying the project into the Sandbox"
    New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
    & robocopy.exe "C:\Project" $buildRoot /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Failed to copy the project into the Sandbox (robocopy exit code $LASTEXITCODE)."
    }

    $pythonDirectory = "C:\Python"
    $python = Join-Path $pythonDirectory "python.exe"
    Write-Step "Preparing Python (download on first run)"
    $installerName = "python-$($request.python_version)-amd64.exe"
    $installer = Join-Path "C:\Cache" $installerName
    if (-not (Test-Path -LiteralPath $installer)) {
        $partialInstaller = "$installer.partial"
        $downloadUrl = "https://www.python.org/ftp/python/$($request.python_version)/$installerName"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $partialInstaller
        Move-Item -LiteralPath $partialInstaller -Destination $installer -Force
    }
    $installerSignature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($installerSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "Python installer signature validation failed: $($installerSignature.Status)."
    }

    Write-Step "Installing Python (silent, takes a few minutes)"
    $install = Start-Process -FilePath $installer -ArgumentList @(
        "/quiet",
        "InstallAllUsers=0",
        "TargetDir=$pythonDirectory",
        "Include_pip=1",
        "Include_test=0",
        "PrependPath=0"
    ) -Wait -PassThru
    if ($install.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $python)) {
        throw "Python installation failed with exit code $($install.ExitCode)."
    }

    $env:PIP_CACHE_DIR = "C:\Cache\pip"
    Write-Step "Updating pip"
    & $python -m pip install --disable-pip-version-check --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to update pip." }
    Write-Step "Installing dependencies and PyInstaller (longest step)"
    & $python -m pip install --disable-pip-version-check -r (Join-Path $buildRoot "requirements.txt") pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "Failed to install build dependencies." }

    $buildArguments = @(
        (Join-Path $buildRoot "scripts\build_windows.py"),
        "--app-name", [string]$request.app_name,
        "--icon", [string]$request.icon,
        "--dist-dir", $outputDirectory
    )
    if (-not [string]::IsNullOrWhiteSpace([string]$request.build_id)) {
        $buildArguments += @("--build-id", [string]$request.build_id)
    }

    Write-Step "Building the EXE with PyInstaller"
    Push-Location $buildRoot
    try {
        & $python @buildArguments
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed with exit code $LASTEXITCODE." }
    }
    finally {
        Pop-Location
    }

    Write-Step "Build finished"
    $artifacts = @(Get-ChildItem -LiteralPath $outputDirectory -Filter "*.exe" -File)
    if ($artifacts.Count -eq 0) {
        throw "The build completed without producing an EXE."
    }
    $artifactNames = @($artifacts.Name)
}
catch {
    $errorText = ($_ | Out-String)
}
finally {
    Remove-Item -LiteralPath $RequestPath -Force -ErrorAction SilentlyContinue
    if ($transcriptStarted) {
        Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
    }
    if ($null -eq $errorText) {
        ($artifactNames -join [Environment]::NewLine) | Set-Content -LiteralPath $successMarker -Encoding UTF8
    }
    else {
        $errorText | Set-Content -LiteralPath $errorMarker -Encoding UTF8
    }
    Start-Process -FilePath "shutdown.exe" -ArgumentList "/s", "/t", "3", "/f" -WindowStyle Hidden
}
