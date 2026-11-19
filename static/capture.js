// Timestamped 20 ms / 48 kHz mono packets. Persistent fractional position
// resamples a 44.1 kHz AudioContext without accumulating drift between blocks.
class Capture extends AudioWorkletProcessor {
  constructor() {
    super(); this.buffer=new Float32Array(960);this.count=0;this.sourceIndex=0;this.next=0;this.previous=0;this.frameStart=0;
  }
  process(inputs,outputs) {
    const input=inputs[0]?.[0];
    if(!input) return true;
    const ratio=sampleRate/48000;
    for(let i=0;i<input.length;i++) {
      const index=this.sourceIndex++;
      while(this.next<=index) {
        const fraction=this.next-(index-1);
        const value=index===0 ? input[i] : this.previous+(input[i]-this.previous)*fraction;
        if(this.count===0) this.frameStart=currentTime+(i+(this.next-index))/sampleRate;
        this.buffer[this.count++]=value;
        this.next+=ratio;
        if(this.count===960) {
          const pcm=new Int16Array(960);
          for(let j=0;j<960;j++) pcm[j]=Math.round(Math.max(-1,Math.min(1,this.buffer[j]))*32767);
          this.port.postMessage({time:this.frameStart,pcm:pcm.buffer},[pcm.buffer]);this.count=0;
        }
      }
      this.previous=input[i];
    }
    // Outputs remain zero: the capture graph must never monitor its own mic.
    return true;
  }
}
registerProcessor("capture",Capture);
