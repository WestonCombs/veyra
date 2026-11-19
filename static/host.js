"use strict";
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="hub-token"]').content;
let state = null, outputs = [], network = 0, busy = false;
const cards = new Map();
function error(message) { $("error").textContent = message; $("error").hidden = !message; }
async function api(path, body) {
  const response = await fetch(path, {method: body ? "POST" : "GET", headers:{"X-Hub-Token":token, ...(body ? {"Content-Type":"application/json"} : {})}, body:body ? JSON.stringify(body) : undefined});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The hub could not complete that request.");
  return result;
}
async function control(body) {
  try { error(""); await api("/api/control", body); await refresh(); }
  catch (e) { error(e.message); }
}
function meter(el, level) { el.style.width = `${Math.max(0, Math.min(100, (level + 65) / 65 * 100))}%`; }
function db(level) { return `${Math.round(level)} dB`; }
function updateLinks() {
  if (!state) return;
  $("join-url").textContent = state.setup_urls[network] || "No network address found";
  $("setup-link").href = state.setup_urls[network] || "/setup";
}
function makeCard(d) {
  const card = $("device-template").content.firstElementChild.cloneNode(true);
  card.querySelector(".mute").onclick = () => control({action:"device", id:d.id, muted:!state.devices.find(x=>x.id===d.id)?.muted});
  card.querySelector(".pin").onclick = () => control({action:"pin", id:state.pinned===d.id ? null : d.id});
  card.querySelector(".disconnect").onclick = () => control({action:"disconnect", id:d.id});
  const gain = card.querySelector(".gain");
  gain.oninput = () => card.querySelector(".gain-label").textContent = `${Number(gain.value)>0 ? "+" : ""}${gain.value} dB`;
  gain.onchange = () => control({action:"device", id:d.id, gain_db:Number(gain.value)});
  cards.set(d.id,card);
  return card;
}
function render(next) {
  state = next;
  $("connection").classList.remove("offline");
  $("connection").lastChild.textContent = " Hub online";
  $("device-count").textContent = `${state.devices.length} / 4`;
  $("room-code").textContent = `${state.code.slice(0,3)} ${state.code.slice(3)}`;
  $("local-mic-link").href = `/join#code=${state.code}`;
  $("host-fingerprint").textContent = state.fingerprint;
  $("master").textContent = state.master_muted ? "Unmute all" : "Mute all";
  $("master").classList.toggle("danger",state.master_muted);
  const winner = state.devices.find(d=>d.active);
  const running = state.output.running;
  $("air-label").textContent = state.master_muted ? "ALL MICROPHONES MUTED" : winner ? "SELECTED MICROPHONE" : "READY WHEN YOU ARE";
  $("air-name").textContent = state.master_muted ? "A moment of quiet." : winner ? winner.name : state.devices.length ? "Listening for a voice…" : "Let’s hear everyone.";
  $("air-description").textContent = state.master_muted ? "Unmute when you’re ready to continue." : winner ? (running ? "This microphone is feeding your output." : "Mic selected. Start output to send it to your call.") : state.devices.length ? "The loudest microphone will take the lead." : "Connect a microphone to get started.";
  document.querySelector(".onair-panel").classList.toggle("live",!!winner && running);
  $("output-badge").textContent = running ? (state.master_muted ? "Muted" : "Output live") : "Output off";
  meter($("master-meter"), running ? state.output_db : -90);
  $("master-db").textContent = running ? db(state.output_db) : "Off";
  $("start-output").textContent = running ? "Stop output" : "Start output";
  $("start-output").classList.toggle("danger",running);
  $("output-device").disabled = running;
  $("output-detail").textContent = state.output.error || (running ? `${state.output.rate/1000} kHz · Driver warnings: ${state.output.underruns}` : "");
  const names = state.join_urls.map(u=>new URL(u).hostname);
  if (JSON.stringify(names) !== $("network").dataset.addresses) {
    $("network").replaceChildren(...names.map((n,i)=>new Option(n,String(i))));
    $("network").dataset.addresses = JSON.stringify(names);
    network = 0;
  }
  updateLinks();
  for (const [id,card] of cards) if (!state.devices.some(d=>d.id===id)) { card.remove(); cards.delete(id); }
  document.querySelectorAll(".device-card.empty").forEach(el=>el.remove());
  state.devices.forEach((d,i)=> {
    const card = cards.get(d.id) || makeCard(d);
    if (!card.isConnected) $("devices").append(card);
    card.classList.toggle("active",d.active);
    card.querySelector(".device-number").textContent = `MIC 0${i+1}`;
    card.querySelector(".device-name").textContent = d.name;
    card.querySelector(".device-name").title = d.name;
    card.querySelector(".device-status").textContent = d.muted ? "Muted" : d.stale ? "No signal" : d.active ? (running ? "On air" : "Selected") : "Standby";
    card.querySelector(".device-detail").textContent = d.muted ? "Excluded from output" : d.stale ? "Keep the sender screen awake" : state.pinned===d.id ? "Pinned · automatic switching paused" : d.active ? "Taking the lead" : "Ready when you speak";
    meter(card.querySelector(".meter>div"),d.level_db);
    card.querySelector(".level-text").textContent = db(d.level_db);
    card.querySelector(".mute").textContent = d.muted ? "Unmute" : "Mute";
    card.querySelector(".mute").classList.toggle("selected",d.muted);
    card.querySelector(".pin").textContent = state.pinned===d.id ? "Unpin" : "Pin mic";
    card.querySelector(".pin").classList.toggle("selected",state.pinned===d.id);
    if (document.activeElement!==card.querySelector(".gain")) {
      card.querySelector(".gain").value=d.gain_db;
      card.querySelector(".gain-label").textContent=`${d.gain_db>0?"+":""}${d.gain_db} dB`;
    }
  });
  for(let i=state.devices.length;i<4;i++) {
    const empty=document.createElement("article"); empty.className="device-card empty";
    const symbol=document.createElement("span");symbol.className="empty-symbol";symbol.textContent="+";
    const title=document.createElement("p");title.textContent=`Microphone ${i+1}`;
    const hint=document.createElement("small");hint.textContent="Waiting to connect";
    empty.append(symbol,title,hint);$("devices").append(empty);
  }
  for (const [key,label,unit] of [["delay_ms","delay-value","ms"],["gate_db","gate-value","dB"],["margin_db","margin-value","dB"],["hold_ms","hold-value","ms"]]) {
    if(document.activeElement!==$(key)) { $(key).value=state[key]; $(label).textContent=`${state[key]} ${unit}`; }
  }
  if(state.engine_error) error(`Audio engine: ${state.engine_error}`);
}
async function refresh() {
  if(busy) return; busy=true;
  try { render(await api("/api/state")); }
  catch(e) { $("connection").classList.add("offline");$("connection").lastChild.textContent=" Hub offline";error("Connection to the hub was lost. Check that the program is still running."); }
  finally {busy=false;}
}
async function refreshOutputs() {
  try {
    const selected=$("output-device").value;
    const data=await api("/api/outputs");outputs=data.devices;
    $("output-device").replaceChildren(new Option("Choose an output…",""),...outputs.map(d=>new Option(`${d.cable?"★ ":""}${d.name} · ${d.api}`,String(d.id))));
    const current=state?.output.device;
    const preferred=outputs.find(d=>d.cable && d.api==="Windows WASAPI") || outputs.find(d=>d.cable);
    $("output-device").value=current!==null && current!==undefined ? String(current) : outputs.some(d=>String(d.id)===selected) ? selected : String(preferred?.id ?? "");
    $("cable-help").hidden=outputs.some(d=>d.cable);
  } catch(e) { error(e.message); }
}
$("master").onclick=()=>state && control({action:"master",muted:!state.master_muted});
$("network").onchange=()=>{network=Number($("network").value);updateLinks();};
$("copy-link").onclick=async()=>{
  try { await navigator.clipboard.writeText(state.setup_urls[network]);$("copy-link").textContent="✓";setTimeout(()=>$("copy-link").textContent="⧉",1500); }
  catch(e){error("Copy this setup link manually: "+state.setup_urls[network]);}
};
$("rotate-code").onclick=()=>control({action:"rotate_code"});
$("refresh-outputs").onclick=refreshOutputs;
$("start-output").onclick=async()=>{
  if(state?.output.running) return control({action:"output_stop"});
  if(!$("output-device").value) return error("Select CABLE Input, or choose another audio output for a listening test.");
  $("start-output").disabled=true;
  await control({action:"output_start",device:Number($("output-device").value)});
  $("start-output").disabled=false;
};
for(const [key,label,unit] of [["delay_ms","delay-value","ms"],["gate_db","gate-value","dB"],["margin_db","margin-value","dB"],["hold_ms","hold-value","ms"]]) {
  $(key).oninput=()=>$(label).textContent=`${$(key).value} ${unit}`;
  $(key).onchange=()=>control({action:"settings",[key]:Number($(key).value)});
}
$("reset-settings").onclick=()=>control({action:"settings",delay_ms:180,gate_db:-60,margin_db:4,hold_ms:120});
$("stop-hub").onclick=async()=>{
  try { await api("/api/control",{action:"shutdown"}); }
  catch(e){error(e.message);}
};
refresh().then(refreshOutputs);setInterval(refresh,150);
