param(
    [ValidateNotNullOrEmpty()]
    [string]$AppName = "NTE Auto-Fish",

    [ValidateNotNullOrEmpty()]
    [string]$Icon = "random",

    [string]$BuildId = "",

    [string]$OutputDirectory = "",

    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$PythonVersion = "3.14.10",

    [ValidateRange(5, 120)]
    [int]$TimeoutMinutes = 45,

    [switch]$Manual
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repoRoot "dist\sandbox"
}
elseif (-not [IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $repoRoot $OutputDirectory
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$sandboxCommand = Get-Command "WindowsSandbox.exe" -ErrorAction SilentlyContinue
if ($null -eq $sandboxCommand) {
    throw "Windows Sandbox is not installed. Enable 'Windows Sandbox' in Windows Features and restart Windows."
}

$temporaryRoot = Join-Path $env:TEMP ("nte-auto-fish-build-" + [guid]::NewGuid().ToString("N"))
$stagedSource = Join-Path $temporaryRoot "source"
$stagedOutput = Join-Path $temporaryRoot "output"
$cacheDirectory = Join-Path $env:LOCALAPPDATA "NTEAutoFish\SandboxCache"
$configurationPath = Join-Path $temporaryRoot "build.wsb"
$sandboxProcess = $null

function Wait-SandboxExit {
    param([int]$Seconds = 60)
    $limit = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $limit) {
        $running = @(Get-Process -Name "WindowsSandbox", "WindowsSandboxClient", "WindowsSandboxRemoteSession" -ErrorAction SilentlyContinue)
        if ($running.Count -eq 0) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

try {
    New-Item -ItemType Directory -Force -Path $stagedSource, $stagedOutput, $cacheDirectory | Out-Null
    $copyArguments = @(
        $repoRoot,
        $stagedSource,
        "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
        "/XD", ".git", ".venv", ".serena", "build", "dist", "__pycache__"
    )
    & robocopy.exe @copyArguments | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Failed to stage the project (robocopy exit code $LASTEXITCODE)."
    }

    [ordered]@{
        app_name = $AppName
        icon = $Icon
        build_id = $BuildId
        python_version = $PythonVersion
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stagedOutput "build-request.json") -Encoding UTF8

    $escapedSource = [Security.SecurityElement]::Escape($stagedSource)
    $escapedOutput = [Security.SecurityElement]::Escape($stagedOutput)
    $escapedCache = [Security.SecurityElement]::Escape($cacheDirectory)
    $guestBuildCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Project\scripts\build_in_windows_sandbox.ps1"
    if ($Manual) {
        $clipboardRedirection = "Enable"
        $logonCommand = ""
    }
    else {
        $clipboardRedirection = "Disable"
        $logonCommand = @"
  <LogonCommand>
    <Command>$guestBuildCommand</Command>
  </LogonCommand>
"@
    }
    $configuration = @"
<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Enable</Networking>
  <ClipboardRedirection>$clipboardRedirection</ClipboardRedirection>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$escapedSource</HostFolder>
      <SandboxFolder>C:\Project</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$escapedOutput</HostFolder>
      <SandboxFolder>C:\Output</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$escapedCache</HostFolder>
      <SandboxFolder>C:\Cache</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
$logonCommand
</Configuration>
"@
    $configuration | Set-Content -LiteralPath $configurationPath -Encoding UTF8

    Write-Host ("Starting Windows Sandbox build... (mode: " + $(if ($Manual) { "manual" } else { "automatic" }) + ")")
    Write-Host "The first build downloads Python and dependencies; later builds reuse the local download cache."
    if ($Manual) {
        Write-Host ""
        Write-Host "Manual mode: Windows Sandbox is NOT started automatically."
        Write-Host "1. Start Windows Sandbox by opening this file (double-click it in Explorer):"
        Write-Host $configurationPath -ForegroundColor Cyan
        Write-Host "2. Open PowerShell inside Windows Sandbox and run this command:"
        Write-Host $guestBuildCommand -ForegroundColor Cyan
        Write-Host "This script keeps waiting (up to $TimeoutMinutes minutes) and collects the EXE when the build finishes."
        Write-Host ""
        try {
            Set-Clipboard -Value $guestBuildCommand
            Write-Host "(The command was copied to the clipboard; paste it with Ctrl+V inside the Sandbox.)"
        }
        catch {
            # Clipboard access is a convenience only.
        }
    }
    else {
        $sandboxProcess = Start-Process -FilePath $sandboxCommand.Source -ArgumentList "`"$configurationPath`"" -PassThru
    }
    $successMarker = Join-Path $stagedOutput "build-success.txt"
    $errorMarker = Join-Path $stagedOutput "build-error.txt"
    $deadline = [DateTime]::UtcNow.AddMinutes($TimeoutMinutes)
    $startedAt = [DateTime]::UtcNow
    $sessionSeen = $false
    $liveLog = Join-Path $stagedOutput "sandbox-build.log"
    $logOffset = 0L
    $lastNotice = [DateTime]::UtcNow
    $logSeen = $false

    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $successMarker) { break }
        if (Test-Path -LiteralPath $errorMarker) {
            Write-Host "[host] Build failed inside the Sandbox. Collecting logs..."
            [void](Wait-SandboxExit -Seconds 30)
            Copy-Item -LiteralPath $errorMarker -Destination $OutputDirectory -Force
            $sandboxLog = Join-Path $stagedOutput "sandbox-build.log"
            if (Test-Path -LiteralPath $sandboxLog) {
                Copy-Item -LiteralPath $sandboxLog -Destination $OutputDirectory -Force
            }
            throw (Get-Content -LiteralPath $errorMarker -Raw)
        }
        if ($null -ne $sandboxProcess -and $sandboxProcess.HasExited) {
            # WindowsSandbox.exe can be a short-lived launcher, so also check the Sandbox session processes.
            $sessionProcesses = @(Get-Process -Name "WindowsSandboxClient", "WindowsSandboxRemoteSession" -ErrorAction SilentlyContinue)
            if ($sessionProcesses.Count -eq 0) {
                if ($sessionSeen -or ([DateTime]::UtcNow - $startedAt).TotalSeconds -gt 60) {
                    throw "Windows Sandbox closed before the build completed."
                }
            }
            else {
                $sessionSeen = $true
            }
        }
        # Relay new Sandbox log output so progress is visible on the host.
        if (Test-Path -LiteralPath $liveLog) {
            try {
                $stream = [IO.File]::Open($liveLog, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
                try {
                    if ($stream.Length -gt $logOffset) {
                        [void]$stream.Seek($logOffset, [IO.SeekOrigin]::Begin)
                        $reader = New-Object IO.StreamReader($stream)
                        $chunk = $reader.ReadToEnd()
                        $logOffset = $stream.Position
                        if ($chunk.Length -gt 0) { Write-Host $chunk -NoNewline }
                        $logSeen = $true
                        $lastNotice = [DateTime]::UtcNow
                    }
                }
                finally { $stream.Dispose() }
            }
            catch { }
        }
        if (([DateTime]::UtcNow - $lastNotice).TotalSeconds -ge 15) {
            $elapsed = [int]([DateTime]::UtcNow - $startedAt).TotalSeconds
            if ($logSeen) {
                Write-Host "[host] Build in progress in the Sandbox... (${elapsed}s elapsed)"
            }
            else {
                Write-Host "[host] Waiting for the build to start in the Sandbox (no output yet, ${elapsed}s elapsed). Run the printed command inside the Sandbox."
            }
            $lastNotice = [DateTime]::UtcNow
        }
        Start-Sleep -Seconds 2
        if ($null -ne $sandboxProcess) { $sandboxProcess.Refresh() }
    }
    if (-not (Test-Path -LiteralPath $successMarker)) {
        throw "Windows Sandbox build timed out after $TimeoutMinutes minutes."
    }
    Write-Host "[host] Build finished. Collecting artifacts..."
    [void](Wait-SandboxExit -Seconds 30)

    $artifacts = @(Get-ChildItem -LiteralPath $stagedOutput -Filter "*.exe" -File)
    if ($artifacts.Count -eq 0) {
        throw "The Sandbox reported success without producing an EXE."
    }
    foreach ($artifact in $artifacts) {
        Copy-Item -LiteralPath $artifact.FullName -Destination $OutputDirectory -Force
        Write-Host (Join-Path $OutputDirectory $artifact.Name)
    }
    $sandboxLog = Join-Path $stagedOutput "sandbox-build.log"
    if (Test-Path -LiteralPath $sandboxLog) {
        Copy-Item -LiteralPath $sandboxLog -Destination $OutputDirectory -Force
    }
}
finally {
    if (-not (Wait-SandboxExit -Seconds 30)) {
        Write-Host "[host] Windows Sandbox is still running; close its window to release the staged folders."
        if ($null -ne $sandboxProcess -and -not $sandboxProcess.HasExited) {
            Stop-Process -Id $sandboxProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path -LiteralPath $temporaryRoot) {
        for ($attempt = 1; $attempt -le 5; $attempt++) {
            try {
                Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction Stop
                break
            }
            catch {
                if ($attempt -eq 5) {
                    Write-Warning "Could not remove the temporary directory: $temporaryRoot"
                }
                else { Start-Sleep -Seconds 3 }
            }
        }
    }
}
