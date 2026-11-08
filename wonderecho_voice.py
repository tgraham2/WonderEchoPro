"""
WonderEcho Pro voice responder for Windows.

Reads command codes from the Pro's USB serial port (CH340, 115200 baud),
prints each code, and speaks a reply through the Pro's own speaker
(its USB audio device, "USB PnP Audio Device") using Windows text-to-speech.

Requirements:
    pip install pyserial pywin32

The Pro must be flashed with a communication-UART0 image. The RESPONSES
table below matches your build CI1302_英文_单麦_V00916_UART0_115200_2M.bin
(sfw2025111401393371252406). Other images use different codes, so update
the table if you flash a different one. UART1 images send no codes over USB.

Usage:
    python wonderecho_voice.py              # auto-detect port, speak on the Pro
    python wonderecho_voice.py --port COM3  # pick the port yourself
    python wonderecho_voice.py --list       # show ports and audio outputs
"""

import argparse
import sys

import serial
from serial.tools import list_ports
import win32com.client

BAUD = 115200
CH340_VID = 0x1A86          # WCH, maker of the CH340
DEFAULT_DEVICE = "USB PnP"  # how Windows names the Pro's audio device

# Commands from the Pro's command table, kept in sync with
# firmware/Command Word Broadcasting Protocol List_251108-claw.xlsx in this repo.
# Codes up to 0D FF are in the current build sfw2025111401393371252406;
# the 0E claw codes need a new build from the updated spreadsheet.
# Keyed by the two middle bytes of each frame: AA 55 <b2> <b3> FB.
# Each entry is (command word, spoken reply). Edit the replies freely.
RESPONSES = {
    (0x00, 0x00): ('GREETING', 'Welcome'),
    (0x00, 0x01): ('HAVE-A-REST', "I'm going to take a break"),
    (0x00, 0x02): ('HELLO-HI-WONDER', "I'm here"),
    (0x00, 0x03): ('TURN-UP-VOLUME', 'Volume increase'),
    (0x00, 0x04): ('TURN-DOWN-VOLUME', 'Volume decrease'),
    (0x00, 0x05): ('MAXIMUM-VOLUME', 'Maximum volume'),
    (0x00, 0x06): ('MEDIUM-VOLUME', 'Medium volume'),
    (0x00, 0x07): ('MINIMUM-VOLUME', 'Minimum volume'),
    (0x00, 0x08): ('START-BROADCASTING', 'Start Broadcasting'),
    (0x00, 0x09): ('STOP-BROADCASTING', 'Stop broadcasting'),
    (0x00, 0x10): ('HELLO', 'Hi'),
    (0x01, 0x00): ('MARCH', 'Marching'),
    (0x01, 0x01): ('GO-STRAIGHT', 'Going straight'),
    (0x01, 0x02): ('GO-BACKWARD', 'Going backward'),
    (0x01, 0x03): ('TURN-LEFT', 'Turning left'),
    (0x01, 0x04): ('TURN-RIGHT', 'Turning right'),
    (0x01, 0x05): ('LEAN-FORWARD', 'Lean forward'),
    (0x01, 0x06): ('LEAN-BACK', 'Lean back'),
    (0x01, 0x07): ('LEAN-LEFT', 'Lean left'),
    (0x01, 0x08): ('LEAN-RIGHT', 'Lean right'),
    (0x01, 0x09): ('STOP', 'Copy that'),
    (0x01, 0x0A): ('ATTENTION', 'Copy that'),
    (0x01, 0x0B): ('GET-DOWN', 'Copy that'),
    (0x01, 0x0C): ('SIT-DOWN', 'Copy that'),
    (0x01, 0x0D): ('SPEED-UP', 'Copy that'),
    (0x01, 0x0E): ('SLOW-DOWN', 'Copy that'),
    (0x01, 0x0F): ('RAISE-THE-BODY', 'Copy that'),
    (0x01, 0x10): ('LOWER-THE-BODY', 'Copy that'),
    (0x01, 0x11): ('MAKE-A-SOUND', 'Copy that'),
    (0x02, 0x00): ('TAKE-A-PICK', 'Click'),
    (0x02, 0x01): ('CAMERA-ON', 'Begin video record'),
    (0x02, 0x02): ('CAMERA-OFF', 'End video record'),
    (0x02, 0x03): ('TAKE-A-PICK', 'Click'),
    (0x03, 0x00): ('INTRODUCE-YOURSELF', "Hello, I'm Hiwonder, and I can talk and dance."),
    (0x03, 0x01): ('SHOW-A-SKILL', 'Watch closely'),
    (0x03, 0x02): ('SHAKE-HEAD', 'Copy that'),
    (0x03, 0x03): ('COMBAT MODE', 'Copy that'),
    (0x03, 0x04): ('SQUAT-DOWN', 'Copy that'),
    (0x03, 0x05): ('SHAKE-IT-OFF', 'Copy that'),
    (0x03, 0x06): ('DANCE', 'Copy that'),
    (0x03, 0x07): ('PUSH-UP', 'Copy that'),
    (0x03, 0x08): ('LEFT-FOOT-SHOOT', 'Copy that'),
    (0x03, 0x09): ('RIGHT-FOOT-SHOOT', 'Copy that'),
    (0x03, 0x0A): ('TWIST', 'Copy that'),
    (0x03, 0x0B): ('SIT-UP', 'Copy that'),
    (0x03, 0x0C): ('BOW', 'Copy that'),
    (0x03, 0x0D): ('SPREAD-THE-HANDS', 'Copy that'),
    (0x03, 0x0E): ('WAVE-HAND', 'Copy that'),
    (0x03, 0x0F): ('MARCH-IN-PLACE', 'Copy that'),
    (0x03, 0x10): ('FALL-AND-STAND-UP', 'Copy that'),
    (0x03, 0x11): ('STRUT', 'Copy that'),
    (0x03, 0x12): ('LEFT-HOOK', 'Copy that'),
    (0x03, 0x13): ('RIGHT-HOOK', 'Copy that'),
    (0x04, 0x00): ('SORTING-TIME', 'Copy that'),
    (0x04, 0x01): ('SORT-RED', 'Copy that'),
    (0x04, 0x02): ('SORT-GREEN', 'Copy that'),
    (0x04, 0x03): ('SORT-BLUE', 'Copy that'),
    (0x04, 0x04): ('SORT-YELLOW', 'Copy that'),
    (0x04, 0xFF): ('END-SORTING', 'Copy that'),
    (0x05, 0x00): ('PERFORM-READY', 'ready'),
    (0x05, 0x01): ('PERFORM-2-LEGS-STAND', 'perform two legs stand'),
    (0x05, 0x02): ('PERFORM-BOW', 'perform bow'),
    (0x05, 0x03): ('PERFORM-BOXING', 'perform boxing'),
    (0x05, 0x04): ('PERFORM-BOXING2', 'perform boxing two'),
    (0x05, 0x05): ('PERFORM-DEMO', 'perform demo'),
    (0x05, 0x06): ('PERFORM-GRAB', 'perform grab'),
    (0x05, 0x07): ('PERFORM-JUMP', 'perform jump'),
    (0x05, 0x08): ('PERFORM-KICK-LEFT', 'perform kick left'),
    (0x05, 0x09): ('PERFORM-KICK-RIGHT', 'perform kick right'),
    (0x05, 0x0A): ('PERFORM-LIE-DOWN', 'perform lie down'),
    (0x05, 0x0B): ('PERFORM-LOOK-DOWN', 'perform look down'),
    (0x05, 0x0C): ('PERFORM-MOONWALK', 'perform moonwalk'),
    (0x05, 0x0D): ('PERFORM-NOD', 'perform nod'),
    (0x05, 0x0E): ('PERFORM-PEE', 'perform pee'),
    (0x05, 0x0F): ('PERFORM-PRESS-UP', 'perform press up'),
    (0x05, 0x10): ('PERFORM-PUSH-UP', 'perform push up'),
    (0x05, 0x11): ('PERFORM-SHAKE-HANDS', 'perform shake hands'),
    (0x05, 0x12): ('PERFORM-SHAKE-HEAD', 'perform shake head'),
    (0x05, 0x13): ('PERFORM-SIT', 'perform sit'),
    (0x05, 0x14): ('PERFORM-SPACEWALK', 'perform spacewalk'),
    (0x05, 0x15): ('PERFORM-STAND', 'perform stand'),
    (0x05, 0x16): ('PERFORM-STRETCH', 'perform stretch'),
    (0x05, 0x17): ('PERFORM-UP-STAIRS-2', 'perform up stairs two'),
    (0x05, 0x18): ('PERFORM-UP-STAIRS-3', 'perform up stairs three'),
    (0x05, 0x19): ('PERFORM-WAVE', 'perform wave'),
    (0x05, 0x1A): ('PERFORM-PUSH-UP01', 'perform push up zero one'),
    (0x05, 0x1B): ('PERFORM-STAND-WITH-ARM', 'perform stand with arm'),
    (0x05, 0x1C): ('PERFORM-CLAMPING', 'perform clamping'),
    (0x05, 0x1D): ('PERFORM-ARM-TEST', 'perform arm test'),
    (0x06, 0x00): ('START-FACE-RECOGNITION', 'Start face recognition'),
    (0x06, 0xFF): ('END-FACE-RECOGNITION', 'Complete'),
    (0x07, 0x00): ('START-LABEL-RECOGNITION', 'Start label recognition'),
    (0x07, 0xFF): ('END-LABEL-RECOGNITION', 'Complete'),
    (0x08, 0x00): ('START-WASTE-SORTING', 'Start waste sorting'),
    (0x08, 0xFF): ('END-WASTE-SORTING', 'Complete'),
    (0x09, 0x00): ('START-COLOR-RECOGNITION', 'Start color recognition'),
    (0x09, 0xFF): ('END-COLOR-RECOGNITION', 'Complete'),
    (0x0A, 0x00): ('START-LINE-FOLLOWING', 'Start line following'),
    (0x0A, 0xFF): ('END-LINE-FOLLOWING', 'Complete'),
    (0x0B, 0x00): ('START-COLOR-TRACKING', 'Start color tracking'),
    (0x0B, 0xFF): ('END-COLOR-TRACKING', 'Complete'),
    (0x0C, 0x00): ('START-OBSTACLE-AVOIDANCE', 'Start obstacle avoidance'),
    (0x0C, 0xFF): ('END-OBSTACLE-AVOIDANCE', 'Complete'),
    (0x0D, 0x00): ('START-OBJECT-TRACKING', 'Start object tracking'),
    (0x0D, 0x01): ('PICK-COLOR', 'Color identified'),
    (0x0D, 0xFF): ('END-OBJECT-TRACKING', 'Complete'),
    # Claw commands (added Nov 8; need a new firmware build to be recognized)
    (0x0E, 0x00): ('OPEN-THE-CLAW', 'Opening the claw'),
    (0x0E, 0x01): ('CLOSE-THE-CLAW', 'Closing the claw'),
    (0x0E, 0x02): ('RAISE-THE-CLAW', 'Raising the claw'),
    (0x0E, 0x03): ('LOWER-THE-CLAW', 'Lowering the claw'),
    (0x0E, 0x04): ('EXTEND-THE-CLAW', 'Extending the claw'),
    (0x0E, 0x05): ('RETRACT-THE-CLAW', 'Retracting the claw'),
}

