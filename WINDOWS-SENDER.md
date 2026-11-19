# Windows microphone sender

Use this instead of the browser microphone page on each Windows computer.
Chrome may be minimized or closed. The main **hub program must still run**.

## On the hub computer

1. Start the hub as usual and open http://localhost:8787.
2. Disconnect that computer's old browser mic to avoid duplicate inputs.
3. Double-click **Start Windows Mic Sender.cmd**, or run **Cancel Group Mics Sender.exe**.
4. Leave Hub address as **http://localhost:8787**.
5. Enter the current six-digit code from the hub dashboard, a mic name, and
   select your physical microphone (prefer its Windows WASAPI entry).
6. Click **Connect microphone**. Click **Hide to tray**, minimize the window,
   or close it with X. Audio continues. The dashboard still shows its level.

Keep the hub output set to **CABLE Input / WASAPI**, and Discord's microphone
set to **CABLE Output**. The sender doesn't replace the hub or virtual cable.

## On another Windows computer

1. Copy **Cancel Group Mics Sender.exe** and the hub's **ca.crt** to that computer.
   The provided ZIP contains both. Extract it first. Python is not required.
2. Run the executable. Enter **https://HOST-IP:8788** as the Hub address.
   Use the IP displayed on the hub dashboard, e.g. `https://192.168.1.20:8788`.
   If you configured a different HTTPS port, use that port.
3. Click **Browse** under Hub public CA file and select the included **ca.crt**.
   This verifies the TLS connection without installing a system-wide trusted CA.
   Copy this file from your own hub; never use someone else's CA. Check its
   fingerprint against the hub dashboard if downloading it over the network.
4. Enter the current room code, choose a physical mic and click Connect.
5. Disconnect the old browser mic page for this device, then minimize/close Chrome.

The ZIP includes only the public certificate, never the hub's private keys.
For a different hub, download its public CA from its setup page. Windows desktop
microphone access must be enabled. Don't select CABLE Output as your physical mic.

## Tray controls

- Right-click the green waveform icon beside the clock (possibly inside the ^
  overflow menu). Choose **Show microphone sender**, **Mute / unmute**,
  **Disconnect**, or **Quit sender**.
- Closing the window hides it. **Disconnect** releases the mic; **Quit sender**
  releases the mic and exits. Local mute sends silence rather than your voice.
- The window shows input level, selected/on-air state, host mute and output status.
- Wi-Fi interruptions retry every eight seconds. Pairing rejection (wrong code,
  room full, or removal by host) stops retries so you can fix the settings.
- If the hub restarts and changes its room code, reopen the sender and enter the
  new code. Settings are locked while connected: Disconnect before editing.
- Hub address, mic name, mic choice and CA path are remembered in
  `%LOCALAPPDATA%\CancelGroupMics\sender.json`. Room codes aren't saved.
- This does not start automatically on Windows login or connect without your
  click. Each sender counts toward the hub's four-mic limit.
- Sleep, shutdown and loss of the physical mic can still interrupt capture;
  minimizing a window or browser cannot suspend this native audio worker.

## Verification

Tested actual Razer Seiren V3 Mini capture through an isolated hub with the sender
window hidden to tray: six seconds of continued fresh audio, 150 packets buffered,
zero rejected packets. The test did not send audio into the live call. Automated
tests cover PCM framing/resampling, room rejection, capture cleanup, mute/unmute,
and reconnection following an interrupted WebSocket. This is not a guarantee for
every Windows sound driver or network configuration.

## Building from source

Run **Build Windows Sender.cmd** with Python 3.11+ and the project's venv installed.
It installs sender dependencies and PyInstaller, then builds the standalone EXE
in `dist`. For source execution, use `requirements-sender.txt` and `tray_sender.py`.
