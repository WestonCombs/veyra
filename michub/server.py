import argparse
import asyncio
import contextlib
import json
import logging
import math
import secrets
import ssl
import struct
import time
from pathlib import Path
from urllib.parse import urlsplit
import numpy as np
from aiohttp import web, WSMsgType
from .audio import Mixer, AudioOutput, Engine, BLOCK, MAX_DEVICES
from .certificates import lan_addresses, prepare

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
LOG = logging.getLogger("michub")


class Hub:
    def __init__(self, http_port=8787, https_port=8788):
        self.mixer, self.output = Mixer(), AudioOutput()
        self.engine = Engine(self.mixer, self.output)
        self.code = f"{secrets.randbelow(1000000):06d}"
        self.token = secrets.token_urlsafe(32)
        self.http_port, self.https_port = http_port, https_port
        self.addresses = lan_addresses()
        self.sockets = {}
        self.attempts = {}
        self.fingerprint = ""
        self.stop_requested = asyncio.Event()

    def local(self, request):
        host = request.host.split(":")[0].lower()
        return request.remote in ("127.0.0.1", "::1") and host in ("localhost", "127.0.0.1", "[::1]")

    def authorize(self, request):
        if not self.local(request) or not secrets.compare_digest(request.headers.get("X-Hub-Token", ""), self.token):
            raise web.HTTPForbidden(text="Host controls are available only on the hub computer.")

    async def index(self, request):
        if not self.local(request):
            raise web.HTTPFound("/join")
        html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__HUB_TOKEN__", self.token)
        return web.Response(text=html, content_type="text/html")

    async def join(self, request):
        if not request.secure and not self.local(request):
            raise web.HTTPFound("/setup")
        return web.FileResponse(STATIC / "join.html")

    async def setup(self, request):
        html = (STATIC / "setup.html").read_text(encoding="utf-8").replace("__HTTPS_PORT__", str(self.https_port)).replace("__FINGERPRINT__", self.fingerprint)
        return web.Response(text=html, content_type="text/html")

    async def certificate(self, request):
        return web.FileResponse(ROOT / ".runtime" / "ca.crt", headers={"Content-Disposition": 'attachment; filename="cancel-group-mics-ca.crt"'})

    async def state(self, request):
        self.authorize(request)
        return web.json_response({**self.mixer.snapshot(), "output": self.output.snapshot(),
            "code": self.code, "capacity": MAX_DEVICES, "engine_error": self.engine.error,
            "join_urls": [f"https://{a}:{self.https_port}/join#code={self.code}" for a in self.addresses],
            "setup_urls": [f"http://{a}:{self.http_port}/setup#code={self.code}" for a in self.addresses],
            "fingerprint": self.fingerprint})

    async def outputs(self, request):
        self.authorize(request)
        try:
            devices = await asyncio.to_thread(self.output.devices)
            return web.json_response({"devices": devices})
        except Exception as exc:
            return web.json_response({"devices": [], "error": str(exc)}, status=503)

    async def control(self, request):
        self.authorize(request)
        try:
            data = await request.json()
            action = data.get("action")
            if action == "output_start":
                device = data.get("device")
                if type(device) is not int or device not in [d["id"] for d in self.output.devices()]:
                    raise ValueError("Choose an available output device.")
                await asyncio.to_thread(self.output.start, device)
            elif action == "output_stop":
                await asyncio.to_thread(self.output.stop)
            elif action == "disconnect":
                ws = self.sockets.get(data.get("id"))
                if ws:
                    await ws.close(code=1000, message=b"Disconnected by host")
            elif action == "rotate_code":
                self.code = f"{secrets.randbelow(1000000):06d}"
            elif action == "shutdown":
                self.stop_requested.set()
            else:
                with self.mixer.lock:
                    if action == "master":
                        if type(data.get("muted")) is not bool:
                            raise ValueError("Invalid mute setting.")
                        self.mixer.master_muted = data["muted"]
                    elif action == "pin":
                        device_id = data.get("id")
                        if device_id is not None and device_id not in self.mixer.devices:
                            raise ValueError("That microphone is no longer connected.")
                        self.mixer.pinned = device_id
                    elif action == "device":
                        d = self.mixer.devices.get(data.get("id"))
                        if not d:
                            raise ValueError("That microphone is no longer connected.")
                        if "muted" in data:
                            if type(data["muted"]) is not bool:
                                raise ValueError("Invalid mute setting.")
                            d.muted = data["muted"]
                        if "gain_db" in data:
                            gain = float(data["gain_db"])
                            if not math.isfinite(gain) or not -18 <= gain <= 18:
                                raise ValueError("Mic trim must be between -18 and +18 dB.")
                            d.gain_db = gain
                    elif action == "settings":
                        ranges = {"delay_ms": (80, 1000), "gate_db": (-70, -20), "margin_db": (1, 12), "hold_ms": (40, 500)}
                        settings = {}
                        for name, (lo, hi) in ranges.items():
                            if name in data:
                                val = float(data[name])
                                if not math.isfinite(val) or not lo <= val <= hi:
                                    raise ValueError(f"{name} must be between {lo} and {hi}.")
                                settings[name] = val
                        for name, value in settings.items():
                            setattr(self.mixer, name, value)
                    else:
                        raise ValueError("Unknown control.")
            return web.json_response({"ok": True})
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)

    async def socket(self, request):
        if not request.secure and not self.local(request):
            raise web.HTTPForbidden(text="Remote microphones require HTTPS. Open /setup first.")
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            raise web.HTTPForbidden(text="Origin mismatch")
        ip = request.remote
        now = time.monotonic()
        history = [t for t in self.attempts.get(ip, []) if now - t < 60]
        if len(history) >= 12:
            raise web.HTTPTooManyRequests(text="Too many pairing attempts. Wait one minute.")
        history.append(now)
        self.attempts[ip] = history
        if len(self.attempts) > 512:
            self.attempts = {k: v for k, v in self.attempts.items() if now-v[-1] < 60}
        ws = web.WebSocketResponse(heartbeat=10, max_msg_size=8192, compress=False)
        await ws.prepare(request)
        device_id = None
        try:
            msg = await ws.receive(timeout=10)
            if msg.type != WSMsgType.TEXT:
                raise ValueError("Pair with a room code first.")
            hello = json.loads(msg.data)
            if not secrets.compare_digest(str(hello.get("code", "")), self.code):
                raise ValueError("That room code doesn't match. Check the host screen.")
            name = str(hello.get("name", "Microphone")).strip()[:40] or "Microphone"
            device_id = secrets.token_hex(8)
            self.mixer.add(device_id, name)
            self.sockets[device_id] = ws
            await ws.send_json({"type": "welcome", "id": device_id})
            last_status = 0
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("type") == "ping":
                        await ws.send_json({"type": "pong", "client": data.get("client"), "server": time.perf_counter()*1000})
                    elif data.get("type") == "rename":
                        with self.mixer.lock:self.mixer.devices[device_id].name=str(data.get("name", "Microphone")).strip()[:40] or "Microphone"
                    elif data.get("type") == "mute":
                        with self.mixer.lock:
                            self.mixer.devices[device_id].muted = bool(data.get("muted"))
                elif msg.type == WSMsgType.BINARY:
                    if len(msg.data) != 8 + BLOCK*2:
                        raise ValueError("Invalid audio frame.")
                    timestamp = struct.unpack_from("<d", msg.data)[0]
                    samples = np.frombuffer(msg.data, dtype="<i2", offset=8).astype(np.float32) / 32768
                    with self.mixer.lock:
                        self.mixer.devices[device_id].push(timestamp, samples, time.perf_counter()*1000)
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
                if time.monotonic() - last_status > 0.1:
                    d = self.mixer.devices[device_id]
                    await ws.send_json({"type": "status", "active": self.mixer.active == device_id and not self.mixer.master_muted and d.level_db > self.mixer.gate_db,
                        "muted": d.muted, "master_muted": self.mixer.master_muted,
                        "output_running": self.output.snapshot()["running"], "level_db": d.level_db, "devices": self.mixer.snapshot()["devices"]})
                    last_status = time.monotonic()
        except (ValueError, TypeError, AttributeError, asyncio.TimeoutError) as exc:
            with contextlib.suppress(ConnectionError, RuntimeError):
                await ws.send_json({"type": "error", "message": str(exc) or "Pairing timed out."})
                await ws.close(code=1008)
        finally:
            if device_id:
                self.sockets.pop(device_id, None)
                self.mixer.remove(device_id)
        return ws


