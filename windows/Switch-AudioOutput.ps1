#Requires -Version 5.1
<#
.SYNOPSIS
    Switches the default Windows audio output between the 3.5 mm jack and
    the speakers, with a fully keyboard-driven, screen-reader-friendly
    interface.

.DESCRIPTION
    Built to be operated entirely by keyboard. Every state change is written
    as a plain text sentence (no ASCII art, no color-only signals, no popup
    dialogs), so JAWS and a refreshable Braille display both announce it
    correctly as it appears in the console.

    Uses the "AudioDeviceCmdlets" PowerShell module to talk to the same
    device list found in Settings > System > Sound. The module is installed
    automatically, for the current user only, the first time this script
    runs (this needs internet access once).

.PARAMETER Jack
    Switch output to the 3.5 mm jack device and exit immediately. No menu.

.PARAMETER Speakers
    Switch output to the speaker device and exit immediately. No menu.

.PARAMETER Toggle
    Switch to whichever of the two configured devices is NOT currently
    active, and exit immediately. No menu. This is the one to bind to a
    keyboard shortcut for single-key operation (see windows/README.md).

.PARAMETER Status
    Announce the current default playback device and exit.

.PARAMETER ListDevices
    List every playback device Windows currently knows about, with its
    exact name, so you can copy the exact text into -JackDeviceName /
    -SpeakerDeviceName.

.PARAMETER JackDeviceName
    Text found in the jack device's name (matched case-insensitively as a
    substring, e.g. "Headphones"). Saved to a config file after first use,
    so you only need to type it once.

.PARAMETER SpeakerDeviceName
    Text found in the speaker device's name (matched the same way, e.g.
    "Speakers"). Saved to a config file after first use.

.PARAMETER NoBeep
    Suppress the confirmation beep. Text feedback is always given
    regardless of this switch.

.EXAMPLE
    .\Switch-AudioOutput.ps1
    Opens the accessible numbered menu.

.EXAMPLE
    .\Switch-AudioOutput.ps1 -Toggle
    Flips output between jack and speakers with no prompts.

.EXAMPLE
    .\Switch-AudioOutput.ps1 -ListDevices
    Prints every playback device name so you can find the exact wording
    Windows uses for your jack / speakers before configuring the script.
#>

[CmdletBinding(DefaultParameterSetName = 'Menu')]
param(
    [Parameter(ParameterSetName = 'Jack')]
    [switch]$Jack,

    [Parameter(ParameterSetName = 'Speakers')]
    [switch]$Speakers,

    [Parameter(ParameterSetName = 'Toggle')]
    [switch]$Toggle,

    [Parameter(ParameterSetName = 'Status')]
    [switch]$Status,

    [Parameter(ParameterSetName = 'ListDevices')]
    [switch]$ListDevices,

    [string]$JackDeviceName,
    [string]$SpeakerDeviceName,

    [switch]$NoBeep
)

$ErrorActionPreference = 'Stop'
$ConfigPath = Join-Path $PSScriptRoot 'AudioSwitcher.config.json'

# Distinct confirmation tones so the choice is audible even without reading
# the text - a low tone for the jack, a high tone for the speakers.
$JackTone = 500
$SpeakerTone = 900

function Say {
    # Single choke point for all user-facing text: plain sentences only,
    # so JAWS and a Braille display read every line correctly.
    param([string]$Text)
    Write-Host $Text
}

function Confirm-Beep {
    param([int]$Frequency = 700, [int]$DurationMs = 150)
    if (-not $NoBeep) {
        try { [console]::beep($Frequency, $DurationMs) } catch { }
    }
}

function Confirm-AudioModule {
    if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) {
        return
    }
    Say "The AudioDeviceCmdlets module is required and is not installed yet."
    Say "Installing it now for the current user. This only happens once."
    try {
        try {
            Set-PSRepository -Name PSGallery -InstallationPolicy Trusted -ErrorAction Stop
        } catch { }
        Install-Module -Name AudioDeviceCmdlets -Scope CurrentUser -Force -AllowClobber -Confirm:$false
        Say "Module installed successfully."
    } catch {
        Say "Automatic install failed: $($_.Exception.Message)"
        Say "Open PowerShell yourself and run this command, then re-run this script:"
        Say "    Install-Module -Name AudioDeviceCmdlets -Scope CurrentUser -Force"
        exit 1
    }
}

function Get-SavedConfig {
    if (Test-Path $ConfigPath) {
        try { return Get-Content $ConfigPath -Raw | ConvertFrom-Json } catch { return $null }
    }
    return $null
}

function Save-Config {
    param([string]$JackName, [string]$SpeakerName)
    [pscustomobject]@{
        JackDeviceName    = $JackName
        SpeakerDeviceName = $SpeakerName
    } | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding UTF8
}

function Get-PlaybackDevices {
    Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' }
}

function Find-Device {
    param([string]$NameFragment)
    Get-PlaybackDevices | Where-Object { $_.Name -like "*$NameFragment*" } | Select-Object -First 1
}

function Get-CurrentDevice {
    Get-AudioDevice -Playback
}

