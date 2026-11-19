"""In-process host capture: no WebSocket, PCM codec or clock probes."""
import threading,time,secrets,sys,ctypes
import numpy as np
from .audio import RATE,BLOCK,db

class LocalSender:
 def __init__(self,hub,notify):
  self.hub=hub;self.notify=notify;self.thread=None;self.done=threading.Event();self.id=secrets.token_hex(8)
 def start(self,address,code,name,device):
  self.hub.mixer.add(self.id,name)
  with self.hub.mixer.lock:self.hub.mixer.devices[self.id].local=True
  self.thread=threading.Thread(target=self.run,args=(device,),daemon=True);self.thread.start()
 def stop(self):self.done.set()
 def run(self,device):
  initialized=sys.platform=='win32' and ctypes.windll.ole32.CoInitializeEx(None,0) in (0,1)
  try:
   import sounddevice as sd
   rate=int(sd.query_devices(device,'input')['default_samplerate'])
   def callback(data,frames,timing,status):
    samples=data[:,0]
    if rate!=RATE:samples=np.interp(np.arange(BLOCK)*rate/RATE,np.arange(len(samples)),samples).astype(np.float32)
    else:samples=samples.copy()
    now=time.perf_counter()*1000;age=timing.currentTime-timing.inputBufferAdcTime
    stamp=now-(age*1000 if 0<=age<1 else 0)
    m=self.hub.mixer
    with m.lock:
     d=m.devices.get(self.id)
     if not d:return
     d.push(stamp,samples,now)
     if m.direct_mode():
      output=samples*(10**(d.gain_db/20)) if d.gain_db else samples
      if d.muted or m.master_muted:output=np.zeros_like(samples)
      else:output=np.clip(output,-.98,.98)
      d.level_db=db(samples);m.output_db=db(output);m.active=None if d.muted or m.master_muted else d.id
      self.hub.output.feed(output)
   with sd.InputStream(device=device,samplerate=rate,blocksize=round(rate*.02),channels=1,dtype='float32',callback=callback):
    self.notify('status','Local microphone connected');self.done.wait()
  except Exception as e:self.notify('status',str(e))
  finally:
   self.hub.mixer.remove(self.id)
   if initialized:ctypes.windll.ole32.CoUninitialize()
   self.notify('ended',None)
