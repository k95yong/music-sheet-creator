param(
    [string]$Workspace = "",
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$server = Join-Path $repositoryRoot "app\workspace_server.pyw"

if ($Workspace) {
    $env:MUSIC_SHEET_WORKSPACE = $Workspace
}
$env:MUSIC_SHEET_PORT = [string]$Port

$arguments = @($server)
if ($NoBrowser) {
    $arguments += "--no-browser"
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @arguments
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python @arguments
} else {
    throw "Python 3 was not found. Install Python and retry."
}

