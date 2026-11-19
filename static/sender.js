"use strict";
const $=id=>document.getElementById(id);
let ws=null,stream=null,context=null,node=null,source=null,wake=null,syncTimer=null;
let running=false,muted=false,offset=0,basePerf=0,baseAudio=0,pingWaiters=new Map(),lastError="",generation=0;
const code=new URLSearchParams(location.hash.slice(1)).get("code");
if(code && /^\d{6}$/.test(code)) $("code").value=code;
if(location.hash) history.replaceState(null,"",location.pathname);
$("name").value=localStorage.getItem("mic-name")||"";
function error(message){$("error").textContent=message;$("error").hidden=!message;}
async function listMics(){
  if(!navigator.mediaDevices) return;
  const selected=$("mic").value;
  const devices=await navigator.mediaDevices.enumerateDevices();
  $("mic").replaceChildren(new Option("System default microphone",""),...devices.filter(d=>d.kind==="audioinput" && d.deviceId!=="default").map((d,i)=>new Option(d.label||`Microphone ${i+1}`,d.deviceId)));
  if([...$("mic").options].some(o=>o.value===selected)) $("mic").value=selected;
}
function ping(){return new Promise((resolve,reject)=>{
  const start=performance.now(),key=String(start);
  const timer=setTimeout(()=>{pingWaiters.delete(key);reject(new Error("Clock sync timed out. Check your Wi-Fi and try again."));},2500);
  pingWaiters.set(key,{start,resolve:sample=>{clearTimeout(timer);resolve(sample);}});
  ws.send(JSON.stringify({type:"ping",client:key}));
});}
async function sync(initial=false){
  const results=[];for(let i=0;i<(initial?7:3);i++) results.push(await ping());
  results.sort((a,b)=>a.rtt-b.rtt);
  offset=initial?results[0].offset:offset*0.85+results[0].offset*0.15;
  if(!initial && context?.state==="running") {
    basePerf=performance.now();baseAudio=context.currentTime;
  }
}
async function lockScreen(){
  if(!running || !navigator.wakeLock || document.visibilityState!=="visible") return;
  try{wake=await navigator.wakeLock.request("screen");}catch(e){/* Visible hint already explains background limitations. */}
}
async function stop(message=""){
  ++generation;running=false;clearInterval(syncTimer);syncTimer=null;
  if(node){node.port.onmessage=null;node.disconnect();node=null;}
  if(source){source.disconnect();source=null;}
  if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}
  if(context){await context.close().catch(()=>{});context=null;}
  if(ws){const old=ws;ws=null;old.onclose=null;old.close();}
  if(wake){await wake.release().catch(()=>{});wake=null;}
  $("join-form").hidden=false;$("sender-panel").hidden=true;$("connect").disabled=false;$("connect").textContent="Connect microphone →";
  if(message) error(message);
}
$("join-form").onsubmit=async event=>{
  event.preventDefault();error("");lastError="";const attempt=++generation;
  $("connect").disabled=true;$("connect").textContent="Connecting…";
  try{
    if(!isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error("Microphone access needs a trusted HTTPS connection. Open device setup on this hub first.");
    // Request capture immediately within the user's gesture (important on mobile).
    context=new AudioContext({sampleRate:48000,latencyHint:"interactive"});await context.resume();
    stream=await navigator.mediaDevices.getUserMedia({audio:{deviceId:$("mic").value?{exact:$("mic").value}:undefined,channelCount:1,echoCancellation:false,noiseSuppression:false,autoGainControl:false},video:false});
    if(attempt!==generation){stream.getTracks().forEach(t=>t.stop());return;}
    await listMics();
    ws=new WebSocket(`${location.protocol==="https:"?"wss":"ws"}://${location.host}/ws`);ws.binaryType="arraybuffer";
    await new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(new Error("Connection timed out. Check the host and Wi-Fi.")),10000);
      ws.onopen=()=>ws.send(JSON.stringify({code:$("code").value,name:$("name").value.trim()}));
      ws.onerror=()=>{clearTimeout(timeout);reject(new Error("Could not reach the hub. Check the connection and local certificate."));};
      ws.onclose=()=>{clearTimeout(timeout);reject(new Error(lastError||"The hub closed the connection."));};
      ws.onmessage=event=>{
        const data=JSON.parse(event.data);
        if(data.type==="welcome"){clearTimeout(timeout);resolve();}
        else if(data.type==="error"){lastError=data.message;clearTimeout(timeout);reject(new Error(data.message));}
      };
    });
    ws.onmessage=event=>{
      const data=JSON.parse(event.data);
      if(data.type==="pong"){
        const waiter=pingWaiters.get(data.client);if(waiter){pingWaiters.delete(data.client);const end=performance.now();waiter.resolve({rtt:end-waiter.start,offset:data.server-(waiter.start+end)/2});}
      } else if(data.type==="error"){lastError=data.message;error(data.message);}
      else if(data.type==="status"){
        muted=data.muted;$("mute").textContent=muted?"Unmute mic":"Mute mic";$("mute").classList.toggle("danger",muted);
        $("sender-status").classList.toggle("active",data.active && data.output_running);
        $("status-title").textContent=muted?"Microphone muted":data.master_muted?"Room is muted":data.active?(data.output_running?"You’re on air":"Your mic is selected"):"Standing by";
        $("status-detail").textContent=muted?"Your microphone is excluded from the output.":data.master_muted?"The host has muted the room.":!data.output_running?"Connected. The host still needs to start output.":data.active?"Your voice is feeding the call.":"Connected. Speak naturally to take the lead.";
        const level=Math.round(data.level_db);$("local-db").textContent=`${level} dB`;$("local-meter").style.width=`${Math.max(0,Math.min(100,(level+65)/65*100))}%`;
      }
    };
    ws.onclose=()=>stop(lastError||"Disconnected from the hub. Reconnect when you’re ready.");
    await sync(true);
    if(attempt!==generation)return;
    await context.audioWorklet.addModule("/static/capture.js");
    if(attempt!==generation)return;
    basePerf=performance.now();baseAudio=context.currentTime;
    node=new AudioWorkletNode(context,"capture");source=context.createMediaStreamSource(stream);
    node.port.onmessage=event=>{
      if(!running || ws?.readyState!==WebSocket.OPEN) return;
      if(ws.bufferedAmount>1928*10){stop("Wi-Fi is too slow to send live audio. Move closer to the router, then reconnect.");return;}
      const {time,pcm}=event.data;const packet=new ArrayBuffer(8+pcm.byteLength);
      new DataView(packet).setFloat64(0,basePerf+(time-baseAudio)*1000+offset,true);
      new Uint8Array(packet,8).set(new Uint8Array(pcm));ws.send(packet);
    };
    source.connect(node);node.connect(context.destination);
    running=true;muted=false;$("join-form").hidden=true;$("sender-panel").hidden=false;
    localStorage.setItem("mic-name",$("name").value.trim());
    stream.getAudioTracks()[0].onended=()=>stop("Microphone access ended. Check the microphone and reconnect.");
    context.onstatechange=()=>{if(running && context?.state==="suspended") error("Audio was paused by your browser. Keep this page visible, then disconnect and reconnect.");};
    syncTimer=setInterval(()=>sync().catch(e=>{error(e.message);}),5000);await lockScreen();
  }catch(e){if(attempt!==generation)return;await stop();error(e.name==="NotAllowedError"?"Microphone permission was denied. Allow microphone access in this browser’s site settings, then reconnect.":e.message);}
};
$("mute").onclick=()=>{if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:"mute",muted:!muted}));};
$("disconnect").onclick=()=>stop();
document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible")lockScreen();});
window.addEventListener("pagehide",()=>{if(stream)stream.getTracks().forEach(t=>t.stop());if(ws)ws.close();});
listMics().catch(()=>{});
