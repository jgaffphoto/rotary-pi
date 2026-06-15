#!/usr/bin/env zsh
# =============================================================================
# rotary-voip.zsh  —  Western Electric Type 500 Rotary Phone VoIP Interface
# Target: Raspberry Pi Zero W running Raspberry Pi OS Lite
#
# Hardware connections (BCM pin numbers):
#   GPIO 17  — Hook switch (LOW = handset lifted / off-hook)
#              Wire between one terminal of the hook switch and GPIO 17;
#              other terminal to GND.  Enable internal pull-up in script.
#
#   GPIO 27  — Rotary dial pulse line (normally HIGH, pulses LOW)
#              Wire to the dial's normally-closed (NC) pulsing contact.
#              Other contact to GND.  Enable internal pull-up in script.
#
#   GPIO 22  — Bell relay control (HIGH = ring)
#              Drive a 5 V relay module (active-high) connected to the
#              bell's electromagnet coil via an appropriate AC/DC circuit.
#
#   USB audio adapter → handset (via 600-ohm matching transformer or SLIC
#              board).  Carbon mic needs ~3-9 V DC bias from the SLIC or
#              a bias resistor network; electret mic replacement skips this.
#
# Dependencies (install via apt):
#   baresip  baresip-core  baresip-extra  alsa-utils  netcat-openbsd
#
# SIP configuration:  edit the CONFIGURATION section below.
# =============================================================================

setopt NO_UNSET PIPE_FAIL
emulate -LR zsh

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION  — edit these to match your environment
# ─────────────────────────────────────────────────────────────────────────────
typeset -A CFG
CFG=(
    # SIP account
    sip_user        "100"
    sip_pass        "secret"
    sip_server      "pbx.local"
    sip_port        "5060"

    # GPIO pins (BCM / broadcom numbering)
    pin_hook        17          # LOW  = off-hook (handset lifted)
    pin_dial        27          # pulses LOW while dial spins
    pin_bell        22          # HIGH = ring the bell

    # ALSA device for the handset audio (find yours with: aplay -l)
    audio_dev       "plughw:1,0"

    # Rotary-dial timing (milliseconds)
    pulse_gap_ms    300         # silence between pulses within one digit
    digit_gap_ms    2500        # silence after last pulse  → dial out

    # Minimum digits before we will attempt to dial
    min_digits      3

    # Maximum digits we collect before auto-dialing
    max_digits      11          # 11 = full NANP  (1 + 10-digit), adjust for PBX

    # baresip ctrl_tcp port (must match config file written by init_baresip)
    ctrl_port       4444

    # Paths
    work_dir        "${HOME}/.rotary-voip"
)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBALS
# ─────────────────────────────────────────────────────────────────────────────
typeset    STATE="IDLE"         # IDLE | RINGING | OFF_HOOK | DIALING | CALLING | IN_CALL
typeset    DIGITS=""            # digits collected so far
typeset -i BELL_PID=0
typeset -i BARESIP_PID=0
typeset -i EVENT_LISTENER_PID=0
typeset    EVENT_FIFO=""

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
log()  { print -P "%F{cyan}[%D{%H:%M:%S}]%f $*" }
warn() { print -P "%F{yellow}[%D{%H:%M:%S}] WARN:%f $*" }
die()  { print -P "%F{red}[%D{%H:%M:%S}] FATAL:%f $*" >&2; exit 1 }

# ─────────────────────────────────────────────────────────────────────────────
# GPIO  (kernel sysfs interface — no external tools required)
# ─────────────────────────────────────────────────────────────────────────────
readonly GPIO_ROOT=/sys/class/gpio

_gpio_path()  { echo "${GPIO_ROOT}/gpio${1}" }

gpio_export() {
    local pin=$1 dir=$2   # dir: "in" or "out"
    if [[ ! -d $(_gpio_path $pin) ]]; then
        echo $pin > ${GPIO_ROOT}/export 2>/dev/null || true
        sleep 0.15        # kernel needs a moment to create the sysfs entry
    fi
    echo $dir > $(_gpio_path $pin)/direction

    # Enable internal pull-up for inputs via raspi-gpio (if available)
    if [[ $dir == "in" ]]; then
        command -v raspi-gpio &>/dev/null &&
            raspi-gpio set $pin pu 2>/dev/null || true
    fi
}

gpio_read()  { < $(_gpio_path ${1})/value }

gpio_write() { echo ${2} > $(_gpio_path ${1})/value }

gpio_unexport() {
    echo ${1} > ${GPIO_ROOT}/unexport 2>/dev/null || true
}

init_gpio() {
    log "Initialising GPIO pins…"
    gpio_export $CFG[pin_hook] in
    gpio_export $CFG[pin_dial] in
    gpio_export $CFG[pin_bell] out
    gpio_write  $CFG[pin_bell] 0
    log "GPIO ready"
}

