// Run with node --test tests/test_capture.cjs. No browser or mic needed.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
for(const rate of [44100,48000]) {
  test(`worklet resamples ${rate} Hz to continuous timestamped 48 kHz PCM`,()=>{
    const packets=[];
    const scope={sampleRate:rate,currentTime:0,Float32Array,Int16Array,
      AudioWorkletProcessor:class {constructor(){this.port={postMessage:p=>packets.push(p)};}},
      registerProcessor:(name,type)=>scope.Processor=type};
    vm.createContext(scope);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/capture.js'),'utf8'),scope);
    const capture=new scope.Processor();
    for(let start=0;start<rate;start+=128){
      scope.currentTime=start/rate;
      const input=Float32Array.from({length:Math.min(128,rate-start)},(_,i)=>.25*Math.sin(2*Math.PI*440*(start+i)/rate));
      assert.equal(capture.process([[input]],[]),true);
    }
    assert.ok(packets.length>=49 && packets.length<=50);
    let square=0,count=0;
    packets.forEach((p,i)=>{
      assert.equal(p.pcm.byteLength,1920);
      assert.ok(Math.abs(p.time-i*.02)<2/rate,`timestamp ${p.time} at packet ${i}`);
      for(const x of new Int16Array(p.pcm)){square+=x*x;count++;}
    });
    assert.ok(Math.abs(Math.sqrt(square/count)/32767-.25/Math.sqrt(2))<.001);
  });
}
