# Registers this folder as a Claude Code plugin folder for every session.
#
# Adds the folder this script is in to `env.CLAUDE_CODE_PLUGIN_DIRS` in
# ~/.claude/settings.json, beside any folders already listed there, and keeps
# the settings as they were in settings.json.before-marin.bak.
# Run it again after moving the folder. `-Remove` takes the folder out again.
param([switch]$Remove)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$settingsPath = Join-Path $HOME '.claude\settings.json'
$key = 'CLAUDE_CODE_PLUGIN_DIRS'

if (-not (Test-Path (Join-Path $here '.claude-plugin\plugin.json'))) {
    throw "No .claude-plugin\plugin.json beside this script: run it from the mod's own folder."
}

if (Test-Path $settingsPath) {
    $raw = Get-Content $settingsPath -Raw
    Copy-Item $settingsPath "$settingsPath.before-marin.bak" -Force
    $settings = $raw | ConvertFrom-Json
} else {
    New-Item -ItemType Directory -Force (Split-Path $settingsPath) | Out-Null
    $settings = [pscustomobject]@{}
}

if (-not $settings.PSObject.Properties['env']) {
    $settings | Add-Member -NotePropertyName env -NotePropertyValue ([pscustomobject]@{})
}
$listed = @()
if ($settings.env.PSObject.Properties[$key]) {
    $listed = @($settings.env.$key -split ';' | Where-Object { $_ })
}
# Compare as full paths, so `~/...` and a different spelling of this folder count as this folder.
$full = { param($p) [IO.Path]::GetFullPath(($p -replace '^~', $HOME)).TrimEnd('\') }
$others = @($listed | Where-Object { (& $full $_) -ne (& $full $here) })
$folders = if ($Remove) { $others } else { $others + $here }

if ($folders.Count -gt 0) {
    $settings.env | Add-Member -NotePropertyName $key -NotePropertyValue ($folders -join ';') -Force
} else {
    $settings.env.PSObject.Properties.Remove($key)
}
$settings | ConvertTo-Json -Depth 64 | Set-Content $settingsPath -Encoding utf8

if ($Remove) {
    "Removed $here from $key. Sessions opened from now on start without the Marin theme."
} else {
    "Registered $here in $key. Sessions opened from now on start with the Marin theme."
}