cleanup_gpio() {
    gpio_write  $CFG[pin_bell] 0
    gpio_unexport $CFG[pin_hook]
    gpio_unexport $CFG[pin_dial]
    gpio_unexport $CFG[pin_bell]
}

# ─────────────────────────────────────────────────────────────────────────────
# BELL  (US cadence: 2 s on / 4 s off)
# ─────────────────────────────────────────────────────────────────────────────
ring_bell() {
    (( BELL_PID )) && return  # already ringing
    {
        while true; do
            gpio_write $CFG[pin_bell] 1
            sleep 2
            gpio_write $CFG[pin_bell] 0
            sleep 4
        done
    } &
    BELL_PID=$!
    log "Bell started (pid $BELL_PID)"
}

stop_bell() {
    if (( BELL_PID )); then
        kill $BELL_PID 2>/dev/null || true
        wait $BELL_PID 2>/dev/null || true
        BELL_PID=0
    fi
    gpio_write $CFG[pin_bell] 0
}

# ─────────────────────────────────────────────────────────────────────────────
# ROTARY DIAL — pulse counting
#
# The rotary dial's NC contact pulses LOW (break) for each digit.
# Pulse rate ≈ 10 pulses/second (100 ms period).
# 1 pulse → digit 1 … 9 pulses → digit 9, 10 pulses → digit 0.
#
# This function BLOCKS while reading one digit or times out after
# $CFG[pulse_gap_ms] ms of silence (returns empty string on timeout).
# Call it only when the handset is already off-hook.
# ─────────────────────────────────────────────────────────────────────────────
read_one_digit() {
    local -i pulses=0
    local cur prev
    prev=$(gpio_read $CFG[pin_dial])

    # ── wait for first falling edge (dial begins to rotate) ──────────────────
    local -F t0=$EPOCHREALTIME
    while true; do
        cur=$(gpio_read $CFG[pin_dial])
        if [[ $cur == 0 && $prev == 1 ]]; then
            break                   # first pulse started
        fi
        prev=$cur
        # If the hook is back on before any pulse, bail out immediately
        [[ $(gpio_read $CFG[pin_hook]) == 1 ]] && echo "" && return
        # Timeout — no pulse within 100 ms means no digit forthcoming
        (( (EPOCHREALTIME - t0) * 1000 > 100 )) && echo "" && return
        sleep 0.005
    done

    # ── count pulses ─────────────────────────────────────────────────────────
    while true; do
        # wait for rising edge (end of pulse)
        local -F t1=$EPOCHREALTIME
        while [[ $(gpio_read $CFG[pin_dial]) == 0 ]]; do
            sleep 0.005
            # safety: bail if on-hook mid-pulse
            [[ $(gpio_read $CFG[pin_hook]) == 1 ]] && echo "" && return
        done
        (( pulses++ ))

        # wait for next falling edge OR inter-digit gap timeout
        local -F gap_start=$EPOCHREALTIME
        prev=1
        while true; do
            cur=$(gpio_read $CFG[pin_dial])
            if [[ $cur == 0 && $prev == 1 ]]; then
                break               # another pulse coming
            fi
            prev=$cur
            local -F elapsed=$(( (EPOCHREALTIME - gap_start) * 1000 ))
            if (( elapsed > CFG[pulse_gap_ms] )); then
                # inter-digit gap — digit is complete
                (( pulses == 10 )) && pulses=0      # 10 pulses → digit 0
                echo $pulses
                return
            fi
            sleep 0.005
        done
    done
}

# ─────────────────────────────────────────────────────────────────────────────
# BARESIP  — SIP user-agent controlled over ctrl_tcp (JSON + netstrings)
# ─────────────────────────────────────────────────────────────────────────────

# Write baresip config and accounts files
init_baresip_config() {
    local bdir="${CFG[work_dir]}/baresip"
    mkdir -p "$bdir"

    cat > "${bdir}/config" <<- CONFIG
	# baresip config — rotary-voip auto-generated
	sip_listen          0.0.0.0:${CFG[sip_port]}

	# Audio
	audio_player        alsa,${CFG[audio_dev]}
	audio_source        alsa,${CFG[audio_dev]}
	audio_alert         alsa,${CFG[audio_dev]}
	audio_buffer        40-160

	# Codecs (G.711 µ-law is universal; add more if your PBX supports them)
	audio_codecs        PCMU/8000/1,PCMA/8000/1

	# Modules
	module              alsa.so
	module              g711.so
	module              ctrl_tcp.so

	# ctrl_tcp — command/event socket
	ctrl_tcp_listen     127.0.0.1:${CFG[ctrl_port]}
	CONFIG

    cat > "${bdir}/accounts" <<- ACCOUNTS
	<sip:${CFG[sip_user]}@${CFG[sip_server]}>;auth_pass=${CFG[sip_pass]};regint=60;
	ACCOUNTS

    log "baresip config written to ${bdir}"
}

