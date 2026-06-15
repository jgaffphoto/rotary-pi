---

## What's in the diagrams

### `bell_simple.pdf` — Option 1: Single-strike relay
Simple control path: **GPIO 22 → 5 V relay module IN → relay NO contact → bell coil → 12 V supply**. The script's 2 s on/4 s off cadence energises and de-energises the coil, producing one clapper strike each time. Includes the mandatory flyback diode (D1, 1N4007) across the bell coil.

### `bell_555.pdf` — Option 2: Authentic 20 Hz mechanical ring
Full circuit for a proper oscillating ring:

| Stage | Component | Purpose |
|---|---|---|
| Gate | GPIO 22 → 555 pin 4 (RST) + 10 kΩ pull-up | HIGH = 555 runs; LOW = silent |
| Oscillator | NE555 + R1=1 kΩ, R2=36 kΩ, C1=1 µF | ~19.7 Hz square wave |
| Noise filter | C2=0.1 µF on pin 5 (CTL) | Stable frequency |
| Driver | R3=1 kΩ + Q1 2N2222 NPN | Switches relay coil current |
| Protection | D1 1N4007 across relay coil | Clamps inductive back-EMF |
| Load | Relay NO contact → bell coil → 12 V | Clapper oscillates at 20 Hz |

The 3.3 V GPIO drives the 555 RESET pin directly — no level-shifter needed since the 555's reset threshold is ~0.7 V on a 5 V supply. The pull-up resistor prevents spurious ringing if GPIO 22 floats at boot.
