"""Timestamped jitter buffers and a single-winner microphone selector.

All internal audio is mono float32 at 48 kHz. Selection uses aligned, buffered
audio, so a late packet cannot win against an earlier moment on another mic.
"""
from collections import deque
from dataclasses import dataclass, field
import math
import threading
import time
import numpy as np

RATE = 48000
BLOCK = 960
MAX_DEVICES = 4


def db(samples):
    return max(-90.0, 20 * math.log10(max(0.000001, float(np.sqrt(np.mean(samples * samples))))))


@dataclass
class Device:
    id: str
    name: str
    local: bool = False
    gain_db: float = 0.0
    muted: bool = False
    level_db: float = -90.0
    score_db: float = -90.0
    last_received: float = 0.0
    late_packets: int = 0
    packets: deque = field(default_factory=lambda: deque(maxlen=150))
    last_end: int = 0
    voice_until: float = 0.0

    def push(self, timestamp_ms, samples, now_ms):
        if not math.isfinite(timestamp_ms) or abs(timestamp_ms - now_ms) > 2500:
            raise ValueError("Audio timestamp is outside the live window. Reconnect to resync.")
        start = round(timestamp_ms * RATE / 1000)
        # Clock probes and AudioContext clock quantization must not punch tiny
        # holes into an otherwise continuous PCM stream.
        if self.last_end and abs(start-self.last_end) < RATE*.010:
            start = self.last_end
        # WebSocket is ordered. Reject replays; allow clock correction to move
        # a packet by a fraction of a frame without duplicating samples.
        if self.last_end and start < self.last_end - BLOCK // 2:
            self.late_packets += 1
            return
        self.packets.append((start, samples))
        self.last_end = start + len(samples)
        self.last_received = now_ms

    def read(self, start, frames=BLOCK):
        result = np.zeros(frames, dtype=np.float32)
        while self.packets and self.packets[0][0] + len(self.packets[0][1]) <= start:
            self.packets.popleft()
        for pos, samples in self.packets:
            if pos >= start + frames:
                break
            lo, hi = max(start, pos), min(start + frames, pos + len(samples))
            if hi > lo:
                result[lo-start:hi-start] = samples[lo-pos:hi-pos]
        return result


class Mixer:
    def __init__(self):
        self.lock = threading.RLock()
        self.devices = {}
        self.active = None
        self.master_muted = False
        self.pinned = None
        self.delay_ms = 180
        self.gate_db = -60.0
        self.margin_db = 4.0
        self.hold_ms = 120
        self.challenger = None
        self.challenge_since = 0.0
        self.last_voice = 0.0
        self.output_db = -90.0
        self.switches = 0
        self.last_sample = 0.0
        self.fade_remaining = 0
        self.was_silent = True

    def add(self, device_id, name):
        with self.lock:
            if len(self.devices) >= MAX_DEVICES:
                raise ValueError("This room already has four microphones. Disconnect one first.")
            self.devices[device_id] = Device(device_id, name)

    def remove(self, device_id):
        with self.lock:
            self.devices.pop(device_id, None)
            if self.pinned == device_id:
                self.pinned = None

    def direct_mode(self):
        return len(self.devices)==1 and next(iter(self.devices.values())).local and self.pinned in (None,next(iter(self.devices)))

    def render(self, now_ms):
        with self.lock:
            start = round((now_ms - self.delay_ms) * RATE / 1000)
            blocks = {}
            for d in self.devices.values():
                samples = d.read(start) * (10 ** (d.gain_db / 20))
                d.level_db = db(samples)
                # Fast attack, short release; do not let a missing/stale feed
                # remain a candidate because of its previous envelope.
                d.score_db = d.level_db if d.level_db > d.score_db else max(d.level_db, d.score_db - 5)
                if d.level_db > self.gate_db:
                    d.voice_until = now_ms + 300
                # Keep quiet syllables and word endings after speech starts.
                # Still exclude missing packets, muted and stale feeds.
                if not d.muted and now_ms - d.last_received < 500 and np.any(samples) and now_ms <= d.voice_until:
                    blocks[d.id] = samples
            previous = self.active
            if self.pinned is not None:
                self.active = self.pinned if self.pinned in blocks else None
                self.challenger = None
            elif not blocks:
                # Brief gaps retain the winner but output silence immediately.
                if now_ms - self.last_voice > 180 or self.active not in self.devices or self.devices[self.active].muted:
                    self.active = None
                self.challenger = None
            else:
                best = max(blocks, key=lambda i: self.devices[i].score_db)
                current = self.devices.get(self.active)
                if self.active not in blocks:
                    self.active = best
                    self.challenger = None
                elif best != self.active and self.devices[best].score_db > current.score_db + self.margin_db:
                    if self.challenger != best:
                        self.challenger, self.challenge_since = best, now_ms
                    if now_ms - self.challenge_since >= self.hold_ms:
                        self.active, self.challenger = best, None
                else:
                    self.challenger = None
                self.last_voice = now_ms
            if self.active != previous:
                self.switches += 1
                self.fade_remaining = 240  # 5 ms de-click, never sum microphones
            output = blocks.get(self.active, np.zeros(BLOCK, dtype=np.float32)).copy()
            silent = not np.any(output)
            if silent != self.was_silent:
                self.fade_remaining = 240
            if self.master_muted:
                output.fill(0)
            elif self.fade_remaining:
                n = min(self.fade_remaining, len(output))
                ramp = np.linspace(0, 1, n, dtype=np.float32)
                # Interpolate from the previous output endpoint, not a second
                # audio stream. This softens both handoffs and gate edges.
                output[:n] = self.last_sample * (1-ramp) + output[:n] * ramp
                self.fade_remaining -= n
            # Hard limiter guarantees legal PCM even when per-mic gain is high.
            np.clip(output, -0.98, 0.98, out=output)
            self.last_sample = float(output[-1])
            self.was_silent = silent or self.master_muted
            self.output_db = db(output)
            return output

    def snapshot(self):
        with self.lock:
            return {
                "devices": [{"id": d.id, "name": d.name, "gain_db": d.gain_db,
                             "muted": d.muted, "level_db": round(d.level_db, 1),
                             "active": d.id == self.active and not self.master_muted and d.level_db > self.gate_db,
                             "stale": time.perf_counter()*1000 - d.last_received > 1000,
                             "late_packets": d.late_packets} for d in self.devices.values()],
                "active": self.active, "master_muted": self.master_muted,
                "pinned": self.pinned, "delay_ms": self.delay_ms,
                "gate_db": self.gate_db, "margin_db": self.margin_db,
                "hold_ms": self.hold_ms, "output_db": round(self.output_db, 1),
                "switches": self.switches,
            }