# Send a single command and return the JSON response (one-shot connection)
_baresip_send() {
    local payload="$1"
    local len=${#payload}
    # netstring framing:  "<len>:<payload>,"
    printf '%d:%s,' $len "$payload" |
        nc -q 1 127.0.0.1 $CFG[ctrl_port] 2>/dev/null || true
}

baresip_dial() {
    local number="$1"
    local uri="sip:${number}@${CFG[sip_server]}"
    log "Dialing $uri"
    _baresip_send "{\"command\":\"dial\",\"params\":\"${uri}\"}"
}

baresip_answer() {
    log "Answering call"
    _baresip_send '{"command":"accept"}'
}

baresip_hangup() {
    log "Hanging up"
    _baresip_send '{"command":"hangup"}' || true
}

# ─────────────────────────────────────────────────────────────────────────────
# BARESIP EVENT LISTENER  (background process → EVENT_FIFO)
#
# baresip pushes JSON events over the same ctrl_tcp port.  We keep a persistent
# nc connection open and write each complete JSON object to the event FIFO so
# the main loop can poll it without blocking.
# ─────────────────────────────────────────────────────────────────────────────
start_event_listener() {
    EVENT_FIFO="${CFG[work_dir]}/events.fifo"
    [[ -p $EVENT_FIFO ]] || mkfifo "$EVENT_FIFO"

    {
        while true; do
            # nc reconnects automatically if baresip restarts
            nc 127.0.0.1 $CFG[ctrl_port] 2>/dev/null | while IFS= read -r line; do
                # Each line from ctrl_tcp is a netstring; extract the JSON part
                # Format: "<len>:<json>,"  — strip the framing
                local json="${line#*:}"
                json="${json%,}"
                [[ -n $json ]] && echo "$json" >> "$EVENT_FIFO"
            done
            sleep 2     # pause before reconnect attempt
        done
    } &
    EVENT_LISTENER_PID=$!
    log "Event listener started (pid $EVENT_LISTENER_PID)"
}

# Non-blocking read of one event line from the FIFO; returns empty if none
poll_event() {
    [[ -s $EVENT_FIFO ]] || return 0
    local line
    # read with near-zero timeout so we don't block the main loop
    IFS= read -r -t 0.001 line < "$EVENT_FIFO" 2>/dev/null && echo "$line" || true
}

# Parse an event JSON string and return the "event" or "type" field value
event_type() {
    # Minimal parser — avoids depending on jq
    local json="$1"
    local val
    # Try "event" key first, then "type"
    val="${json#*\"event\":\"}"
    val="${val%%\"*}"
    [[ $val != $json ]] && { echo "$val"; return }
    val="${json#*\"type\":\"}"
    val="${val%%\"*}"
    [[ $val != $json ]] && { echo "$val"; return }
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# START / STOP baresip daemon
# ─────────────────────────────────────────────────────────────────────────────
start_baresip() {
    init_baresip_config

    baresip -f "${CFG[work_dir]}/baresip" &
    BARESIP_PID=$!
    log "baresip started (pid $BARESIP_PID)"

    # Wait up to 8 s for the ctrl_tcp port to open
    local -i i=0
    while (( i < 16 )); do
        sleep 0.5
        nc -z 127.0.0.1 $CFG[ctrl_port] 2>/dev/null && break
        (( i++ ))
    done
    if ! nc -z 127.0.0.1 $CFG[ctrl_port] 2>/dev/null; then
        die "baresip ctrl_tcp port ${CFG[ctrl_port]} did not open — check baresip install and config"
    fi
    log "baresip ctrl_tcp ready"
}

stop_baresip() {
    (( BARESIP_PID )) && kill $BARESIP_PID 2>/dev/null || true
    (( BARESIP_PID )) && wait $BARESIP_PID 2>/dev/null || true
    BARESIP_PID=0
}

# ─────────────────────────────────────────────────────────────────────────────
# STATE MACHINE
# ─────────────────────────────────────────────────────────────────────────────
transition() {
    log "state: ${STATE} → ${1}"
    STATE="$1"
}

handle_baresip_event() {
    local json="$1"
    local etype
    etype=$(event_type "$json")
    [[ -z $etype ]] && return

    case $etype in
        CALL_INCOMING)
            if [[ $STATE == IDLE ]]; then
                log "Incoming call — ringing"
                ring_bell
                transition RINGING
            elif [[ $STATE == IN_CALL || $STATE == CALLING ]]; then
                # Reject a second incoming call — we don't do waiting
                log "Second incoming call rejected (busy)"
                _baresip_send '{"command":"hangup"}' || true
            fi
            ;;
        CALL_ESTABLISHED)
            stop_bell
            transition IN_CALL
            log "Call connected"
            ;;
        CALL_CLOSED)
            stop_bell
            if [[ $STATE != IDLE ]]; then
                log "Call ended by remote"
                DIGITS=""
                transition IDLE
            fi
            ;;
        REGISTER_OK)
            log "SIP registered successfully"
            ;;
        REGISTER_FAIL)
            warn "SIP registration failed — check credentials/server"
            ;;
    esac
}

