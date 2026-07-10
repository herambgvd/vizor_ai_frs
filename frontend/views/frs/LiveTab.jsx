"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Icon } from "@iconify/react";

import { api, fileUrl, tokens } from "@/web/api";
import { Badge, Modal, Select } from "@/web/kit";

import { EVENT_COLOR, confColor, fmt, fmtTime, pct } from "./shared";

const TYPE_LABEL = { face_recognized: "Recognised", face_unknown: "Unknown", spoof_detected: "Spoof", face_detected: "Detected", transit_overdue: "Transit Overdue" };
// VMS grid layouts: cell-count -> column-count.
const LAYOUTS = [
  { n: 1, cols: 1 }, { n: 4, cols: 2 }, { n: 9, cols: 3 }, { n: 16, cols: 4 },
  { n: 25, cols: 5 }, { n: 36, cols: 6 }, { n: 48, cols: 8 },
];

// =============================================================================
// Audio-alert subsystem — ported from vizor_nvr's LiveTab.js. On each new
// recognition event pushed over the SSE stream we play (gated by the operator's
// mute + the matched group's alert_sound): a WebAudio beep, a SpeechSynthesis
// announcement, and/or a server-synthesised TTS clip. Everything is wrapped so an
// autoplay-block or an unsupported browser (no AudioContext / SpeechSynthesis)
// NEVER throws — the events still render, they just stay silent.
// =============================================================================

// --- WebAudio beep cues ------------------------------------------------------
let _audioCtx = null;
function _getAudioCtx() {
  if (typeof window === "undefined") return null;
  if (!_audioCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    _audioCtx = new Ctx();
  }
  if (_audioCtx.state === "suspended") _audioCtx.resume().catch(() => {});
  return _audioCtx;
}

// Sharp alert — new unknown / spoof / unauthorized the operator must notice.
function playAlertBeep() {
  try {
    const ctx = _getAudioCtx();
    if (!ctx) return;
    const t0 = ctx.currentTime;
    for (const [freq, at] of [[1000, t0], [700, t0 + 0.14]]) {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "square";
      o.frequency.value = freq;
      g.gain.setValueAtTime(0.0001, at);
      g.gain.exponentialRampToValueAtTime(0.5, at + 0.005);
      g.gain.exponentialRampToValueAtTime(0.0001, at + 0.12);
      o.connect(g).connect(ctx.destination);
      o.start(at);
      o.stop(at + 0.13);
    }
  } catch {
    /* autoplay policy / unsupported — ignore */
  }
}

// Soft chirp — informational cue for a new authorized recognition.
function playSoftBeep() {
  try {
    const ctx = _getAudioCtx();
    if (!ctx) return;
    const at = ctx.currentTime;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = "sine";
    o.frequency.value = 880;
    g.gain.setValueAtTime(0.0001, at);
    g.gain.exponentialRampToValueAtTime(0.12, at + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, at + 0.1);
    o.connect(g).connect(ctx.destination);
    o.start(at);
    o.stop(at + 0.12);
  } catch {
    /* ignore */
  }
}

// Alarm throttle — a crew walking past would otherwise stack overlapping beeps.
const ALARM_THROTTLE_MS = 1500;
let _lastAlarmAt = 0;
function playAlertBeepThrottled() {
  const now = Date.now();
  if (now - _lastAlarmAt < ALARM_THROTTLE_MS) return;
  _lastAlarmAt = now;
  playAlertBeep();
}

// --- Autoplay priming --------------------------------------------------------
// Browsers block audio/speech until the user interacts with the page. We "warm"
// the AudioContext, the shared TTS <audio> element and SpeechSynthesis under the
// first gesture so the very first real announcement actually plays.
let _audioPrimed = false;
function primeAudio() {
  try {
    const ctx = _getAudioCtx();
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
  } catch { /* no webaudio */ }
  try {
    const el = _getTtsEl();
    if (el) {
      el.muted = true;
      const p = el.play();
      if (p && p.then) p.then(() => { el.pause(); el.muted = false; }).catch(() => { el.muted = false; });
      else { el.pause(); el.muted = false; }
    }
  } catch { /* no audio el */ }
  if (_audioPrimed) return;
  _audioPrimed = true;
  _warmVoices();
  try {
    const synth = window.speechSynthesis;
    if (synth) {
      const u = new SpeechSynthesisUtterance(" ");
      u.volume = 0;
      synth.speak(u);
    }
  } catch {
    /* speech unavailable — beep fallback still works */
  }
}

