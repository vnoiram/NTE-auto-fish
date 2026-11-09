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
    $installLog = Join-Path $outputDirectory "python-install.log"
    $install = Start-Process -FilePath $installer -ArgumentList @(
        "/quiet",
        "/log", $installLog,
        "InstallAllUsers=0",
        "TargetDir=$pythonDirectory",
        "Include_pip=0",
        "Include_test=0",
        "Include_doc=0",
        "Include_launcher=0",
        "Include_dev=0",
        "Include_symbols=0",
        "Include_debug=0",
        "PrependPath=0"
    ) -PassThru
    # Poll instead of -Wait so a stalled installer is reported and eventually aborted.
    $installTimeoutSeconds = 600
    $installWatch = [System.Diagnostics.Stopwatch]::StartNew()
    while (-not $install.WaitForExit(30000)) {
        $lastLine = ""
        if (Test-Path -LiteralPath $installLog) {
            $lastLine = (Get-Content -LiteralPath $installLog -Tail 1 -ErrorAction SilentlyContinue)
        }
        Write-Step ("Python installer still running ({0}s): {1}" -f [int]$installWatch.Elapsed.TotalSeconds, $lastLine)
        # Show who else is using Windows Installer (only one MSI can run at a time).
        $msi = @(Get-CimInstance Win32_Process -Filter "Name='msiexec.exe'" -ErrorAction SilentlyContinue |
            ForEach-Object { "pid=$($_.ProcessId) cmd=$($_.CommandLine)" })
        Write-Step ("  msiexec processes: {0}" -f $(if ($msi.Count) { $msi -join " | " } else { "none" }))
        if ($installWatch.Elapsed.TotalSeconds -gt $installTimeoutSeconds) {
            Get-Process -Name "python-*" -ErrorAction SilentlyContinue | Stop-Process -Force
            throw "Python installer did not finish within $installTimeoutSeconds seconds. See python-install.log."
        }
    }
    if ($install.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $python)) {
        throw "Python installation failed with exit code $($install.ExitCode). See python-install.log."
    }

    # The installer's pip MSI can stall in the Sandbox, so bootstrap pip directly where output is visible.
    Write-Step "Bootstrapping pip (ensurepip)"
    $ensure = Start-Process -FilePath $python -ArgumentList @("-m", "ensurepip", "--default-pip") `
        -NoNewWindow -PassThru
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
