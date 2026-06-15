Let me first look at what's already in the repository to understand the project structure.


Ran 2 commands
Empty repository on the feature branch. I'll write a complete, well-structured zsh script with a setup script and config file.


Ran a command, created 3 files
Now let me commit and push everything.


Ran 3 commands
Pushed. Here's what was created:

Files
rotary-voip.zsh — main script
Full state machine with six states:

IDLE → RINGING (incoming) → IN_CALL (answer) → IDLE (remote hangup or on-hook)
IDLE → OFF_HOOK (lift) → DIALING (first pulse) → CALLING (digits complete) → IN_CALL → IDLE
Key design decisions:

GPIO via /sys/class/gpio/ — no external tools needed beyond raspi-gpio for pull-ups
Rotary pulse counting — 5 ms polling loop, counts falling edges, inter-pulse gap of 300 ms ends a digit, 2.5 s inactivity auto-dials (configurable)
Bell — background subshell toggles GPIO 22 on the US 2s-on/4s-off cadence
VoIP — uses baresip (lightweight, designed for embedded), controlled over its ctrl_tcp JSON socket (netstring protocol). A separate background process streams events to a FIFO so the main loop never blocks on the network
On-hook mid-dial — any hook transition terminates the current state cleanly
setup.zsh — run once as root
Installs baresip, alsa-utils, netcat-openbsd, creates a systemd service that auto-starts on boot.

WIRING.md
Hook switch, rotary dial pulse contact, bell relay, and audio (SLIC / electret conversion) wiring diagrams.

Getting started
Edit the CFG block at the top of rotary-voip.zsh — set your SIP credentials, server address, GPIO pins, and audio device
sudo zsh setup.zsh — installs packages and the systemd service
sudo systemctl start rotary-voip — run it; journalctl -u rotary-voip -f to watch logs
