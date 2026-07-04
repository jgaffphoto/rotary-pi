# Audio Output Switcher (Windows)

`Switch-AudioOutput.ps1` switches the default Windows audio output between
the 3.5 mm jack and the speakers. It is built to be operated entirely with
a keyboard (or a Braille keyboard/display in keyboard-emulation mode) and
read by a screen reader such as JAWS: every state change is written as a
plain text sentence, there are no popup dialogs, no color-only signals,
and no mouse interaction anywhere in the script.

## Requirements

- Windows PowerShell 5.1 or later (built into Windows 10/11).
- Internet access the *first* time you run it, so it can install the
  `AudioDeviceCmdlets` module for your user account. After that it works
  offline.

## First run

Open PowerShell and run:

```powershell
cd path\to\rotary-pi\windows
powershell -ExecutionPolicy Bypass -File .\Switch-AudioOutput.ps1 -ListDevices
```

This prints the exact playback device names Windows has, for example:

```
Playback devices known to Windows:
1. Speakers (Realtek(R) Audio) (currently default)
2. Headphones (Realtek(R) Audio)
```

By default the script looks for "Headphones" (jack) and "Speakers"
(speakers). If your device names are different, tell it once and it will
remember:

```powershell
powershell -ExecutionPolicy Bypass -File .\Switch-AudioOutput.ps1 -JackDeviceName "Headphones" -SpeakerDeviceName "Speakers" -Status
```

The names are saved next to the script in `AudioSwitcher.config.json`, so
every later run (menu or command-line) uses them automatically.

## Everyday use

Interactive, fully spoken/Braille-readable menu:

```powershell
powershell -ExecutionPolicy Bypass -File .\Switch-AudioOutput.ps1
```

Type `1`, `2`, `3`, `4`, `5`, `6`, or `Q` and press Enter — no arrow-key
navigation or mouse required. Every action confirms itself in plain text
("Audio output switched to: Headphones (Realtek(R) Audio)") plus a short
beep (low tone for the jack, high tone for the speakers) as a second,
non-visual cue. Add `-NoBeep` to a command if you only want text.

Direct, no-prompt commands for scripts or shortcuts:

```powershell
.\Switch-AudioOutput.ps1 -Jack       # switch to the 3.5 mm jack
.\Switch-AudioOutput.ps1 -Speakers   # switch to the speakers
.\Switch-AudioOutput.ps1 -Toggle     # switch to whichever isn't active
.\Switch-AudioOutput.ps1 -Status     # announce the current device
```

## Setting up a one-key shortcut

`-Toggle` is meant to be bound to a keyboard shortcut so switching output
never requires opening a menu at all:

1. Right-click (or open the context menu with the Menu/Shift+F10 key) in
   File Explorer and choose **New > Shortcut**.
2. Set the target to:
   ```
   powershell -ExecutionPolicy Bypass -File "C:\path\to\rotary-pi\windows\Switch-AudioOutput.ps1" -Toggle
   ```
3. Save the shortcut to the Desktop or Start Menu.
4. Open the shortcut's **Properties** dialog (standard Win32 dialog, fully
   navigable with Tab/Shift+Tab and read correctly by JAWS) and set the
   **Shortcut key** field, e.g. `Ctrl+Alt+A`. Windows will then run the
   toggle from anywhere on the desktop with that key combination.

## Notes

- Run the script in a normal (not minimized/hidden) console window so its
  text output is visible to the screen reader.
- If a device name fragment matches more than one device, use a more
  specific fragment (e.g. the full device name from `-ListDevices`).
- `AudioDeviceCmdlets` is the open-source module this script relies on for
  talking to Windows' Core Audio API: https://github.com/frgnca/AudioDeviceCmdlets
