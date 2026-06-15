# Type 500 Rotary Phone — Raspberry Pi Zero W Wiring Guide

## GPIO Assignments (BCM numbering)

| GPIO | Pin # | Role | Signal |
|------|-------|------|--------|
| 17 | 11 | Hook switch | LOW = off-hook (handset lifted) |
| 27 | 13 | Rotary dial pulse | Pulses LOW (~10 Hz) while dialing |
| 22 | 15 | Bell relay | HIGH = ring |

All input pins use the Pi's internal pull-up resistors (enabled by `raspi-gpio set N pu`).

---

## Hook Switch

The Type 500 has a spring-loaded hook switch with two contacts.

```
Pi GPIO 17 (pin 11) ──── Hook Switch Terminal A
Pi GND               ──── Hook Switch Terminal B
```

- Handset **on** hook → switch **closed** → GPIO reads **HIGH** (1)
- Handset **off** hook → switch **open** → GPIO reads **LOW** (0) via pull-up

---

## Rotary Dial

The dial has two contacts:
- **Pulse contact** (NC — normally closed): opens once per digit unit
- **Off-normal contact** (NO — normally open): closes during dial rotation (mutes the line)

Wire the **pulse contact**:

```
Pi GPIO 27 (pin 13) ──── Pulse contact Terminal A
Pi GND               ──── Pulse contact Terminal B
```

During dialing the contact opens (pulses LOW) once per digit at ~10 pulses/second:
- 1 pulse → digit 1
- 9 pulses → digit 9
- 10 pulses → digit 0

---

## Bell Relay

The Type 500 ringer requires ~90 V AC at 20 Hz, or can be operated with a relay
and an external ringer supply.  A simpler approach is to use a 5 V relay module:

```
Pi GPIO 22 (pin 15) ──── Relay IN (active-high module)
Pi 5 V  (pin 2)     ──── Relay VCC
Pi GND  (pin 6)     ──── Relay GND

Relay COM ──── Bell coil supply (+)
Relay NO  ──── Bell coil Terminal A
Bell coil Terminal B ──── Supply (-)
```

Drive the coil with an oscillating signal (the script toggles 2 s ON / 4 s OFF
for US ring cadence).  For the authentic mechanical ring the coil needs AC or a
square-wave driver circuit; a simple relay on DC will produce a single strike
per activation.  For a proper ring use a 555 timer circuit at 20 Hz driving the
relay, gated by GPIO 22.

---

## Audio (Handset)

The Type 500 handset has a 4-wire interface (2 wires mic, 2 wires speaker).

**Recommended**: use a SLIC (Subscriber Line Interface Circuit) board such as
the Tele-Pi or a Yate BH1 SLIC, which handles:
- Carbon microphone DC bias
- Hybrid (2-wire to 4-wire conversion)
- Impedance matching (600 Ω)

**Minimal alternative**: replace the carbon element with an electret capsule
(add a 2.2 kΩ bias resistor to 3.3 V) and wire directly to a USB audio adapter.

USB audio adapter → 3.5 mm TRRS:
```
Tip   (L)  → Earpiece speaker +
Ring1 (R)  → Earpiece speaker - (or GND)
Ring2 (Mic) → Microphone +
Sleeve (GND) → Microphone -
```

Find the ALSA device name with `aplay -l` and set `CFG[audio_dev]` accordingly.