# Codes that also change the speaking volume.
VOLUME_ACTIONS = {
    (0x00, 0x03): "up",
    (0x00, 0x04): "down",
    (0x00, 0x05): 100,   # MAXIMUM-VOLUME
    (0x00, 0x06): 60,    # MEDIUM-VOLUME
    (0x00, 0x07): 25,    # MINIMUM-VOLUME
}
VOLUME_STEP = 15

SVSF_ASYNC = 1         # don't block while speaking
SVSF_PURGE = 2         # cut off any reply still playing


class Speaker:
    """Windows SAPI voice, routed to the Pro's USB audio device if found."""

    def __init__(self, device_hint):
        self.voice = win32com.client.Dispatch("SAPI.SpVoice")
        outputs = self.voice.GetAudioOutputs()
        chosen = None
        for i in range(outputs.Count):
            token = outputs.Item(i)
            if device_hint.lower() in token.GetDescription().lower():
                chosen = token
                break
        if chosen is not None:
            self.voice.AudioOutput = chosen
            print(f"Speaking through: {chosen.GetDescription()}")
        else:
            print(f"No audio output matching '{device_hint}'; "
                  "using the Windows default. Run with --list to see outputs.")

    def say(self, text):
        self.voice.Speak(text, SVSF_ASYNC | SVSF_PURGE)

    def set_volume(self, percent):
        self.voice.Volume = max(0, min(100, percent))

    def change_volume(self, action):
        if action == "up":
            self.set_volume(self.voice.Volume + VOLUME_STEP)
        elif action == "down":
            self.set_volume(self.voice.Volume - VOLUME_STEP)
        else:
            self.set_volume(action)


