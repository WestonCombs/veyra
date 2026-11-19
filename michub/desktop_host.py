import asyncio, threading, ssl
from pathlib import Path
from aiohttp import web
from .server import Hub
from .certificates import prepare

class DesktopHost:
 def __init__(self):
  self.hub=None;self.loop=None;self.error=None;self.thread=None
 def start(self):
  if self.thread and self.thread.is_alive():return
  self.error=None
  self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
 def run(self):
  try:asyncio.run(self.serve())
  except Exception as e:self.error=str(e)
  finally:self.hub=None
 async def serve(self):
  self.loop=asyncio.get_running_loop();h=Hub();self.hub=h
  import os
  folder=Path(os.environ.get('LOCALAPPDATA','.'))/'CancelGroupMics'/'hub'
  h.fingerprint=prepare(folder,h.addresses)
  tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(folder/'server.pem',folder/'server-key.pem')
  # Native host exposes audio transport only; no browser pages or capture UI.
  app = web.Application()
  async def notice(request):
   return web.Response(text='Open Cancel Group Mics and paste your invite into the Guest dashboard.')
  async def certificate(request):
   return web.FileResponse(folder/'ca.crt')
  app.router.add_get('/',notice)
  app.router.add_get('/setup',notice)
  app.router.add_get('/ca.crt',certificate)
  app.router.add_get('/ws',h.socket)
  async def cleanup(app):
   for ws in list(h.sockets.values()):await ws.close(code=1001)
   if h.engine.thread.is_alive():h.engine.stop()
  app.on_cleanup.append(cleanup)
  runner=web.AppRunner(app,access_log=None);await runner.setup()
  discovery=None
  try:
   await web.TCPSite(runner,'0.0.0.0',8787).start()
   await web.TCPSite(runner,'0.0.0.0',8788,ssl_context=tls).start()
   from .discovery import Discovery,PORT
   try:discovery,_=await self.loop.create_datagram_endpoint(lambda:Discovery(h),local_addr=('0.0.0.0',PORT))
   except OSError:pass # Invite links still work when discovery port is occupied.
   h.engine.thread.start();await h.stop_requested.wait()
  finally:
   if discovery:discovery.close()
   await runner.cleanup()
 def stop(self):
  if self.hub and self.loop:self.loop.call_soon_threadsafe(self.hub.stop_requested.set)
