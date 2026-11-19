"""Native capture and hub protocol, independent of the tray/window lifecycle."""
import asyncio
import contextlib
import ctypes
import sys
import ssl
import struct
import threading
import time
from urllib.parse import urlsplit, urlunsplit
import aiohttp
import numpy as np


def socket_url(address):
    value = urlsplit(address.strip())
    if value.scheme not in ('http', 'https') or not value.hostname or value.username or value.password:
        raise ValueError('Enter an http://localhost:8787 or https://HOST:8788 address.')
    if value.scheme == 'http' and value.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Other computers require HTTPS and the hub public CA certificate.')
    return urlunsplit(('wss' if value.scheme == 'https' else 'ws', value.netloc, '/ws', '', ''))


def pcm_packet(samples, timestamp, rate):
    mono = np.asarray(samples, dtype=np.float32)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    if rate != 48000:
        mono = np.interp(np.arange(960)*rate/48000, np.arange(len(mono)), mono)
    if len(mono) != 960:
        raise ValueError('Capture must provide exactly 20 ms of audio.')
    return struct.pack('<d', timestamp) + (np.clip(mono, -1, 1)*32767).astype('<i2').tobytes()


class PairingError(Exception):
    pass


class NativeSender:
    def __init__(self, notify, stream_factory=None):
        self.notify = notify
        self.stream_factory = stream_factory
        self.thread = None
        self.loop = None
        self.task = None
        self.stopping = threading.Event()
        self.muted = False
        self.name = None
        self.offset = 0
        self.last_audio = 0
        self.retry_delay = 8

    def start(self, address, code, name, device=None, ca_file=''):
        if self.thread and self.thread.is_alive():
            raise ValueError('Disconnect before changing connection settings.')
        self.name = name
        url = socket_url(address)
        if len(code) != 6 or not code.isdigit():
            raise ValueError('Enter the six-digit room code from the host dashboard.')
        tls = ssl.create_default_context(cafile=ca_file or None) if url.startswith('wss:') else None
        self.stopping.clear()
        self.thread = threading.Thread(target=self._thread, args=(url, code, name, device, tls), daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.loop and self.task:
            with contextlib.suppress(RuntimeError):
                self.loop.call_soon_threadsafe(self.task.cancel)

    def _thread(self, *args):
        # WASAPI uses COM on the thread that opens the capture stream.
        com_initialized = False
        if sys.platform == 'win32':
            com_initialized = ctypes.windll.ole32.CoInitializeEx(None, 0) in (0, 1)
        try:
            asyncio.run(self.run(*args))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.notify('status', str(exc))
        finally:
            if com_initialized:
                ctypes.windll.ole32.CoUninitialize()
            self.loop = self.task = None
            self.notify('ended', None)

    async def run(self, url, code, name, device, tls):
        self.loop = asyncio.get_running_loop()
        self.task = asyncio.current_task()
        while not self.stopping.is_set():
            try:
                self.notify('status', 'Connecting…')
                await self.connection(url, code, name, device, tls)
            except PairingError as exc:
                self.notify('status', str(exc))
                return  # Wrong code/full room/host removal must not retry forever.
            except (ssl.SSLError, aiohttp.ClientConnectorCertificateError) as exc:
                self.notify('status', 'Certificate not trusted. Select the correct hub CA file. ' + str(exc))
                return
            except Exception as exc:
                self.notify('status', f'Connection interrupted: {exc}. Retrying in 8 seconds…')
            if not self.stopping.is_set():
                await asyncio.sleep(self.retry_delay)

    async def connection(self, url, code, name, device, tls):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=8)) as session:
            async with session.ws_connect(url, ssl=tls if tls is not None else True, heartbeat=10, max_msg_size=8192) as ws:
                await ws.send_json({'code': code, 'name': name[:40] or 'Windows mic'})
                hello = await ws.receive_json(timeout=10)
                if hello.get('type') != 'welcome':
                    raise PairingError(hello.get('message', 'Pairing failed.'))
                # Initial probes before starting capture. Receive status messages
                # interleaved with pong replies without mistaking them for probes.
                probes = []
                for i in range(7):
                    start = time.perf_counter()*1000
                    await ws.send_json({'type': 'ping', 'client': str(i)})
                    while True:
                        reply = await ws.receive_json(timeout=5)
                        if reply.get('type') == 'pong' and reply.get('client') == str(i):
                            end = time.perf_counter()*1000
                            probes.append((end-start, reply['server']-(start+end)/2))
                            break
                self.offset = min(probes)[1]
                self.last_audio = time.monotonic()
                queue = asyncio.Queue(maxsize=10)
                loop = asyncio.get_running_loop()
                def enqueue(item):
                    if queue.full():
                        queue.get_nowait()  # Never replay a backlog after a stall.
                    queue.put_nowait(item)
                def callback(data, frames, timing, status):
                    age = timing.currentTime-timing.inputBufferAdcTime
                    stamp = time.perf_counter()*1000 - (age*1000 if 0 <= age < 1 else 0)
                    loop.call_soon_threadsafe(enqueue, (stamp, data.copy()))
                if self.stream_factory:
                    stream, rate = self.stream_factory(callback)
                else:
                    import sounddevice as sd
                    info = sd.query_devices(device, 'input')
                    rate = int(info['default_samplerate'])
                    stream = sd.InputStream(device=device, samplerate=rate, blocksize=round(rate*.02),
                                            channels=1, dtype='float32', callback=callback)
                self.notify('status', 'Connected · listening')
                async def receive():
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = msg.json()
                            if data.get('type') == 'error':
                                raise PairingError(data.get('message', 'Host rejected audio.'))
                            if data.get('type') == 'status':
                                self.notify('meter', data)
                            if data.get('type') == 'pong':
                                end = time.perf_counter()*1000
                                start = float(data['client'])
                                if end-start < 100:
                                    self.offset = self.offset*.9 + (data['server']-(start+end)/2)*.1
                    if ws.close_code == 1000:
                        raise PairingError('Disconnected by host. Click Connect to join again.')
                    raise ConnectionError('Hub disconnected')
                async def send():
                    last_ping = 0
                    last_mute = None
                    last_name = name
                    while True:
                        stamp, samples = await asyncio.wait_for(queue.get(), timeout=3)
                        self.last_audio = time.monotonic()
                        if self.name is not None and self.name != last_name:
                            await ws.send_json({'type':'rename','name':self.name});last_name=self.name
                        if self.muted != last_mute:
                            await ws.send_json({'type':'mute', 'muted':self.muted})
                            last_mute = self.muted
                        await ws.send_bytes(pcm_packet(np.zeros_like(samples) if self.muted else samples, stamp+self.offset, rate))
                        if time.monotonic()-last_ping > 5:
                            await ws.send_json({'type':'ping','client':str(time.perf_counter()*1000)})
                            last_ping = time.monotonic()
                tasks = []
                try:
                    with stream:
                        tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
