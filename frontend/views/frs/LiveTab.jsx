"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Icon } from "@iconify/react";

import { api, fileUrl } from "@/web/api";
import { Select } from "@/web/kit";

import { EVENT_COLOR, fmtTime, pct } from "./shared";

const TYPE_LABEL = { face_recognized: "Recognised", face_unknown: "Unknown", spoof_detected: "Spoof", face_detected: "Detected" };
// VMS grid layouts: cell-count -> column-count.
const LAYOUTS = [
  { n: 1, cols: 1 }, { n: 4, cols: 2 }, { n: 9, cols: 3 }, { n: 16, cols: 4 },
  { n: 25, cols: 5 }, { n: 36, cols: 6 }, { n: 48, cols: 8 },
];

function Tile({ cam, last }) {
  if (!cam) {
    return <div className="relative bg-black rounded-sm border border-white/5 flex items-center justify-center"><Icon icon="heroicons-outline:video-camera-slash" className="text-white/10 text-2xl" /></div>;
  }
  const online = cam.status === "online";
  return (
    <div className="relative bg-black rounded-sm overflow-hidden border border-white/10 group">
      {cam.snapshot_url ? (
        <img src={fileUrl(cam.snapshot_url)} alt={cam.name} className="absolute inset-0 h-full w-full object-cover" />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center"><Icon icon="heroicons-outline:video-camera" className="text-white/15 text-3xl" /></div>
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

export default function LiveTab() {
  const [layout, setLayout] = useState(9);
  const [showFeed, setShowFeed] = useState(false);
  const [selectedCamId, setSelectedCamId] = useState("");

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
            {cells.map((cam, i) => <Tile key={cam?.id || `empty-${i}`} cam={cam} last={cam ? latestByCam(cam.id) : null} />)}
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
                  <li key={e.id} className="flex items-center gap-2.5 px-3 py-2">
                    <div className="h-9 w-9 rounded-md bg-black/40 overflow-hidden shrink-0 flex items-center justify-center">
                      {e.snapshot_url ? <img src={fileUrl(e.snapshot_url)} alt="" className="h-full w-full object-cover" /> : <Icon icon="heroicons-outline:user" className="text-muted" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-foreground truncate">{e.person_name || TYPE_LABEL[e.event_type] || "Unknown"}</div>
                      <div className="text-[11px] text-muted truncate">{e.camera_name || "—"} · {fmtTime(e.triggered_at)}</div>
                    </div>
                    {e.confidence != null && <span className={`text-[11px] tabular-nums text-${EVENT_COLOR[e.event_type] || "slate"}-500`}>{pct(e.confidence)}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
