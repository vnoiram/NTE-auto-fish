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
$completed = $false

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
    # The NuGet package is a plain archive: no Windows Installer, which can stall in the Sandbox.
    # It does not ship tkinter, so the scanning area editor is disabled in the built EXE.
    Write-Step "Preparing Python (download on first run)"
    $packageName = "python.$($request.python_version).zip"
    $package = Join-Path "C:\Cache" $packageName
    if (-not (Test-Path -LiteralPath $package)) {
        $partialPackage = "$package.partial"
        $downloadUrl = "https://www.nuget.org/api/v2/package/python/$($request.python_version)"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $partialPackage
        Move-Item -LiteralPath $partialPackage -Destination $package -Force
    }

    Write-Step "Extracting Python"
    $extractDirectory = "C:\PythonPackage"
    Remove-Item -LiteralPath $extractDirectory -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -LiteralPath $package -DestinationPath $extractDirectory -Force
    Move-Item -LiteralPath (Join-Path $extractDirectory "tools") -Destination $pythonDirectory -Force
    if (-not (Test-Path -LiteralPath $python)) {
        throw "python.exe was not found in the extracted Python package."
    }

    # The package ships ensurepip but no pip; bootstrap it with a timeout.
    Write-Step "Bootstrapping pip (ensurepip)"
    $ensure = Start-Process -FilePath $python -ArgumentList @("-m", "ensurepip", "--default-pip") `
        -NoNewWindow -PassThru
    # Touch Handle so ExitCode stays available after WaitForExit (otherwise it can be empty).
    $null = $ensure.Handle
    if (-not $ensure.WaitForExit(180000)) {
        $ensure | Stop-Process -Force
        throw "ensurepip did not finish within 180 seconds."
    }
    if ($ensure.ExitCode -ne 0) { throw "ensurepip failed with exit code $($ensure.ExitCode)." }

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
    $completed = $true
}
catch {
    $errorText = ($_ | Out-String)
}
finally {
    # Keep the request after a failure or interruption so the script can be run again in the same Sandbox.
    if ($completed) {
        Remove-Item -LiteralPath $RequestPath -Force -ErrorAction SilentlyContinue
    }
    if ($transcriptStarted) {
        Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
    }
    if ($completed) {
        ($artifactNames -join [Environment]::NewLine) | Set-Content -LiteralPath $successMarker -Encoding UTF8
    }
    else {
        if ($null -eq $errorText) { $errorText = "The build was interrupted before it finished." }
        $errorText | Set-Content -LiteralPath $errorMarker -Encoding UTF8
    }
    Start-Process -FilePath "shutdown.exe" -ArgumentList "/s", "/t", "3", "/f" -WindowStyle Hidden
}
