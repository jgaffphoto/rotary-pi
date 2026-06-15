#!/usr/bin/env zsh
# =============================================================================
# setup.zsh  —  Install dependencies and configure the system for rotary-voip
# Run as root:  sudo zsh setup.zsh
# =============================================================================

setopt ERR_EXIT NO_UNSET

[[ $EUID -eq 0 ]] || { print "Run as root: sudo zsh setup.zsh"; exit 1 }

SCRIPT_DIR=${0:a:h}
SERVICE_USER=${SUDO_USER:-pi}

print "=== rotary-voip setup ==="

# ─── System packages ─────────────────────────────────────────────────────────
print "\n[1/5] Installing packages…"
apt-get update -qq
apt-get install -y \
    baresip \
    baresip-core \
    baresip-extra \
    alsa-utils \
    netcat-openbsd \
    zsh \
    raspi-gpio 2>/dev/null || apt-get install -y zsh raspi-gpio || true

# ─── Verify baresip modules are present ──────────────────────────────────────
print "\n[2/5] Checking baresip modules…"
for mod in alsa g711 ctrl_tcp; do
    found=$(find /usr/lib /usr/local/lib -name "${mod}.so" 2>/dev/null | head -1)
    if [[ -n $found ]]; then
        print "  ✓ ${mod}.so  ($found)"
    else
        print "  ✗ ${mod}.so  NOT FOUND — you may need baresip-extra or a manual build"
    fi
done

# ─── ALSA: list audio devices for the user to identify their USB adapter ─────
print "\n[3/5] Audio devices detected:"
aplay -l 2>/dev/null || print "  (aplay not available yet — run 'aplay -l' after reboot)"

print ""
print "  Edit rotary-voip.zsh and set CFG[audio_dev] to match your USB adapter."
print "  Common value for a single USB audio dongle:  plughw:1,0"

# ─── Script permissions ───────────────────────────────────────────────────────
print "\n[4/5] Setting permissions…"
chmod +x "${SCRIPT_DIR}/rotary-voip.zsh"
chown "${SERVICE_USER}:${SERVICE_USER}" "${SCRIPT_DIR}/rotary-voip.zsh"

# ─── systemd service ──────────────────────────────────────────────────────────
print "\n[5/5] Installing systemd service…"

cat > /etc/systemd/system/rotary-voip.service << SERVICE
[Unit]
Description=Rotary Phone VoIP Interface
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=/usr/bin/zsh ${SCRIPT_DIR}/rotary-voip.zsh
Restart=on-failure
RestartSec=5

# Allow GPIO access
SupplementaryGroups=gpio audio

StandardOutput=journal
StandardError=journal
SyslogIdentifier=rotary-voip

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable rotary-voip.service
print "  Service installed and enabled."
print "  Start now with:  sudo systemctl start rotary-voip"
print "  View logs with:  journalctl -u rotary-voip -f"

print "\n=== Setup complete ==="
print ""
print "Next steps:"
print "  1. Edit rotary-voip.zsh — fill in CFG[sip_user], [sip_pass], [sip_server]"
print "  2. Confirm CFG[audio_dev] matches your USB audio adapter (aplay -l)"
print "  3. Confirm GPIO pin numbers match your wiring (see header comments)"
print "  4. sudo systemctl start rotary-voip"