# ─────────────────────────────────────────────────────────────────────────────
# CLEANUP
# ─────────────────────────────────────────────────────────────────────────────
cleanup() {
    log "Shutting down…"
    stop_bell
    baresip_hangup 2>/dev/null || true
    (( EVENT_LISTENER_PID )) && kill $EVENT_LISTENER_PID 2>/dev/null || true
    stop_baresip
    cleanup_gpio
    [[ -n $EVENT_FIFO && -p $EVENT_FIFO ]] && rm -f "$EVENT_FIFO"
    exit 0
}

trap cleanup INT TERM

# ─────────────────────────────────────────────────────────────────────────────
# DIGIT TIMEOUT helper
# Track the time of the last dialed digit; auto-dial after CFG[digit_gap_ms]
# ─────────────────────────────────────────────────────────────────────────────
typeset -F LAST_DIGIT_TIME=0

reset_digit_timer() { LAST_DIGIT_TIME=$EPOCHREALTIME }

digit_timeout_expired() {
    (( LAST_DIGIT_TIME > 0 )) || return 1    # timer not running
    local -F elapsed=$(( (EPOCHREALTIME - LAST_DIGIT_TIME) * 1000 ))
    (( elapsed > CFG[digit_gap_ms] ))
}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────
main() {
    log "=== Rotary VoIP starting ==="

    # Prerequisites
    for cmd in baresip nc aplay; do
        command -v $cmd &>/dev/null || die "Required command not found: $cmd"
    done

    mkdir -p "${CFG[work_dir]}"

    init_gpio
    start_baresip
    start_event_listener

    # Seed the hook state
    local prev_hook cur_hook
    prev_hook=$(gpio_read $CFG[pin_hook])
    log "Ready — handset is currently $(( prev_hook == 0 )) && echo OFF-HOOK || echo ON-HOOK)"

    while true; do
        # ── 1. Process pending baresip events ────────────────────────────────
        local ev
        while ev=$(poll_event) && [[ -n $ev ]]; do
            handle_baresip_event "$ev"
        done

        # ── 2. Hook-switch edge detection ────────────────────────────────────
        cur_hook=$(gpio_read $CFG[pin_hook])
        if [[ $cur_hook != $prev_hook ]]; then
            prev_hook=$cur_hook

            if [[ $cur_hook == 0 ]]; then
                # ─── handset LIFTED ──────────────────────────────────────────
                log "Handset lifted"
                case $STATE in
                    IDLE)
                        DIGITS=""
                        LAST_DIGIT_TIME=0
                        transition OFF_HOOK
                        ;;
                    RINGING)
                        stop_bell
                        baresip_answer
                        transition IN_CALL
                        ;;
                    *) ;;   # already off-hook
                esac
            else
                # ─── handset REPLACED ────────────────────────────────────────
                log "Handset replaced"
                case $STATE in
                    RINGING)
                        stop_bell
                        baresip_hangup
                        ;;
                    OFF_HOOK|DIALING|CALLING|IN_CALL)
                        baresip_hangup
                        ;;
                    *) ;;
                esac
                DIGITS=""
                LAST_DIGIT_TIME=0
                transition IDLE
            fi
        fi

        # ── 3. Digit collection (only when waiting to dial) ──────────────────
        if [[ $STATE == OFF_HOOK || $STATE == DIALING ]]; then
            local digit
            digit=$(read_one_digit)

            if [[ -n $digit ]]; then
                DIGITS+="$digit"
                reset_digit_timer
                transition DIALING
                log "Digit: $digit  →  collected so far: ${DIGITS}"

                # Auto-dial when maximum digit count reached
                if (( ${#DIGITS} >= CFG[max_digits] )); then
                    baresip_dial "$DIGITS"
                    DIGITS=""
                    LAST_DIGIT_TIME=0
                    transition CALLING
                fi
            fi

            # Auto-dial after inactivity if we have enough digits
            if [[ $STATE == DIALING ]] && digit_timeout_expired &&
               (( ${#DIGITS} >= CFG[min_digits] )); then
                baresip_dial "$DIGITS"
                DIGITS=""
                LAST_DIGIT_TIME=0
                transition CALLING
            fi
        fi

        # ── 4. Yield CPU briefly ─────────────────────────────────────────────
        sleep 0.01
    done
}

main "$@"
