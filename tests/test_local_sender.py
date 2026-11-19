from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from michub.audio import Mixer
from michub.local_sender import LocalSender

@pytest.mark.parametrize('rate',[48000,96000])
@pytest.mark.parametrize('remote',[False,True])
def test_local_direct_routing_and_network_fallback(monkeypatch,rate,remote):
 import sounddevice as sd,time
 mixer=Mixer();output=SimpleNamespace(feed=Mock());hub=SimpleNamespace(mixer=mixer,output=output)
 sender=LocalSender(hub,lambda *args:None);mixer.add(sender.id,'Host');mixer.devices[sender.id].local=True
 if remote:mixer.add('remote','Remote')
 monkeypatch.setattr(sd,'query_devices',lambda *args:{'default_samplerate':rate})
 class Stream:
  def __init__(self,**kwargs):self.cb=kwargs['callback']
  def __enter__(self):
   t=time.perf_counter();self.cb(np.full((round(rate*.02),1),.002,dtype=np.float32),round(rate*.02),SimpleNamespace(currentTime=t,inputBufferAdcTime=t-.02),None)
   assert len(mixer.devices[sender.id].packets)==1
   if not remote:
    samples=output.feed.call_args.args[0];assert len(samples)==960;np.testing.assert_allclose(samples,.002)
    mixer.devices[sender.id].muted=True
    self.cb(np.full((round(rate*.02),1),.2,dtype=np.float32),round(rate*.02),SimpleNamespace(currentTime=t+.02,inputBufferAdcTime=t),None)
    np.testing.assert_array_equal(output.feed.call_args.args[0],0)
   else:output.feed.assert_not_called()
   sender.done.set();return self
  def __exit__(self,*args):pass
 monkeypatch.setattr(sd,'InputStream',Stream);sender.run(0)
 assert sender.id not in mixer.devices

def test_direct_eligibility_tracks_room_membership():
 m=Mixer();m.add('host','Host');m.devices['host'].local=True;assert m.direct_mode()
 m.add('other','Other');assert not m.direct_mode()
 m.remove('other');assert m.direct_mode()
 m.devices['host'].local=False;assert not m.direct_mode()
