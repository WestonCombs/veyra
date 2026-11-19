import numpy as np
from michub.audio import Mixer, Device, BLOCK, RATE


def test_quiet_word_endings_survive_gate():
    m=Mixer();m.gate_db=-48;m.add('a','Voice');d=m.devices['a']
    for i,level in enumerate([.1]+[.002]*10):
        now=10000+i*20
        d.push(now-m.delay_ms,np.full(BLOCK,level,dtype=np.float32),now)
        out=m.render(now)
        # First block fades in; every following quiet block must survive intact.
        if i:np.testing.assert_allclose(out,.002)


def test_clock_quantization_does_not_insert_packet_holes():
    d=Device('a','Voice')
    base=10000
    for i in range(40):
        stamp=base+i*20+(2 if i%2 else -2)
        d.push(stamp,np.full(BLOCK,.1,dtype=np.float32),stamp+30)
    start=round((base-2)*RATE/1000)
    for i in range(40):
        np.testing.assert_allclose(d.read(start+i*BLOCK),.1)