@web.middleware
async def headers(request, handler):
    response = await handler(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "microphone=(self), camera=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response


def create_app(hub):
    app = web.Application(middlewares=[headers], client_max_size=16384)
    app.router.add_get("/", hub.index)
    app.router.add_get("/join", hub.join)
    app.router.add_get("/setup", hub.setup)
    app.router.add_get("/ca.crt", hub.certificate)
    app.router.add_get("/api/state", hub.state)
    app.router.add_get("/api/outputs", hub.outputs)
    app.router.add_post("/api/control", hub.control)
    app.router.add_get("/ws", hub.socket)
    app.router.add_static("/static/", STATIC, show_index=False)
    async def cleanup(app):
        for ws in list(hub.sockets.values()):
            await ws.close(code=1001, message=b"Host stopped")
        if hub.engine.thread.is_alive():
            hub.engine.stop()
    app.on_cleanup.append(cleanup)
    return app


async def serve(args):
    hub = Hub(args.port, args.tls_port)
    hub.fingerprint = prepare(ROOT / ".runtime", hub.addresses)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(ROOT / ".runtime" / "server.pem", ROOT / ".runtime" / "server-key.pem")
    runner = web.AppRunner(create_app(hub), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, "0.0.0.0", args.port).start()
        await web.TCPSite(runner, "0.0.0.0", args.tls_port, ssl_context=tls).start()
        hub.engine.thread.start()
        print(f"\n  CANCEL GROUP MICS\n  Host dashboard: http://localhost:{args.port}\n  Room code: {hub.code}", flush=True)
        for a in hub.addresses:
            print(f"  Device setup: http://{a}:{args.port}/setup", flush=True)
        print("  Press Ctrl+C to stop. Audio output stays off until you start it.\n", flush=True)
        if not args.no_browser:
            import webbrowser
            webbrowser.open(f"http://localhost:{args.port}")
        await hub.stop_requested.wait()
    finally:
        await runner.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Four local microphones, one voice output.")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--tls-port", type=int, default=8788)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        # Double-clicking the launcher again should reopen the existing hub.
        if not args.no_browser:
            import urllib.request
            import webbrowser
            url = f"http://localhost:{args.port}"
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    existing = response.read(65536).decode("utf-8")
                if "Cancel Group Mics · Host" in existing and 'name="hub-token"' in existing:
                    print(f"The hub is already running at {url}")
                    webbrowser.open(url)
                    return
            except (OSError, UnicodeError):
                pass
        print(f"Could not start the hub: {exc}. Check whether another copy is running.")
        raise SystemExit(1)