function Set-OutputDevice {
    param($Device, [string]$FriendlyLabel, [int]$Frequency = 700)
    if (-not $Device) {
        Say "Could not find a playback device matching '$FriendlyLabel'."
        Say "Run this script with -ListDevices to see the exact device names Windows has, then re-run with -JackDeviceName or -SpeakerDeviceName set to that exact text."
        return $false
    }
    Set-AudioDevice -Index $Device.Index | Out-Null
    Say "Audio output switched to: $($Device.Name)"
    Confirm-Beep -Frequency $Frequency
    return $true
}

function Resolve-DeviceNames {
    # Command-line parameters win, then a saved config file, then defaults.
    $config = Get-SavedConfig
    $jackName = if ($JackDeviceName) { $JackDeviceName }
                elseif ($config -and $config.JackDeviceName) { $config.JackDeviceName }
                else { 'Headphones' }
    $speakerName = if ($SpeakerDeviceName) { $SpeakerDeviceName }
                   elseif ($config -and $config.SpeakerDeviceName) { $config.SpeakerDeviceName }
                   else { 'Speakers' }

    if ($JackDeviceName -or $SpeakerDeviceName) {
        Save-Config -JackName $jackName -SpeakerName $speakerName
    }
    return @{ Jack = $jackName; Speaker = $speakerName }
}

function Show-Status {
    $current = Get-CurrentDevice
    if ($current) {
        Say "Current default audio output: $($current.Name)"
    } else {
        Say "Could not determine the current audio output device."
    }
}

function Show-DeviceList {
    $devices = Get-PlaybackDevices
    if (-not $devices) {
        Say "No playback devices were found."
        return
    }
    Say "Playback devices known to Windows:"
    $i = 1
    foreach ($d in $devices) {
        $marker = if ($d.Default) { ' (currently default)' } else { '' }
        Say "$i. $($d.Name)$marker"
        $i++
    }
}

function Invoke-Toggle {
    param([hashtable]$Names)
    $current = Get-CurrentDevice
    $jackDevice = Find-Device -NameFragment $Names.Jack
    $speakerDevice = Find-Device -NameFragment $Names.Speaker

    if (-not $jackDevice -or -not $speakerDevice) {
        Say "Cannot toggle: one or both configured devices were not found."
        Show-DeviceList
        return
    }

    if ($current -and $current.Index -eq $jackDevice.Index) {
        Set-OutputDevice -Device $speakerDevice -FriendlyLabel $Names.Speaker -Frequency $SpeakerTone
    } else {
        Set-OutputDevice -Device $jackDevice -FriendlyLabel $Names.Jack -Frequency $JackTone
    }
}

function Set-DeviceNamesInteractive {
    Say "Enter text found in the jack device's name, for example Headphones."
    $jackInput = Read-Host "Jack device name text"
    Say "Enter text found in the speaker device's name, for example Speakers."
    $speakerInput = Read-Host "Speaker device name text"
    $names = Resolve-DeviceNames
    if ($jackInput) { $names.Jack = $jackInput }
    if ($speakerInput) { $names.Speaker = $speakerInput }
    Save-Config -JackName $names.Jack -SpeakerName $names.Speaker
    Say "Saved. These names will be used automatically next time."
    return $names
}

function Show-Menu {
    param([hashtable]$Names)
    Say ""
    Say "Audio Output Switcher"
    Say "1. Switch to 3.5 mm jack ($($Names.Jack))"
    Say "2. Switch to speakers ($($Names.Speaker))"
    Say "3. Toggle between the two"
    Say "4. Announce current output device"
    Say "5. List all playback devices"
    Say "6. Set which device names to use for jack and speakers"
    Say "Q. Quit"
    Say ""
    (Read-Host "Type a number or letter, then press Enter").Trim()
}

# ---- Entry point ----

Confirm-AudioModule

switch ($PSCmdlet.ParameterSetName) {
    'ListDevices' {
        Show-DeviceList
    }
    'Status' {
        Show-Status
    }
    'Jack' {
        $names = Resolve-DeviceNames
        Set-OutputDevice -Device (Find-Device -NameFragment $names.Jack) -FriendlyLabel $names.Jack -Frequency $JackTone | Out-Null
    }
    'Speakers' {
        $names = Resolve-DeviceNames
        Set-OutputDevice -Device (Find-Device -NameFragment $names.Speaker) -FriendlyLabel $names.Speaker -Frequency $SpeakerTone | Out-Null
    }
    'Toggle' {
        $names = Resolve-DeviceNames
        Invoke-Toggle -Names $names
    }
    default {
        $names = Resolve-DeviceNames
        Say "Welcome to the Audio Output Switcher."
        Say "This menu is fully keyboard-driven. Type a choice and press Enter."
        $running = $true
        while ($running) {
            $choice = (Show-Menu -Names $names).ToUpper()
            switch ($choice) {
                '1' { Set-OutputDevice -Device (Find-Device -NameFragment $names.Jack) -FriendlyLabel $names.Jack -Frequency $JackTone | Out-Null }
                '2' { Set-OutputDevice -Device (Find-Device -NameFragment $names.Speaker) -FriendlyLabel $names.Speaker -Frequency $SpeakerTone | Out-Null }
                '3' { Invoke-Toggle -Names $names }
                '4' { Show-Status }
                '5' { Show-DeviceList }
                '6' { $names = Set-DeviceNamesInteractive }
                'Q' { Say "Goodbye."; $running = $false }
                default { Say "Not a valid choice. Type 1, 2, 3, 4, 5, 6, or Q." }
            }
        }
    }
}