def find_port():
    """Return the first CH340 port, or None."""
    for p in list_ports.comports():
        if p.vid == CH340_VID:
            return p.device
    return None


def list_everything():
    print("Serial ports:")
    for p in list_ports.comports():
        tag = "  <- CH340" if p.vid == CH340_VID else ""
        print(f"  {p.device}: {p.description}{tag}")
    print("\nAudio outputs:")
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    outputs = voice.GetAudioOutputs()
    for i in range(outputs.Count):
        print(f"  {outputs.Item(i).GetDescription()}")


def frames(ser):
    """Yield 5-byte frames AA 55 xx xx FB, resyncing on noise."""
    buf = bytearray()
    while True:
        buf += ser.read(ser.in_waiting or 1)
        while True:
            start = buf.find(b"\xAA\x55")
            if start < 0:
                del buf[:-1]          # keep a trailing AA in case 55 follows
                break
            if len(buf) - start < 5:
                del buf[:start]       # wait for the rest of the frame
                break
            frame = bytes(buf[start:start + 5])
            if frame[4] != 0xFB:
                del buf[:start + 1]   # false start; look again
                continue
            del buf[:start + 5]
            yield frame


def main():
    ap = argparse.ArgumentParser(description="Speak replies to WonderEcho Pro codes.")
    ap.add_argument("--port", help="COM port, e.g. COM3 (default: auto-detect CH340)")
    ap.add_argument("--device", default=DEFAULT_DEVICE,
                    help=f"part of the audio output name (default: '{DEFAULT_DEVICE}')")
    ap.add_argument("--list", action="store_true", help="list ports and audio outputs")
    args = ap.parse_args()

    if args.list:
        list_everything()
        return

    port = args.port or find_port()
    if not port:
        sys.exit("No CH340 port found. Plug in the Pro or pass --port COMx.")

    speaker = Speaker(args.device)

    try:
        ser = serial.Serial(port, BAUD, timeout=0.1)
    except serial.SerialException as e:
        sys.exit(f"Can't open {port}: {e}\nClose any serial terminal using it.")

    print(f"Listening on {port} at {BAUD}. Say 'Hello Hiwonder'. Ctrl+C to quit.")
    try:
        for frame in frames(ser):
            code = (frame[2], frame[3])
            name, reply = RESPONSES.get(code, ("(unknown code)", None))
            print(f"{frame.hex(' ').upper()}  {name:<26} ->  {reply or '(no reply)'}")
            if code in VOLUME_ACTIONS:
                speaker.change_volume(VOLUME_ACTIONS[code])
            if reply:
                speaker.say(reply)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
