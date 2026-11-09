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

    Write-Host "Starting Windows Sandbox build..."
    Write-Host "The first build downloads Python and dependencies; later builds reuse the local download cache."
    if ($Manual) {
        Write-Host ""
        Write-Host "Manual mode: open PowerShell inside Windows Sandbox and run this command:"
        Write-Host $guestBuildCommand -ForegroundColor Cyan
        try {
            Set-Clipboard -Value $guestBuildCommand
            Write-Host "(Copied to the clipboard; paste it with Ctrl+V inside the Sandbox.)"
        }
        catch {
            # Clipboard access is a convenience only.
        }
        Write-Host ""
    }
    $sandboxProcess = Start-Process -FilePath $sandboxCommand.Source -ArgumentList "`"$configurationPath`"" -PassThru
    $successMarker = Join-Path $stagedOutput "build-success.txt"
    $errorMarker = Join-Path $stagedOutput "build-error.txt"
    $deadline = [DateTime]::UtcNow.AddMinutes($TimeoutMinutes)

    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $successMarker) { break }
        if (Test-Path -LiteralPath $errorMarker) {
            if (-not $sandboxProcess.HasExited) {
                [void]$sandboxProcess.WaitForExit(30000)
            }
            Copy-Item -LiteralPath $errorMarker -Destination $OutputDirectory -Force
            $sandboxLog = Join-Path $stagedOutput "sandbox-build.log"
            if (Test-Path -LiteralPath $sandboxLog) {
                Copy-Item -LiteralPath $sandboxLog -Destination $OutputDirectory -Force
            }
            throw (Get-Content -LiteralPath $errorMarker -Raw)
        }
        if ($sandboxProcess.HasExited) {
            throw "Windows Sandbox closed before the build completed."
        }
        Start-Sleep -Seconds 2
        $sandboxProcess.Refresh()
    }
    if (-not (Test-Path -LiteralPath $successMarker)) {
        throw "Windows Sandbox build timed out after $TimeoutMinutes minutes."
    }
    if (-not $sandboxProcess.HasExited) {
        [void]$sandboxProcess.WaitForExit(30000)
    }

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
    if ($null -ne $sandboxProcess -and -not $sandboxProcess.HasExited) {
        if (-not $sandboxProcess.WaitForExit(30000)) {
            Stop-Process -Id $sandboxProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