// SpeechSynthesis voices load asynchronously — getVoices() is often empty until
// the engine fires `voiceschanged`. Warm it up and cache readiness.
let _voicesReady = false;
function _warmVoices() {
  try {
    const synth = window.speechSynthesis;
    if (!synth) return;
    if ((synth.getVoices() || []).length > 0) { _voicesReady = true; return; }
    synth.onvoiceschanged = () => {
      if ((synth.getVoices() || []).length > 0) _voicesReady = true;
    };
  } catch { /* no speech */ }
}

// --- Server TTS (espeak WAV) -------------------------------------------------
let _lastSpeakAt = 0;
let _serverTtsOk = true;   // flips false ONLY if the /frs/tts endpoint is truly gone
let _ttsEl = null;         // ONE shared, gesture-unlocked <audio> element
function _getTtsEl() {
  if (typeof window === "undefined") return null;
  if (!_ttsEl) { _ttsEl = new Audio(); _ttsEl.preload = "auto"; }
  return _ttsEl;
}

// Fetch the server-synthesised WAV as an authed blob (EventSource/<audio> can't
// send a bearer header, but this XHR can) and resolve to an object URL.
async function _ttsAudioUrl(phrase) {
  try {
    const r = await api.get("/frs/tts", { params: { text: phrase }, responseType: "blob" });
    if (!r?.data || r.data.size === 0) return null;
    return URL.createObjectURL(r.data);
  } catch {
    return null;
  }
}

// Play a server WAV on the shared, gesture-unlocked <audio>. Returns true if it
// took ownership of the announcement. A transient autoplay-block on play() must
// NOT disable server TTS forever — only a fetch failure (endpoint missing) does.
function speakServer(phrase) {
  if (!_serverTtsOk) return false;
  const el = _getTtsEl();
  if (!el) return false;
  if (!el.paused && !el.ended) return true; // an announcement is still playing
  _ttsAudioUrl(phrase).then((url) => {
    if (!url) { _serverTtsOk = false; return; }
    const prev = el.src;
    el.src = url;
    el.onended = () => { try { URL.revokeObjectURL(url); } catch { /* noop */ } };
    el.play().catch(() => { /* autoplay-blocked this once — keep trying next event */ });
    if (prev && prev.startsWith("blob:")) { try { URL.revokeObjectURL(prev); } catch { /* noop */ } }
  }).catch(() => { /* network blip — don't permanently disable */ });
  return true;
}

// Prefer a natural female en voice (Google US female → any female en → any en).
function _pickVoice(voices) {
  const en = voices.filter((v) => /^en/i.test(v.lang));
  const byName = (re) => en.find((v) => re.test(v.name || ""));
  return (
    byName(/google.*us.*english/i) ||
    byName(/female|samantha|zira|aria|jenny|libby|sonia/i) ||
    en[0] || voices[0] || null
  );
}

// Speak `phrase`: browser SpeechSynthesis first (natural system voices), server
// espeak TTS as the kiosk fallback. Returns true if something spoke (so the caller
// skips the beep), false if nothing could speak.
function speakPhrase(phrase) {
  if (!phrase) return false;
  const now = Date.now();
  if (now - _lastSpeakAt < ALARM_THROTTLE_MS) return true; // burst gate
  _lastSpeakAt = now;
  let synth = null;
  try { synth = window.speechSynthesis; } catch { synth = null; }
  const voices = (() => { try { return synth ? (synth.getVoices() || []) : []; } catch { return []; } })();
  if (synth && voices.length > 0) {
    if (synth.speaking || synth.pending) return true;
    try {
      const u = new SpeechSynthesisUtterance(phrase);
      u.rate = 1.0; u.pitch = 1.0; u.volume = 1.0;
      u.voice = _pickVoice(voices);
      synth.speak(u);
      return true;
    } catch { /* fall through to server TTS */ }
  }
  if (speakServer(phrase)) return true;
  return false; // caller beeps
}

// --- Phrase + gating ---------------------------------------------------------
// FRS spoken announcement (vizor_nvr parity), from the SSE event's top-level
// fields: authorized -> "Authorized <name>, <group>"; not authorized ->
// "Not Authorized. <reason>"; unknown -> "Unregistered person detected at <cam>".
function frsAnnouncePhrase(ev) {
  const cam = ev?.camera_name || ev?.camera_id || "camera";
  if (ev?.event_type === "spoof_detected") return "Spoof detected";
  if (ev?.event_type === "transit_overdue") {
    const name = ev?.person_name || "Person";
    return `Transit overdue. ${name} has not exited`;
  }
  if (ev?.event_type === "face_recognized") {
    const name = ev?.person_name || "person";
    if (ev?.authorized) {
      return ev?.group_name ? `Authorized ${name}, ${ev.group_name}` : `Authorized ${name}`;
    }
    return ev?.auth_reason ? `Not Authorized. ${ev.auth_reason}` : "Not Authorized";
  }
  return `Unregistered person detected at ${cam}`;
}

