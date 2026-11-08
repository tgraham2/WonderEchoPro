# WonderEcho Pro

Tools and notes for the Hiwonder WonderEcho Pro (CI1302 voice module).

## How the Pro works

- The **CI1302 chip listens**: it recognizes the wake word and commands, then sends a 5-byte code over its USB serial port (CH340, 115200 baud), e.g. `AA 55 00 02 FB`.
- The **host computer speaks**: the Pro's speaker is driven by its USB audio device ("USB PnP Audio Device"), not by the CI1302. Firmware prompts never reach the speaker, so a faint hiss with no speech is normal.

## Firmware

Flash a **communication-UART0** image. On the Pro, the CH340 USB port is wired to chip UART0; UART1 images send no codes over USB.

Current build: `CI1302_英文_单麦_V00916_UART0_115200_2M.bin` from ChipIntelli build `sfw2025111401393371252406` (1,777,145 bytes). Its command table is `Command Word Broadcasting Protocol List_251113-1003 (1).xlsx`.

Flashing with `PACK_UPDATE_TOOL.exe` (Windows):

1. Chip **CI1302**, page **Firmware Upgrade**, select the `.bin`.
2. Tick **Force update all partitions** and **Erase NV**.
3. Set the COM port's baud to **921600** and tick it.
4. Press **RST** on the Pro and wait for `device:update success`.
5. Untick the port and **close the tool**. It holds the COM port while open.

## wonderecho_voice.py

Reads the Pro's codes on Windows and speaks a reply through the Pro's speaker using Windows text-to-speech.

```
python -m pip install pyserial pywin32
python wonderecho_voice.py --list        # show COM ports and audio outputs
python wonderecho_voice.py               # auto-detect the Pro and run
python wonderecho_voice.py --port COM10  # choose the port
```

Edit the `RESPONSES` table to change replies. Replies can change anytime; changing command words or codes means editing the spreadsheet, rebuilding on the ChipIntelli platform, and reflashing.

Only one program can use a COM port at a time, so close serial monitors and the flash tool before running the script.
