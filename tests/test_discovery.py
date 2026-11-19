import asyncio
import pytest
from aiohttp.test_utils import TestClient,TestServer
from michub.discovery import Discovery,discover
from michub.server import Hub

class Transport:
 def __init__(self):self.sent=[]
 def sendto(self,data,peer):self.sent.append((data,peer))

def test_discovery_ignores_unknown_queries():
 p=Discovery(Hub());t=Transport();p.connection_made(t)
 p.datagram_received(b'invalid',('127.0.0.1',42));assert not t.sent
 p.datagram_received(b'VEYRA_DISCOVER_V1',('127.0.0.1',42))
 import json
 response=json.loads(t.sent[0][0]);assert response['code']==p.hub.code and response['tls']==8788

def test_discovery_validates_code_without_network():
 for code in ['', 'abcdef', '12345', '1234567']:
  with pytest.raises(ValueError):discover(code)