// FRS announces every fresh recognition + transit overdue.
function isFrsAnnounceEvent(ev) {
  return ["face_recognized", "face_unknown", "spoof_detected", "transit_overdue"].includes(ev?.event_type);
}

// A "violation" gets the sharp alert beep (when speech is unavailable); a routine
// authorized recognition gets the soft chirp.
function isViolationEvent(ev) {
  return ev?.event_type !== "face_recognized" || ev?.authorized === false;
}

// Alert gating: the matched group's `alert_sound` must be truthy for a RECOGNISED
// person's cue to fire (a group opts into audible alerts). Security events with no
// group — unknown / spoof / transit-overdue — always alert. `alertMap` is
// group-name -> alert_sound.
function shouldAlert(ev, alertMap) {
  const t = ev?.event_type;
  if (t === "face_recognized") {
    const g = ev?.group_name;
    if (g) return !!alertMap[g];   // group must have alert_sound set
    return true;                    // ungrouped recognition — can't gate; announce
  }
  return t === "face_unknown" || t === "spoof_detected" || t === "transit_overdue";
}

// Per-person throttle — the worker emits many sightings of the same face per
// second; announce a given person at most once per window.
const PERSON_THROTTLE_MS = 8000;
const _lastPerPerson = new Map();
function personThrottled(ev) {
  const key = ev?.person_id || ev?.person_name || `${ev?.event_type}:${ev?.camera_id}`;
  const now = Date.now();
  const last = _lastPerPerson.get(key) || 0;
  if (now - last < PERSON_THROTTLE_MS) return true;
  _lastPerPerson.set(key, now);
  return false;
}

// Absolute backend base for EventSource (axios' baseURL isn't reachable by the
// native EventSource, which also can't send an Authorization header — so we pass
// the access token as ?token=, matching the backend's SSE auth).
function _sseBase() {
  // Same-origin production builds set NEXT_PUBLIC_API_URL="" — keep it EMPTY (relative
  // URL through the reverse proxy). Use ?? not || so "" is preserved; || would treat
  // the empty string as falsy and wrongly fall back to http://host:8000 (a direct
  // backend port that isn't exposed behind Caddy → connection refused).
  const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
  return process.env.NEXT_PUBLIC_API_URL ?? `http://${host}:8000`;
}

// =============================================================================
// AI overlay helpers — colour + label for a recognition event drawn over a tile.
// Tint follows authorisation: authorised recognition green, not-authorised /
// spoof red, unknown amber, bare detection blue.
// =============================================================================
function overlayColor(ev) {
  if (ev?.event_type === "spoof_detected") return "#ef4444";
  if (ev?.event_type === "face_unknown") return "#f59e0b";
  if (ev?.authorized === false) return "#ef4444";
  if (ev?.authorized === true || ev?.event_type === "face_recognized") return "#22c55e";
  return "#3b82f6";
}
function overlayLabel(ev) {
  return ev?.person_name || (ev?.event_type === "face_unknown" ? "Unknown" : TYPE_LABEL[ev?.event_type] || "Detected");
}
const OVERLAY_TTL_MS = 4000;

