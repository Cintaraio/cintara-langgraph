#Requires -Version 5.1

[CmdletBinding()]
param(
    [string]$OnboardingCode,
    [string]$DeveloperEmail,
    [string]$VerificationCode,
    [string]$AgentId,
    [string]$TenantId,
    [string]$PolicyUrl,
    [string]$RegistryUrl = "https://platform.cintara.io/registry",
    [string]$GatewayUrl,
    [string]$ApiToken,
    [string]$ToolName = "send_email",
    [string]$ProjectDir = ".",
    [string]$Python,
    [switch]$Overwrite,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$PackageSpec = if ($env:CINTARA_LANGGRAPH_PACKAGE_SPEC) {
    $env:CINTARA_LANGGRAPH_PACKAGE_SPEC
} else {
    "cintara-langgraph[langgraph] @ git+https://github.com/Cintaraio/cintara-langgraph.git"
}

function Test-PythonCommand {
    param(
        [string]$Executable,
        [string[]]$PrefixArgs = @()
    )

    & $Executable @PrefixArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
    return $LASTEXITCODE -eq 0
}

function Set-PythonCommand {
    if ($Python) {
        if (-not (Test-PythonCommand -Executable $Python)) {
            throw "The Python executable passed with -Python must be Python 3.11+."
        }
        $script:PythonExecutable = $Python
        $script:PythonPrefixArgs = @()
        return
    }

    if ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-PythonCommand -Executable "py" -PrefixArgs @("-3.11"))) {
        $script:PythonExecutable = "py"
        $script:PythonPrefixArgs = @("-3.11")
        return
    }

    if ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-PythonCommand -Executable "python")) {
        $script:PythonExecutable = "python"
        $script:PythonPrefixArgs = @()
        return
    }

    if ((Get-Command python3 -ErrorAction SilentlyContinue) -and (Test-PythonCommand -Executable "python3")) {
        $script:PythonExecutable = "python3"
        $script:PythonPrefixArgs = @()
        return
    }

    throw "Python 3.11+ is required. Install Python 3.11+ and re-run this script."
}

function Invoke-Python {
    param([string[]]$Arguments)

    $pythonArgs = @()
    $pythonArgs += $script:PythonPrefixArgs
    $pythonArgs += $Arguments
    & $script:PythonExecutable @pythonArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
}

function Add-ArgumentIfValue {
    param(
        [ref]$Arguments,
        [string]$Name,
        [string]$Value
    )
    if ($Value) {
        $Arguments.Value += @($Name, $Value)
    }
}

Set-PythonCommand

if (-not $env:VIRTUAL_ENV) {
    if (-not (Test-Path ".venv")) {
        Invoke-Python -Arguments @("-m", "venv", ".venv")
    }

    $venvPython = Join-Path ".venv" "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw "Could not find $venvPython after creating the virtual environment."
    }

    $env:VIRTUAL_ENV = (Resolve-Path ".venv").Path
    $env:PATH = "$(Join-Path $env:VIRTUAL_ENV 'Scripts');$env:PATH"
    $script:PythonExecutable = (Resolve-Path $venvPython).Path
    $script:PythonPrefixArgs = @()
}

Invoke-Python -Arguments @("-m", "pip", "install", $PackageSpec)

Write-Host ""
Write-Host "Initializing Cintara LangGraph onboarding files..."

$initArgs = @("-m", "cintara_langgraph", "init", "--project-dir", $ProjectDir)
Add-ArgumentIfValue ([ref]$initArgs) "--onboarding-code" $OnboardingCode
Add-ArgumentIfValue ([ref]$initArgs) "--developer-email" $DeveloperEmail
Add-ArgumentIfValue ([ref]$initArgs) "--verification-code" $VerificationCode
Add-ArgumentIfValue ([ref]$initArgs) "--agent-id" $AgentId
Add-ArgumentIfValue ([ref]$initArgs) "--tenant-id" $TenantId
Add-ArgumentIfValue ([ref]$initArgs) "--policy-url" $PolicyUrl
Add-ArgumentIfValue ([ref]$initArgs) "--registry-url" $RegistryUrl
Add-ArgumentIfValue ([ref]$initArgs) "--gateway-url" $GatewayUrl
Add-ArgumentIfValue ([ref]$initArgs) "--api-token" $ApiToken
Add-ArgumentIfValue ([ref]$initArgs) "--tool-name" $ToolName

if ($Overwrite) {
    $initArgs += "--overwrite"
}
if ($SkipSmokeTest) {
    $initArgs += "--skip-smoke-test"
}

Invoke-Python -Arguments $initArgs
