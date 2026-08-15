[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$ListenAddress = "127.0.0.1",

    [ValidateRange(1, 65535)]
    [int]$Port = 8000,

    [ValidateRange(5, 600)]
    [int]$StartupTimeoutSeconds = 120,

    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-UvExecutable {
    $uvCommand = Get-Command "uv.exe" -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $uvCommand) {
        return $uvCommand.Source
    }

    if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
        $fallbackPath = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
        if (Test-Path -LiteralPath $fallbackPath -PathType Leaf) {
            return $fallbackPath
        }
    }

    throw "uv was not found. Install uv and make sure uv.exe is available in PATH."
}

function Test-ApplicationServer {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HealthUrl,

        [Parameter(Mandatory = $true)]
        [string]$ApplicationUrl
    )

    try {
        $healthResponse = Invoke-WebRequest `
            -UseBasicParsing `
            -Uri $HealthUrl `
            -TimeoutSec 2

        if ($healthResponse.StatusCode -ne 200) {
            return $false
        }

        $healthPayload = $healthResponse.Content | ConvertFrom-Json
        if ($healthPayload.status -ne "ok") {
            return $false
        }

        $applicationResponse = Invoke-WebRequest `
            -UseBasicParsing `
            -Uri $ApplicationUrl `
            -TimeoutSec 2

        return (
            $applicationResponse.StatusCode -eq 200 -and
            $applicationResponse.Content.Contains("<title>DocuStruct AI")
        )
    }
    catch {
        return $false
    }
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Address,

        [Parameter(Mandatory = $true)]
        [int]$TargetPort
    )

    $client = New-Object System.Net.Sockets.TcpClient
    $asyncResult = $null

    try {
        $asyncResult = $client.BeginConnect($Address, $TargetPort, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne(500, $false)) {
            return $false
        }

        $client.EndConnect($asyncResult)
        return $client.Connected
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $asyncResult) {
            $asyncResult.AsyncWaitHandle.Close()
        }
        $client.Close()
    }
}

function Open-ApplicationPage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [bool]$SkipBrowser
    )

    if ($SkipBrowser) {
        Write-Host "Browser launch skipped. Open $Url manually."
        return
    }

    try {
        Start-Process -FilePath $Url | Out-Null
    }
    catch {
        Write-Warning "The browser could not be opened automatically. Open $Url manually."
    }
}

function Stop-ProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Process
    )

    try {
        if ($Process.HasExited) {
            return
        }

        $taskkillPath = Join-Path $env:SystemRoot "System32\taskkill.exe"
        if (Test-Path -LiteralPath $taskkillPath -PathType Leaf) {
            & $taskkillPath /PID $Process.Id /T /F *> $null
            return
        }

        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
    catch {
        Write-Warning "The server process could not be stopped automatically."
    }
}

function Invoke-WebLauncher {
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $healthUrl = "http://${ListenAddress}:$Port/health"
    $applicationUrl = "http://${ListenAddress}:$Port/app/"
    $serverProcess = $null
    $locationChanged = $false

    try {
        Write-Host "Document Digitization AI"
        Write-Host "Project: $projectRoot"
        Write-Host "Web UI:  $applicationUrl"
        Write-Host ""

        $pyprojectPath = Join-Path $projectRoot "pyproject.toml"
        if (-not (Test-Path -LiteralPath $pyprojectPath -PathType Leaf)) {
            throw "pyproject.toml was not found in $projectRoot."
        }

        $environmentPath = Join-Path $projectRoot ".env"
        if (-not (Test-Path -LiteralPath $environmentPath -PathType Leaf)) {
            throw ".env was not found. Create it from .env.example before starting the application."
        }

        $uvExecutable = Get-UvExecutable

        Push-Location -LiteralPath $projectRoot
        $locationChanged = $true

        if (Test-ApplicationServer -HealthUrl $healthUrl -ApplicationUrl $applicationUrl) {
            Write-Host "The application is already running."
            Open-ApplicationPage -Url $applicationUrl -SkipBrowser $NoBrowser.IsPresent
            return 0
        }

        if (Test-TcpPort -Address $ListenAddress -TargetPort $Port) {
            throw "Port $Port is already used by another application. Stop it or choose another port."
        }

        $serverArguments = @(
            "run",
            "--with",
            "uvicorn",
            "uvicorn",
            "document_digitization_ai.api.http.app:create_app",
            "--factory",
            "--host",
            $ListenAddress,
            "--port",
            $Port.ToString()
        )

        Write-Host "Starting the local server..."
        $serverProcess = Start-Process `
            -FilePath $uvExecutable `
            -ArgumentList $serverArguments `
            -WorkingDirectory $projectRoot `
            -NoNewWindow `
            -PassThru

        $startupDeadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
        $serverReady = $false

        while ([DateTime]::UtcNow -lt $startupDeadline) {
            if ($serverProcess.HasExited) {
                $serverProcess.WaitForExit()
                $serverExitCode = $serverProcess.ExitCode
                $serverProcess = $null
                throw "The server exited before startup completed (exit code $serverExitCode)."
            }

            if (Test-ApplicationServer -HealthUrl $healthUrl -ApplicationUrl $applicationUrl) {
                $serverReady = $true
                break
            }

            Start-Sleep -Milliseconds 300
        }

        if (-not $serverReady) {
            throw "The server did not become ready within $StartupTimeoutSeconds seconds."
        }

        Write-Host ""
        Write-Host "The application is ready."
        Write-Host "Close this window or press Ctrl+C to stop the server."
        Write-Host ""
        Open-ApplicationPage -Url $applicationUrl -SkipBrowser $NoBrowser.IsPresent

        $serverProcess.WaitForExit()
        $serverExitCode = $serverProcess.ExitCode
        $serverProcess = $null

        if ($null -ne $serverExitCode -and $serverExitCode -ne 0) {
            throw "The server stopped with exit code $serverExitCode."
        }

        Write-Host "The server has stopped."
        return 0
    }
    catch {
        Write-Host ""
        Write-Host "Launcher error: $($_.Exception.Message)" -ForegroundColor Red
        return 1
    }
    finally {
        if ($null -ne $serverProcess) {
            Stop-ProcessTree -Process $serverProcess
        }

        if ($locationChanged) {
            Pop-Location
        }
    }
}

exit (Invoke-WebLauncher)