// Low-latency WebRTC playback via MediaMTX WHEP (sub-second vs HLS's ~5–10s).
// POSTs the SDP offer to <webrtc>/whep, applies the answer, and attaches the
// remote MediaStream to the <video>. Returns the RTCPeerConnection (close() to
// tear down). Throws on failure so the tile can show "unavailable".
async function startWhep(video, whepUrl, onFail) {
  const pc = new RTCPeerConnection({ iceServers: [] });
  pc.addTransceiver("video", { direction: "recvonly" });
  pc.addTransceiver("audio", { direction: "recvonly" });
  pc.ontrack = (e) => {
    if (video && e.streams && e.streams[0]) {
      video.srcObject = e.streams[0];
      video.play?.().catch(() => {});
    }
  };
  pc.oniceconnectionstatechange = () => {
    if (["failed", "disconnected", "closed"].includes(pc.iceConnectionState)) onFail?.();
  };
  await pc.setLocalDescription(await pc.createOffer());
  // MediaMTX WHEP is happiest non-trickle: wait for ICE gathering (bounded).
  await new Promise((resolve) => {
    if (pc.iceGatheringState === "complete") return resolve();
    const check = () => {
      if (pc.iceGatheringState === "complete") {
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    };
    pc.addEventListener("icegatheringstatechange", check);
    setTimeout(resolve, 1500);
  });
  const res = await fetch(whepUrl, {
    method: "POST",
    headers: { "Content-Type": "application/sdp" },
    body: pc.localDescription.sdp,
  });
  if (!res.ok) { pc.close(); throw new Error(`WHEP ${res.status}`); }
  const answer = await res.text();
  await pc.setRemoteDescription({ type: "answer", sdp: answer });
  return pc;
}

// One VMS wall tile. Streams ONLY when a scenario (recognition/detection) is
// running on the camera — otherwise shows a "scenario off" placeholder (this is
// an AI VMS wall, not a plain NVR). Registers the camera path with MediaMTX and
// plays it over low-latency WebRTC (WHEP), and subscribes to the shared SSE
// stream to paint bbox / name-chip overlays. Every external call is guarded so a
// bad RTSP or a MediaMTX failure shows an "unavailable" tile instead of crashing.
function Tile({ cam, last, subscribeOverlay }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const boxesRef = useRef([]);   // {bbox:[x1,y1,x2,y2], color, label, born} — canvas-drawn
  const [chips, setChips] = useState([]); // corner name chips when no bbox in payload
  // connecting | live | offline | unavailable
  const [state, setState] = useState("connecting");

  const online = cam?.status === "online";
  const aiOn = !!cam && (cam.recognition_enabled || cam.detection_enabled);

  // --- Live video: ONLY stream when a scenario (recognition/detection) is running
  // on this camera — this is an AI VMS wall, not a plain NVR. If AI is off we show
  // a "scenario off" placeholder instead of a live feed. Streams via low-latency
  // WebRTC (MediaMTX WHEP). ---
  useEffect(() => {
    if (typeof window === "undefined" || !cam) return undefined;
    if (!online) { setState("offline"); return undefined; }
    if (!aiOn) { setState("scenario_off"); return undefined; }  // no scenario → no stream
    let cancelled = false;
    let pc = null;
    setState("connecting");
    (async () => {
      let webrtc;
      try {
        const r = await api.post(`/frs/live/streams/${cam.id}`);
        webrtc = r?.data?.webrtc;
      } catch {
        if (!cancelled) setState("unavailable");
        return;
      }
      const video = videoRef.current;
      if (cancelled || !webrtc || !video) { if (!cancelled) setState("unavailable"); return; }
      const whepUrl = webrtc.replace(/\/+$/, "") + "/whep";
      try {
        pc = await startWhep(video, whepUrl, () => { if (!cancelled) setState("unavailable"); });
      } catch {
        if (!cancelled) setState("unavailable");
      }
    })();
    return () => {
      cancelled = true;
      if (pc) { try { pc.close(); } catch { /* noop */ } }
      const v = videoRef.current;
      if (v) { try { v.srcObject = null; } catch { /* noop */ } }
    };
  }, [cam?.id, online, aiOn]);

  // --- AI overlay: subscribe to the shared SSE stream, buffer this camera's events ---
  useEffect(() => {
    if (!cam || !aiOn || typeof subscribeOverlay !== "function") return undefined;
    const unsub = subscribeOverlay((ev) => {
      if (String(ev?.camera_id) !== String(cam.id)) return;
      const color = overlayColor(ev);
      const label = overlayLabel(ev);
      const key = ev?.id || `${Date.now()}-${Math.random()}`;
      if (Array.isArray(ev?.bbox) && ev.bbox.length === 4) {
        boxesRef.current = [...boxesRef.current.slice(-11), { bbox: ev.bbox, color, label, born: Date.now() }];
      } else {
        // No coordinates in the payload — corner name chip instead of a box.
        setChips((prev) => [...prev.slice(-4), { key, label, color }]);
        setTimeout(() => setChips((prev) => prev.filter((c) => c.key !== key)), OVERLAY_TTL_MS);
      }
    });
    return unsub;
  }, [cam?.id, aiOn, subscribeOverlay]);

  // --- Canvas draw loop for bbox overlays (fades out over the TTL) -------------
  useEffect(() => {
    if (!cam || !aiOn) { boxesRef.current = []; return undefined; }
    let raf;
    const draw = () => {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      if (canvas && video) {
        const w = video.clientWidth || canvas.clientWidth;
        const h = video.clientHeight || canvas.clientHeight;
        if (canvas.width !== w) canvas.width = w;
        if (canvas.height !== h) canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, w, h);
        const now = Date.now();
        boxesRef.current = boxesRef.current.filter((b) => now - b.born < OVERLAY_TTL_MS);
        // Normalise bbox to the rendered size. Values ≤ 1 → fractions of the tile;
        // otherwise → pixels in the video's intrinsic resolution.
        const vw = video.videoWidth || w;
        const vh = video.videoHeight || h;
        for (const b of boxesRef.current) {
          const [x1, y1, x2, y2] = b.bbox;
          const norm = x2 <= 1 && y2 <= 1;
          const sx = norm ? w : w / vw;
          const sy = norm ? h : h / vh;
          const bx = x1 * sx, by = y1 * sy, bw = (x2 - x1) * sx, bh = (y2 - y1) * sy;
          const age = now - b.born;
          const alpha = age > OVERLAY_TTL_MS - 800 ? Math.max(0, (OVERLAY_TTL_MS - age) / 800) : 1;
          ctx.globalAlpha = alpha;
          ctx.lineWidth = 2;
          ctx.strokeStyle = b.color;
          ctx.strokeRect(bx, by, bw, bh);
          if (b.label) {
            ctx.font = "12px sans-serif";
            const tw = ctx.measureText(b.label).width + 8;
            ctx.fillStyle = b.color;
            ctx.fillRect(bx, Math.max(0, by - 16), tw, 16);
            ctx.fillStyle = "#000";
            ctx.fillText(b.label, bx + 4, Math.max(11, by - 4));
          }
          ctx.globalAlpha = 1;
        }
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [cam?.id, aiOn]);

  if (!cam) {
    return <div className="relative bg-black rounded-sm border border-white/5 flex items-center justify-center"><Icon icon="heroicons-outline:video-camera-slash" className="text-white/10 text-2xl" /></div>;
  }

  return (
    <div className="relative bg-black rounded-sm overflow-hidden border border-white/10 group">
      {/* live video */}
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        onPlaying={() => setState("live")}
        className="absolute inset-0 h-full w-full object-cover bg-black"
      />
      {/* AI overlay canvas (only mounted when recognition/detection is on) */}
      {aiOn && <canvas ref={canvasRef} className="absolute inset-0 h-full w-full pointer-events-none" />}
      {/* Region of interest outline — the configured monitoring area, drawn over the
          live feed so operators see the zone being analysed. */}
      {aiOn && Array.isArray(cam.roi) && cam.roi.length > 1 && (
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full pointer-events-none">
          <polygon
            points={cam.roi.map((p) => `${p[0] * 100},${p[1] * 100}`).join(" ")}
            fill="rgba(34,197,94,0.10)" stroke="#22c55e" strokeWidth="0.4"
          />
        </svg>
      )}
      {/* corner name chips (used when the event payload carries no bbox) */}
      {aiOn && chips.length > 0 && (
        <div className="absolute top-8 left-2 flex flex-col gap-1 pointer-events-none">
          {chips.map((c) => (
            <span key={c.key} className="px-1.5 py-0.5 rounded text-[10px] font-medium text-black shadow" style={{ backgroundColor: c.color }}>
              {c.label}
            </span>
          ))}
        </div>
      )}
      {/* connecting / offline / unavailable placeholder */}
      {state !== "live" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-center">
          {state === "offline" ? (
            <><Icon icon="heroicons-outline:video-camera-slash" className="text-white/20 text-3xl" /><span className="text-[10px] uppercase tracking-wider text-white/40">{cam.status}</span></>
          ) : state === "scenario_off" ? (
            <><Icon icon="heroicons-outline:pause-circle" className="text-white/20 text-3xl" /><span className="text-[10px] uppercase tracking-wider text-white/40">scenario off</span><span className="text-[9px] text-white/30 px-4">enable recognition to view live</span></>
          ) : state === "unavailable" ? (
            <><Icon icon="heroicons-outline:exclamation-triangle" className="text-white/25 text-3xl" /><span className="text-[10px] uppercase tracking-wider text-white/40">unavailable</span></>
          ) : (
            <><Icon icon="heroicons-outline:signal" className="text-white/25 text-2xl animate-pulse" /><span className="text-[10px] uppercase tracking-wider text-white/40">connecting…</span></>
          )}
        </div>
      )}
      {/* top bar: status dot + camera name */}
      <div className="absolute top-0 inset-x-0 flex items-center gap-1.5 px-2 py-1 bg-gradient-to-b from-black/70 to-transparent">
        <span className={`h-2 w-2 rounded-full shrink-0 ${online ? "bg-green-500" : cam.status === "error" ? "bg-red-500" : "bg-slate-500"}`} />
        <span className="text-[11px] font-medium text-white/90 truncate">{cam.name}</span>
        {!online && <span className="ml-auto text-[9px] uppercase tracking-wider text-white/50">{cam.status}</span>}
      </div>
      {/* bottom overlay: latest recognition on this camera */}
      {last && (
        <div className="absolute bottom-0 inset-x-0 flex items-center gap-1.5 px-2 py-1 bg-gradient-to-t from-black/80 to-transparent">
          <Icon icon="heroicons-solid:user-circle" className={`shrink-0 text-${EVENT_COLOR[last.event_type] || "slate"}-400`} />
          <span className="text-[11px] text-white truncate">{last.person_name || TYPE_LABEL[last.event_type] || "—"}</span>
          {last.confidence != null && <span className="ml-auto text-[10px] tabular-nums text-white/80">{pct(last.confidence)}</span>}
        </div>
      )}
    </div>
  );
}

// Full-frame snapshot with the detection box overlaid (same pattern as EventsTab).
function SnapshotWithBox({ url, bbox }) {
  const [dims, setDims] = useState(null);
  if (!url) return <Icon icon="heroicons-outline:photo" className="text-4xl text-muted" />;
  const box = Array.isArray(bbox) && bbox.length === 4 ? bbox.map(Number) : null;
  return (
    <div className="relative h-full w-full">
      <img src={fileUrl(url)} alt="" className="h-full w-full object-contain"
        onLoad={(e) => setDims({ w: e.target.naturalWidth, h: e.target.naturalHeight })} />
      {dims && box && (
        <svg viewBox={`0 0 ${dims.w} ${dims.h}`} preserveAspectRatio="xMidYMid meet" className="absolute inset-0 h-full w-full pointer-events-none">
          <rect x={box[0]} y={box[1]} width={box[2] - box[0]} height={box[3] - box[1]}
            fill="none" stroke="#22c55e" strokeWidth={Math.max(2, dims.w / 320)} />
        </svg>
      )}
    </div>
  );
}

function Row({ label, children }) {
  return <><dt className="text-muted">{label}</dt><dd className="text-foreground min-w-0 truncate">{children}</dd></>;
}

// Complete-info modal for a Live event (opened by clicking a card in the feed).
function LiveEventModal({ event, onClose }) {
  const e = event;
  return (
    <Modal open={!!e} onClose={onClose} title="Event details" wide>
      {e && (
        <div className="grid md:grid-cols-5 gap-4 items-stretch">
          <div className="md:col-span-3 flex flex-col">
            <div className="text-[10px] uppercase tracking-wider text-muted mb-1.5">Snapshot</div>
            <div className="flex-1 min-h-[240px] rounded-lg bg-black/40 border border-card-border overflow-hidden flex items-center justify-center">
              <SnapshotWithBox url={e.snapshot_url} bbox={e.bbox} />
            </div>
          </div>
          <div className="md:col-span-2 flex flex-col">
            <dl className="grid grid-cols-[92px_1fr] gap-x-3 gap-y-2 text-sm items-center">
              <Row label="Type"><Badge color={EVENT_COLOR[e.event_type] || "slate"}>{TYPE_LABEL[e.event_type] || e.event_type}</Badge></Row>
              <Row label="Person">{e.person_name || "Unknown"}</Row>
              {e.group_name && <Row label="Group">{e.group_name}</Row>}
              {e.authorized != null && (
                <Row label="Access">
                  <Badge color={e.authorized ? "green" : "red"}>{e.authorized ? "Authorized" : "Not authorized"}</Badge>
                </Row>
              )}
              {!e.authorized && e.auth_reason && <Row label="Reason">{e.auth_reason}</Row>}
              <Row label="Camera">{e.camera_name || "—"}</Row>
              {e.direction && <Row label="Direction">{e.direction}</Row>}
              {e.confidence != null && <Row label="Confidence"><span className={`text-${confColor(e.confidence)}-500`}>{pct(e.confidence)}</span></Row>}
              {e.liveness_score != null && <Row label="Liveness">{pct(e.liveness_score)}</Row>}
              {e.gender && <Row label="Gender">{e.gender}{e.gender_confidence != null ? ` (${pct(e.gender_confidence)})` : ""}</Row>}
              {e.age_range && <Row label="Age">{e.age_range}</Row>}
              {e.track_id && <Row label="Track">{e.track_id}</Row>}
              <Row label="Time">{fmt(e.triggered_at)}</Row>
            </dl>
          </div>
        </div>
      )}
    </Modal>
  );
}

export default function LiveTab() {
  const [layout, setLayout] = useState(9);
  const [showFeed, setShowFeed] = useState(false);
  const [selectedCamId, setSelectedCamId] = useState("");
  const [selectedEvent, setSelectedEvent] = useState(null);
  // Audio alerts: default ON (matches vizor_nvr). Ref mirror so the SSE handler
  // reads the latest value without re-subscribing.
  const [muted, setMuted] = useState(false);
  const mutedRef = useRef(muted);
  useEffect(() => { mutedRef.current = muted; }, [muted]);

  const cams = useQuery({
    queryKey: ["frs-cameras"],
    queryFn: () => api.get("/frs/cameras").then((r) => r.data),
    refetchInterval: 15000,
  });
  const live = useQuery({
    queryKey: ["frs-live"],
    queryFn: () => api.get("/frs/live", { params: { limit: 50 } }).then((r) => r.data.items),
    refetchInterval: 3000,
  });
  // Groups drive the alert-sound gate (group-name -> alert_sound). Kept in a ref
  // so the SSE handler always sees the freshest map.
  const groups = useQuery({
    queryKey: ["frs-groups-alert"],
    queryFn: () => api.get("/frs/groups").then((r) => r.data),
    refetchInterval: 60000,
  });
  const alertMapRef = useRef({});
  // Overlay fan-out: tiles register a listener here and the single SSE handler
  // below dispatches every event to them (independent of the audio mute).
  const overlayListenersRef = useRef(new Set());
  const subscribeOverlay = useCallback((fn) => {
    overlayListenersRef.current.add(fn);
    return () => overlayListenersRef.current.delete(fn);
  }, []);
  useEffect(() => {
    const m = {};
    (groups.data || []).forEach((g) => { if (g?.name) m[g.name] = g.alert_sound; });
    alertMapRef.current = m;
  }, [groups.data]);

  // Prime speech/audio on the operator's FIRST interaction anywhere on the page,
  // so the first recognition announces without them hunting for the Alerts button.
  useEffect(() => {
    const onGesture = () => {
      primeAudio();
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
    };
    window.addEventListener("pointerdown", onGesture);
    window.addEventListener("keydown", onGesture);
    return () => {
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
    };
  }, []);

  // Realtime alert layer — subscribe to the authenticated SSE stream and play the
  // gated audio cue per fresh recognition. The wall + events feed stay on their
  // 3s poll (above); this only adds sound. EventSource auto-reconnects and never
  // replays, so there's no backlog to de-dup.
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const token = tokens.access;
    if (!token) return undefined;
    const url = `${_sseBase()}/api/v1/frs/live/stream?token=${encodeURIComponent(token)}`;
    let es;
    try {
      es = new EventSource(url);
    } catch {
      return undefined;
    }
    es.onmessage = (e) => {
      let ev;
      try { ev = JSON.parse(e.data); } catch { return; }
      // Fan out to the per-tile AI overlays first (never gated by mute).
      overlayListenersRef.current.forEach((fn) => { try { fn(ev); } catch { /* noop */ } });
      // Audio-alert layer below — gated by the operator's mute.
      if (mutedRef.current) return;
      if (!isFrsAnnounceEvent(ev)) return;
      if (!shouldAlert(ev, alertMapRef.current)) return;
      if (personThrottled(ev)) return;
      const spoke = speakPhrase(frsAnnouncePhrase(ev));
      if (!spoke) {
        if (isViolationEvent(ev)) playAlertBeepThrottled();
        else playSoftBeep();
      }
    };
    es.onerror = () => { /* transient — EventSource reconnects automatically */ };
    return () => { try { es.close(); } catch { /* noop */ } };
  }, []);

  const cameras = cams.data || [];
  const feed = live.data || [];
  const online = cameras.filter((c) => c.status === "online").length;
  const cols = LAYOUTS.find((l) => l.n === layout)?.cols || 3;
  const single = cameras.find((c) => c.id === selectedCamId) || cameras[0] || null;
  const cells = layout === 1 ? [single] : Array.from({ length: layout }, (_, i) => cameras[i] || null);
  const latestByCam = (id) => feed.find((e) => e.camera_id === id);

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-2 shrink-0">
        <span className="flex items-center gap-1.5 text-xs"><span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" /><span className="text-muted">LIVE</span></span>
        <span className="text-sm text-muted"><span className="text-green-500">{online}</span> / {cameras.length} online</span>
        {layout === 1 && cameras.length > 0 && (
          <div className="w-52">
            <Select options={cameras.map((c) => ({ value: c.id, label: c.name }))} value={single?.id || ""} onChange={(e) => setSelectedCamId(e.target.value)} placeholder="Select camera" />
          </div>
        )}
        <div className="ml-auto flex items-center gap-1 rounded-lg border border-card-border bg-card p-0.5">
          {LAYOUTS.map((l) => (
            <button key={l.n} onClick={() => setLayout(l.n)} title={`${l.n}-up`}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition ${layout === l.n ? "bg-foreground text-background" : "text-muted hover:text-foreground hover:bg-hover"}`}>
              {l.n}
            </button>
          ))}
        </div>
        {/* Audio-alert mute toggle. Clicking IS the user gesture that unlocks
            autoplay, so prime here too — the first real announcement then speaks. */}
        <button
          onClick={() => { primeAudio(); setMuted((m) => !m); }}
          aria-pressed={muted}
          title={muted ? "Unmute audio alerts" : "Mute audio alerts"}
          className={`inline-flex items-center justify-center h-8 w-8 rounded-md border transition ${muted ? "border-card-border text-muted hover:text-foreground hover:bg-hover" : "bg-foreground text-background border-foreground"}`}>
          <Icon icon={muted ? "heroicons-outline:speaker-x-mark" : "heroicons-outline:speaker-wave"} className="text-base" />
        </button>
        <button onClick={() => setShowFeed((v) => !v)} title="Events feed"
          className={`inline-flex items-center justify-center h-8 w-8 rounded-md border transition ${showFeed ? "bg-foreground text-background border-foreground" : "border-card-border text-muted hover:text-foreground hover:bg-hover"}`}>
          <Icon icon="heroicons-outline:bell-alert" className="text-base" />
        </button>
      </div>

      {/* Wall + optional feed */}
      <div className="flex-1 min-h-0 flex gap-2">
        {cameras.length === 0 && !cams.isLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center text-muted border border-dashed border-card-border rounded-lg">
            <Icon icon="heroicons-outline:video-camera-slash" className="text-4xl mb-2" />
            <span className="text-sm">No cameras — add one to see the wall.</span>
          </div>
        ) : (
          <div className="flex-1 min-h-0 grid gap-1" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridAutoRows: "1fr" }}>
            {cells.map((cam, i) => <Tile key={cam?.id || `empty-${i}`} cam={cam} last={cam ? latestByCam(cam.id) : null} subscribeOverlay={subscribeOverlay} />)}
          </div>
        )}

        {showFeed && (
          <div className="w-72 shrink-0 rounded-lg border border-card-border bg-card flex flex-col min-h-0 overflow-hidden">
            <div className="px-3 py-2 border-b border-card-border text-xs uppercase tracking-wider text-muted">Events</div>
            {feed.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-muted text-sm gap-2"><Icon icon="heroicons-outline:signal" className="text-2xl" />Waiting for recognitions…</div>
            ) : (
              <ul className="flex-1 min-h-0 overflow-y-auto divide-y divide-card-border">
                {feed.map((e) => (
                  <li key={e.id}>
                    <button type="button" onClick={() => setSelectedEvent(e)}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-hover transition cursor-pointer">
                      <div className="h-9 w-9 rounded-md bg-black/40 overflow-hidden shrink-0 flex items-center justify-center">
                        {e.snapshot_url ? <img src={fileUrl(e.snapshot_url)} alt="" className="h-full w-full object-cover" /> : <Icon icon="heroicons-outline:user" className="text-muted" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-foreground truncate">{e.person_name || TYPE_LABEL[e.event_type] || "Unknown"}</div>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <Badge color={EVENT_COLOR[e.event_type] || "slate"}>{TYPE_LABEL[e.event_type] || e.event_type}</Badge>
                          <span className="text-[11px] text-muted truncate">{e.camera_name || "—"} · {fmtTime(e.triggered_at)}</span>
                        </div>
                      </div>
                      {e.confidence != null && <span className={`text-[11px] tabular-nums text-${EVENT_COLOR[e.event_type] || "slate"}-500`}>{pct(e.confidence)}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <LiveEventModal event={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </div>
  );
}
