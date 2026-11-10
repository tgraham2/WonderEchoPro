#!/usr/bin/env python3
"""
PuppyPi claw control by voice (WonderEcho Pro) or keyboard.

Runs on the PuppyPi's Raspberry Pi (ROS1 image). Reads the Pro's command
codes from its USB serial port and moves the robot arm:

    servo 9  = claw (open / close)
    servo 10 = arm up / down
    servo 11 = arm out / back

Servos are driven with Hiwonder's own setServoPulse(id, pulse, time_ms)
from /home/ubuntu/software/puppypi_control, the same call the arm games use.

Usage:
    python3 claw_voice_control.py --keys      # test with the keyboard first
    python3 claw_voice_control.py             # voice control from the Pro
    python3 claw_voice_control.py --port /dev/ttyUSB0
    python3 claw_voice_control.py --keys --dry-run   # no servos, prints only

Keys mode: o=open  c=close  u=up  d=down  e=extend  r=retract
           s=start pose  p=print positions  q=quit  (press Enter after each)

The claw voice codes (AA 55 0E 00..05 FB) need the firmware built from
"Command Word Broadcasting Protocol List_251108-claw.xlsx". Until then,
use --keys to test and tune the settings below.
"""

import argparse
import sys
import time

# ---------------------------------------------------------------- settings
# Pulse values are in microseconds-style units (Hiwonder PWM servos, ~500-2500).
# Start pose is Hiwonder's arm startup pose from the PuppyPi arm course.

CLAW, LIFT, REACH = 9, 10, 11

START = {CLAW: 1500, LIFT: 800, REACH: 850}

CLAW_OPEN = 900      # gesture game maps spread fingers to 900
CLAW_CLOSED = 1500   # and pinched fingers to 1500 -- check on your robot

# Safe range for each servo. Deliberately narrow to start with; widen
# them once you've seen how far each joint can go without hitting anything.
LIMITS = {CLAW: (900, 1500), LIFT: (500, 1100), REACH: (550, 1150)}

STEP = 100           # pulse change per up/down/extend/retract command
MOVE_MS = 400        # time for each move

# Direction of travel. If "up" moves the arm down, change RAISE_DIR to -1.
# If "extend" pulls the arm back, change EXTEND_DIR to -1.
RAISE_DIR = +1
EXTEND_DIR = +1

BAUD = 115200
CH340_VID = 0x1A86
DEFAULT_PORT = "/dev/ttyUSB0"

# Voice codes: the two middle bytes of AA 55 <b2> <b3> FB
CODES = {
    (0x0E, 0x00): "open",
    (0x0E, 0x01): "close",
    (0x0E, 0x02): "up",
    (0x0E, 0x03): "down",
    (0x0E, 0x04): "extend",
    (0x0E, 0x05): "retract",
}

KEYS = {"o": "open", "c": "close", "u": "up", "d": "down",
        "e": "extend", "r": "retract", "s": "start"}

# ---------------------------------------------------------------- arm


class Arm:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.pos = dict(START)
        if dry_run:
            self._send = lambda sid, pulse, ms: None
        else:
            sys.path.append("/home/ubuntu/software/puppypi_control/")
            try:
                from servo_controller import setServoPulse
            except ImportError as e:
                sys.exit(f"Can't load Hiwonder's servo_controller ({e}).\n"
                         "Run this on the PuppyPi, or add --dry-run to test without servos.")
            self._send = setServoPulse

    def move(self, sid, pulse, ms=MOVE_MS):
        lo, hi = LIMITS[sid]
        clamped = max(lo, min(hi, int(pulse)))
        note = "" if clamped == int(pulse) else f"  (limit {lo}-{hi})"
        self._send(sid, clamped, ms)
        self.pos[sid] = clamped
        print(f"  servo {sid} -> {clamped}{note}")
        time.sleep(ms / 1000.0)

    def start_pose(self):
        for sid in (CLAW, LIFT, REACH):
            self.move(sid, START[sid], 500)

    def do(self, action):
        if action == "open":
            self.move(CLAW, CLAW_OPEN)
        elif action == "close":
            self.move(CLAW, CLAW_CLOSED)
        elif action == "up":
            self.move(LIFT, self.pos[LIFT] + STEP * RAISE_DIR)
        elif action == "down":
            self.move(LIFT, self.pos[LIFT] - STEP * RAISE_DIR)
        elif action == "extend":
            self.move(REACH, self.pos[REACH] + STEP * EXTEND_DIR)
        elif action == "retract":
            self.move(REACH, self.pos[REACH] - STEP * EXTEND_DIR)
        elif action == "start":
            self.start_pose()

    def show(self):
        print(f"  claw={self.pos[CLAW]}  lift={self.pos[LIFT]}  reach={self.pos[REACH]}")

# ---------------------------------------------------------------- voice


def find_port():
    from serial.tools import list_ports
    for p in list_ports.comports():
        if p.vid == CH340_VID:
            return p.device
    return DEFAULT_PORT


def frames(ser):
    """Yield 5-byte frames AA 55 xx xx FB, resyncing on noise."""
    buf = bytearray()
    while True:
        buf += ser.read(ser.in_waiting or 1)
        while True:
            start = buf.find(b"\xAA\x55")
            if start < 0:
                del buf[:-1]
                break
            if len(buf) - start < 5:
                del buf[:start]
                break
            frame = bytes(buf[start:start + 5])
            if frame[4] != 0xFB:
                del buf[:start + 1]
                continue
            del buf[:start + 5]
            yield frame


def run_voice(arm, port):
    import serial
    try:
        ser = serial.Serial(port, BAUD, timeout=0.1)
    except serial.SerialException as e:
        sys.exit(f"Can't open {port}: {e}\n"
                 "Is another program (e.g. Hiwonder's voice demo) using the Pro?")
    print(f"Listening on {port}. Say 'Hello Hiwonder', then a claw command. Ctrl+C to quit.")
    try:
        for frame in frames(ser):
            action = CODES.get((frame[2], frame[3]))
            print(f"{frame.hex(' ').upper()}  ->  {action or '(not a claw command)'}")
            if action:
                arm.do(action)
    finally:
        ser.close()


def run_keys(arm):
    print("Keys: o=open c=close u=up d=down e=extend r=retract s=start p=print q=quit")
    while True:
        try:
            key = input("> ").strip().lower()[:1]
        except EOFError:
            break
        if key == "q":
            break
        if key == "p":
            arm.show()
        elif key in KEYS:
            print(KEYS[key])
            arm.do(KEYS[key])
        elif key:
            print("  unknown key")


def main():
    ap = argparse.ArgumentParser(description="PuppyPi claw control by voice or keyboard.")
    ap.add_argument("--keys", action="store_true", help="control from the keyboard")
    ap.add_argument("--port", help=f"Pro serial port (default: auto-detect, else {DEFAULT_PORT})")
    ap.add_argument("--dry-run", action="store_true", help="print moves without driving servos")
    args = ap.parse_args()

    arm = Arm(dry_run=args.dry_run)
    print("Moving to start pose")
    arm.start_pose()
    try:
        if args.keys:
            run_keys(arm)
        else:
            run_voice(arm, args.port or find_port())
    except KeyboardInterrupt:
        pass
    print("\nStopped.")


if __name__ == "__main__":
    main()
