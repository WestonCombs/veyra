"""LAN discovery carries no audio and never replaces TLS certificate validation."""
import asyncio,json,socket,time
PORT=48789
class Discovery(asyncio.DatagramProtocol):
 def __init__(self,hub):self.hub=hub
 def connection_made(self,transport):self.transport=transport
 def datagram_received(self,data,peer):
  if data==b'VEYRA_DISCOVER_V1':
   self.transport.sendto(json.dumps({'app':'veyra','code':self.hub.code,'tls':self.hub.https_port}).encode(),peer)
def discover(code,timeout=3):
 if len(code)!=6 or not code.isdigit():raise ValueError('Enter the six-digit room code.')
 matches=set()
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
  sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);sock.settimeout(.25)
  for address in ['255.255.255.255','127.0.0.1']:
   try:sock.sendto(b'VEYRA_DISCOVER_V1',(address,PORT))
   except OSError:pass
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   try:
    data,peer=sock.recvfrom(2048);info=json.loads(data)
    if info.get('app')=='veyra' and info.get('code')==code:matches.add((peer[0],int(info['tls'])))
   except (socket.timeout,ValueError,KeyError):continue
 if not matches:raise ValueError('Room not found on this Wi-Fi. Use Invite link instead, or allow Veyra through the host firewall (UDP 48789).')
 # A local reply and a LAN reply can describe the same host.
 if len(matches)>1:
  matches={m for m in matches if m[0]!='127.0.0.1'}
 if len(matches)!=1:raise ValueError('More than one room matches. Use the invite link.')
 host,port=next(iter(matches));return f'https://{host}:{port}'
