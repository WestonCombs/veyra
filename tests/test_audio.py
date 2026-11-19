import numpy as np
import pytest
from michub.audio import Mixer, Device, AudioOutput, BLOCK, RATE


def feed(mixer, now, values):
    for name, amp in values.items():
        mixer.devices[name].push(now-mixer.delay_ms, np.full(BLOCK, amp, dtype=np.float32), now)
    return mixer.render(now)


def room():
    mixer=Mixer()
    mixer.add("a","Laptop")
    mixer.add("b","Phone")
    return mixer


def test_only_loudest_channel_is_output():
    m=room()
    feed(m,10000,{"a":.2,"b":.1})
    out=feed(m,10020,{"a":.2,"b":.1})
    assert m.active=="a"
    np.testing.assert_allclose(out,.2)


def test_handoff_requires_margin_and_hold():
    m=room()
    feed(m,10000,{"a":.2,"b":.1})
    for t in range(10020,10200,20):
        feed(m,t,{"a":.2,"b":.23})
    assert m.active=="a" # less than 4 dB advantage
    for t in range(10200,10320,20):
        feed(m,t,{"a":.1,"b":.4})
        assert m.active=="a"
    feed(m,10320,{"a":.1,"b":.4})
    assert m.active=="b"


def test_jitter_buffer_compares_same_capture_time_not_arrival():
    m=room()
    capture=10000
    # Phone arrives 90ms later than laptop but has matching capture timestamp.
    m.devices["a"].push(capture,np.full(BLOCK,.1,dtype=np.float32),capture+20)
    m.devices["b"].push(capture,np.full(BLOCK,.4,dtype=np.float32),capture+110)
    out=m.render(capture+m.delay_ms)
    assert m.active=="b"
    np.testing.assert_allclose(out[240:],.4)


def test_gate_master_mute_and_per_device_mute():
    m=room()
    np.testing.assert_array_equal(feed(m,10000,{"a":.00001,"b":.00002}),0)
    assert m.active is None
    m.devices["b"].muted=True
    feed(m,10020,{"a":.1,"b":.5})
    assert m.active=="a"
    m.master_muted=True
    np.testing.assert_array_equal(feed(m,10040,{"a":.2,"b":.1}),0)


def test_gain_trim_and_limiter():
    m=room();m.devices["a"].gain_db=18
    feed(m,10000,{"a":.2,"b":.3})
    out=feed(m,10020,{"a":.2,"b":.3})
    assert m.active=="a" and max(out)<=.98


def test_pin_and_stale_feed_fail_to_silence():
    m=room();m.pinned="a"
    feed(m,10000,{"a":.1,"b":.4})
    assert m.active=="a"
    out=feed(m,10020,{"b":.4})
    assert m.active is None
    assert max(out) <= .100001 # the old endpoint decays; never the other mic
    np.testing.assert_array_equal(out[240:],0)
    m.pinned=None
    feed(m,10040,{"b":.4})
    assert m.active=="b"
    np.testing.assert_array_equal(m.render(11000)[240:],0)
    assert m.active is None
    np.testing.assert_array_equal(m.render(11020),0)


def test_four_devices_and_removal():
    m=room();m.add("c","Third");m.add("d","Fourth")
    with pytest.raises(ValueError,match="four"):m.add("e","Fifth")
    m.pinned="a";m.remove("a");assert m.pinned is None
    m.add("e","Fifth")
    assert len(m.devices)==4


def test_malformed_timestamps_and_bounded_buffer():
    d=Device("x","Test")
    for invalid in [float("nan"),float("inf"),-100000]:
        with pytest.raises(ValueError):d.push(invalid,np.zeros(BLOCK,dtype=np.float32),10000)
    for i in range(200):d.push(10000+i*20,np.ones(BLOCK,dtype=np.float32),10000+i*20)
    assert len(d.packets)==150
    np.testing.assert_array_equal(d.read(round(10000*RATE/1000)),0)


def test_output_callback_respects_frame_count_and_channels():
    output=AudioOutput();output.queue.append(np.arange(12,dtype=np.float32))
    a=np.zeros((5,2),dtype=np.float32);b=np.zeros((10,2),dtype=np.float32)
    output.callback(a,5,None,None);output.callback(b,10,None,None)
    np.testing.assert_array_equal(a[:,0],np.arange(5))
    np.testing.assert_array_equal(a[:,0],a[:,1])
    np.testing.assert_array_equal(b[:7,0],np.arange(5,12))
    np.testing.assert_array_equal(b[7:],0)
