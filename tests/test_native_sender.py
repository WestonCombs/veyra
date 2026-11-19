import asyncio
import struct
import time
from types import SimpleNamespace
import numpy as np
import pytest
from aiohttp.test_utils import TestClient, TestServer
from michub.server import Hub, create_app
from michub.native_sender import NativeSender, socket_url, pcm_packet


def test_native_urls_require_tls_for_lan():
    assert socket_url('http://localhost:8787/join#code=123456')=='ws://localhost:8787/ws'
    assert socket_url('https://10.0.0.1:8788/setup')=='wss://10.0.0.1:8788/ws'
    for value in ['http://10.0.0.1:8787','file:///test','https://user:pass@host']:
        with pytest.raises(ValueError):socket_url(value)


def test_native_pcm_resampling():
    for rate in [44100,48000]:
        packet=pcm_packet(np.full((round(rate*.02),1),.25,dtype=np.float32),1234,rate)
        assert len(packet)==1928
        assert struct.unpack_from('<d',packet)[0]==1234
        np.testing.assert_array_equal(np.frombuffer(packet,dtype='<i2',offset=8),8191)


class FakeInput:
    def __init__(self,callback):self.callback=callback;self.closed=False;self.task=None
    def __enter__(self):
        self.task=asyncio.create_task(self.generate());return self
    async def generate(self):
        while True:
            now=time.perf_counter()
            self.callback(np.full((960,1),.2,dtype=np.float32),960,SimpleNamespace(currentTime=now,inputBufferAdcTime=now-.02),None)
            await asyncio.sleep(.02)
    def __exit__(self,*args):self.closed=True;self.task.cancel()


@pytest.mark.asyncio
async def test_native_sends_mutes_and_releases_device():
    hub=Hub();events=[];inputs=[]
    def factory(callback):
        stream=FakeInput(callback);inputs.append(stream);return stream,48000
    sender=NativeSender(lambda k,v:events.append((k,v)),factory)
    async with TestClient(TestServer(create_app(hub))) as client:
        task=asyncio.create_task(sender.connection(str(client.make_url('/ws')),hub.code,'Native',None,None))
        async def wait_for(predicate):
            for _ in range(100):
                if predicate():return
                await asyncio.sleep(.02)
            raise AssertionError('Sender did not reach expected state')
        await wait_for(lambda:hub.mixer.devices and len(next(iter(hub.mixer.devices.values())).packets)>3)
        device=next(iter(hub.mixer.devices.values()))
        assert np.max(device.packets[-1][1])>.19
        sender.muted=True
        await wait_for(lambda:device.muted and not np.any(device.packets[-1][1]))
        sender.muted=False
        await wait_for(lambda:not device.muted and np.max(device.packets[-1][1])>.19)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert inputs[0].closed


@pytest.mark.asyncio
async def test_rejected_code_does_not_open_microphone_or_retry():
    hub=Hub();events=[]
    def never(callback):raise AssertionError('Unpaired sender must not capture audio')
    sender=NativeSender(lambda k,v:events.append((k,v)),never)
    async with TestClient(TestServer(create_app(hub))) as client:
        await asyncio.wait_for(sender.run(str(client.make_url('/ws')),'wrong','Test',None,None),2)
    assert any('room code' in str(value) for kind,value in events)


@pytest.mark.asyncio
async def test_network_interruption_reconnects_and_closes_old_capture():
    hub=Hub();inputs=[]
    def factory(callback):
        stream=FakeInput(callback);inputs.append(stream);return stream,48000
    sender=NativeSender(lambda *args:None,factory);sender.retry_delay=.05
    async with TestClient(TestServer(create_app(hub))) as client:
        task=asyncio.create_task(sender.run(str(client.make_url('/ws')),hub.code,'Reconnect',None,None))
        try:
            async with asyncio.timeout(3):
                while not inputs:await asyncio.sleep(.01)
                await next(iter(hub.sockets.values())).close(code=1001,message=b'Test interruption')
                while len(inputs)<2:await asyncio.sleep(.01)
                assert inputs[0].closed
                assert len(hub.mixer.devices)==1
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
        assert inputs[-1].closed
