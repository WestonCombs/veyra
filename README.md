# Veyra — Network Microphone Hub

A Windows tray application that connects up to four microphones to one host, selects a single microphone for a shared voice call, and routes the audio through a virtual audio cable.

## Features

- Native Matrix-inspired dashboard, host and guest roles, and system tray operation.
- Four microphone slots with audio-level borders, selected-source highlighting, and mute states.
- Local-only capture fast path; timestamped buffering and automatic selection for multiple or remote microphones.
- Room-code discovery on the LAN and copyable invite links.
- TLS host verification using an exported public CA certificate.
- Automatic preferences, optional Windows startup, and configurable audio output.

## Run from source

Requires Windows and Python 3.11 or later.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-sender.txt
.\.venv\Scripts\python.exe desktop_app.py
```

On the host, install VB-CABLE from https://vb-audio.com/Cable/. Select **CABLE Input / Windows WASAPI** in advanced settings. In Discord or the call application, choose **CABLE Output** (or the recording-device name you assigned) as the microphone. Keep playback on headphones.

Enable profile selection in Settings to switch to Host. Press Start or the first slot's plus button and select a local microphone or invite another machine. Guests enter the room code or full invite link, choose their physical microphone, and join muted.

For remote guests, the host exports its certificate from advanced settings; guests select that public .crt file in their app. Each host generates its own certificate and private key locally. Certificates, keys, personal preferences and generated data are excluded from this repository.

Room codes use UDP discovery on the same LAN (48789). Audio transport uses TCP 8787/8788. A local IP invite does not provide Internet traversal: another network requires a reachable host or shared VPN.

## Build the Windows executable

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\Build Veyra.cmd
```

The executable is generated in `dist/Veyra.exe`. Closing its window leaves it in the tray; Quit releases capture and exits.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-sender.txt
.\.venv\Scripts\python.exe -m pytest -q tests
node --test tests/test_capture.cjs
```

The current suite covers audio selection, continuity, native capture routing, mute, reconnection, discovery and protocol checks. Real-device behavior still depends on Windows audio drivers and network conditions. This is microphone switching, not source separation: simultaneous voices and acoustic speaker feedback are not eliminated.

## Project layout

- `desktop_app.py`: current native application.
- `michub/`: audio engine, host, senders, protocol, UI theme and dialogs.
- `assets/`: application icon.
- `tests/`: automated checks.
- `static/`, `run.py`, `tray_sender.py`: earlier browser hub and standalone sender retained as project history; use desktop_app.py for the current application.
