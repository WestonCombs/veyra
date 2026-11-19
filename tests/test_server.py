import json
import struct
import time
import numpy as np
import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer
from michub.server import Hub, create_app
from michub.audio import BLOCK


@pytest_asyncio.fixture
async def client():
    hub=Hub()
    async with TestClient(TestServer(create_app(hub))) as client:
        client.hub=hub
        yield client


@pytest.mark.asyncio
async def test_host_controls_require_token_and_loopback_host(client):
    assert (await client.get("/api/state")).status==403
    headers={"X-Hub-Token":client.hub.token}
    assert (await client.get("/api/state",headers=headers)).status==200
    assert (await client.get("/api/state",headers={**headers,"Host":"evil.example"})).status==403
    result=await client.post("/api/control",headers=headers,json={"action":"settings","delay_ms":0})
    assert result.status==400
    result=await client.post("/api/control",headers=headers,json={"action":"settings","delay_ms":float("nan")})
    assert result.status==400
    result=await client.post("/api/control",headers=headers,json={"action":"settings","delay_ms":260})
    assert result.status==200 and client.hub.mixer.delay_ms==260


@pytest.mark.asyncio
async def test_pairing_code_four_device_limit_and_audio(client):
    wrong=await client.ws_connect("/ws")
    await wrong.send_json({"code":"incorrect","name":"Nope"})
    assert (await wrong.receive_json())["type"]=="error"
    await wrong.close()
    sockets=[]
    for i in range(4):
        ws=await client.ws_connect("/ws")
        await ws.send_json({"code":client.hub.code,"name":f"Mic {i}"})
        welcome=await ws.receive_json()
        assert welcome["type"]=="welcome"
        sockets.append(ws)
    fifth=await client.ws_connect("/ws")
    await fifth.send_json({"code":client.hub.code,"name":"Fifth"})
    assert "four" in (await fifth.receive_json())["message"]
    await fifth.close()
    ws=sockets[0]
    await ws.send_json({"type":"ping","client":"probe"})
    assert (await ws.receive_json())["type"]=="pong"
    await ws.receive_json() # status
    packet=struct.pack("<d",time.perf_counter()*1000)+np.full(BLOCK,1000,dtype="<i2").tobytes()
    await ws.send_bytes(packet)
    # A ping after the binary frame proves the receive loop accepted the PCM.
    await ws.send_json({"type":"ping","client":"after"})
    while (await ws.receive_json())["type"]!="pong":pass
    assert len(next(iter(client.hub.mixer.devices.values())).packets)==1
    for ws in sockets:await ws.close()


@pytest.mark.asyncio
async def test_websocket_origin_and_bad_packet(client):
    with pytest.raises(Exception):await client.ws_connect("/ws",origin="https://evil.example")
    ws=await client.ws_connect("/ws")
    await ws.send_json({"code":client.hub.code,"name":"Mic"})
    await ws.receive_json()
    await ws.send_bytes(b"broken")
    assert (await ws.receive_json())["type"]=="error"
    await ws.close()