class AudioOutput:
    """PortAudio sink. Never auto-select speakers: output starts explicitly."""
    def __init__(self):
        self.stream = None
        self.lock = threading.Lock()
        self.queue = deque()
        self.pending = np.empty(0, dtype=np.float32)
        self.rate = RATE
        self.device = None
        self.error = None
        self.underruns = 0
        self.channels = 1

    @staticmethod
    def devices():
        import sounddevice as sd
        apis = sd.query_hostapis()
        return [{"id": i, "name": d["name"], "api": apis[d["hostapi"]]["name"],
                 "cable": "cable input" in d["name"].lower(),
                 "rate": d["default_samplerate"]}
                for i, d in enumerate(sd.query_devices()) if d["max_output_channels"] > 0]

    def start(self, device):
        import sounddevice as sd
        self.stop()
        try:
            info = sd.query_devices(device, "output")
            self.rate = int(info["default_samplerate"])
            self.channels = min(2, info["max_output_channels"])
            self.device = device
            self.error = None
            self.underruns = 0
            with self.lock:
                # Small output cushion keeps normal OS scheduling jitter from
                # creating holes between the engine's 20 ms blocks.
                for _ in range(2):
                    self.queue.append(np.zeros(round(self.rate*.02), dtype=np.float32))
            self.stream = sd.OutputStream(device=device, samplerate=self.rate,
                                          channels=self.channels, dtype="float32",
                                          latency="low", callback=self.callback)
            self.stream.start()
        except Exception as exc:
            self.stop()
            self.error = str(exc)
            raise ValueError(f"Could not open that audio output: {exc}") from exc

    def stop(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
        self.stream, self.device = None, None
        with self.lock:
            self.queue.clear()
            self.pending = np.empty(0, dtype=np.float32)

    def feed(self, samples):
        if self.stream is None:
            return
        n = round(len(samples) * self.rate / RATE)
        block = samples if self.rate == RATE else np.interp(np.arange(n) * RATE / self.rate,
                                                           np.arange(len(samples)), samples).astype(np.float32)
        with self.lock:
            # Bound latency even if an audio driver stalls.
            if len(self.queue) >= 5:
                self.queue.popleft()
            self.queue.append(block)

    def callback(self, outdata, frames, timing, status):
        outdata.fill(0)
        if status:
            self.underruns += 1
        with self.lock:
            offset = 0
            while offset < frames:
                if not len(self.pending):
                    if not self.queue:
                        break
                    self.pending = self.queue.popleft()
                n = min(frames-offset, len(self.pending))
                outdata[offset:offset+n] = self.pending[:n, None]
                self.pending = self.pending[n:]
                offset += n

    def snapshot(self):
        running = self.stream is not None and self.stream.active
        return {"running": bool(running), "device": self.device, "error": self.error,
                "underruns": self.underruns, "rate": self.rate}


class Engine:
    def __init__(self, mixer, output):
        self.mixer, self.output = mixer, output
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.run, name="mic-mixer", daemon=True)
        self.error = None

    def run(self):
        deadline = time.perf_counter()
        while not self.done.is_set():
            try:
                with self.mixer.lock:
                    # Sole local capture writes directly to the output queue.
                    # Remote-only and multi-mic rooms retain aligned selection.
                    if not self.mixer.direct_mode():
                        self.output.feed(self.mixer.render(deadline * 1000))
            except Exception as exc:
                self.error = str(exc)
            deadline += BLOCK / RATE
            now = time.perf_counter()
            if now - deadline > 0.1:
                deadline = now
            self.done.wait(max(0, deadline - now))

    def stop(self):
        self.done.set()
        self.thread.join(timeout=2)
        self.output.stop()
