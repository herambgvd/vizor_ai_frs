"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Card, Drawer, EmptyState, Modal, Spinner } from "@/web/kit";
import { api, apiError, fileUrl } from "@/web/api";

import { confColor, fmt } from "./shared";

export default function InvestigateTab() {
  const qc = useQueryClient();
  const fileRef = useRef(null);
  const [preview, setPreview] = useState(null);
  const [file, setFile] = useState(null);
  const [minScore, setMinScore] = useState(0.45);
  const [maxResults, setMaxResults] = useState(100);
  const [hits, setHits] = useState(null);
  const [meta, setMeta] = useState(null);
  const [detail, setDetail] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  const jobs = useQuery({ queryKey: ["frs-investigations"], queryFn: () => api.get("/frs/investigations").then((r) => r.data.items) });

  const search = useMutation({
    mutationFn: () => { const fd = new FormData(); fd.append("file", file); fd.append("min_score", String(minScore)); fd.append("top_k", String(maxResults)); return api.post("/frs/investigate", fd).then((r) => r.data); },
    onSuccess: (data) => { setHits(data.hits || []); setMeta({ total: data.total, min: minScore }); qc.invalidateQueries({ queryKey: ["frs-investigations"] }); if (data.error) toast.error(data.error); },
    onError: (e) => toast.error(apiError(e)),
  });

  function onPick(e) { const f = e.target.files?.[0]; e.target.value = ""; if (!f) return; setFile(f); setPreview(URL.createObjectURL(f)); setHits(null); }
  function reset() { setFile(null); setPreview(null); setHits(null); setMeta(null); }

  async function loadJob(id) {
    try { const { data } = await api.get(`/frs/investigations/${id}`); setHits(data.results || []); setMeta({ total: data.result_count, min: data.similarity_threshold }); setPreview(null); setFile(null); setHistoryOpen(false); }
    catch (e) { toast.error(apiError(e)); }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-10 items-start">
      {/* left: query */}
      <Card className="p-5 space-y-4 lg:col-span-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground">Query face</span>
          <button onClick={() => setHistoryOpen(true)} className="text-xs text-muted hover:text-foreground flex items-center gap-1"><Icon icon="heroicons-outline:clock" /> History</button>
        </div>
        <div onClick={() => fileRef.current?.click()} className="relative aspect-square rounded-lg border border-dashed border-card-border bg-hover/30 flex items-center justify-center cursor-pointer overflow-hidden hover:border-muted transition">
          {preview ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={preview} alt="query" className="h-full w-full object-cover" />
              <button onClick={(e) => { e.stopPropagation(); reset(); }} className="absolute top-2 right-2 p-1 rounded-full bg-black/60 text-white"><Icon icon="heroicons-outline:x-mark" /></button>
            </>
          ) : (
            <div className="text-center text-muted"><Icon icon="heroicons-outline:arrow-up-tray" className="text-3xl mx-auto mb-2" /><div className="text-sm">Drop image or click</div></div>
          )}
        </div>
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onPick} />
        <div>
          <div className="flex items-center justify-between text-xs text-muted mb-1"><span>Similarity</span><span>{minScore.toFixed(2)}</span></div>
          <input type="range" min="0.3" max="0.95" step="0.01" value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} className="w-full accent-foreground" />
        </div>
        <div>
          <span className="block text-xs text-muted mb-1">Max results</span>
          <input type="number" min="1" max="1000" value={maxResults} onChange={(e) => setMaxResults(Number(e.target.value) || 100)} className="w-full rounded-md border border-card-border bg-transparent px-3 py-2 text-sm text-foreground outline-none focus:border-muted" />
        </div>
        <div className="flex gap-2">
          <Button variant="primary" icon="heroicons-outline:magnifying-glass" disabled={!file || search.isPending} onClick={() => search.mutate()}>{search.isPending ? "Searching…" : "Search"}</Button>
          <Button variant="secondary" onClick={reset}>Reset</Button>
        </div>
      </Card>

      {/* right: results */}
      <Card className="p-4 lg:col-span-7 min-h-[360px]">
        <div className="flex items-center justify-between mb-3 px-1">
          <div>
            <div className="text-sm font-semibold text-foreground">Results</div>
            <div className="text-xs text-muted">{meta ? `${meta.total} match${meta.total === 1 ? "" : "es"} · similarity ${meta.min}` : "Upload a query face to search…"}</div>
          </div>
        </div>
        {search.isPending ? (
          <div className="flex flex-col items-center justify-center py-20 text-muted"><Spinner /><div className="text-sm mt-3">Searching for matches…</div></div>
        ) : hits == null ? (
          <EmptyState icon="heroicons-outline:magnifying-glass" title="Run an investigation" subtitle="Matches will appear here." />
        ) : hits.length === 0 ? (
          <EmptyState icon="heroicons-outline:face-frown" title="No matches" subtitle={`No sightings above ${meta?.min} similarity.`} />
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3">
            {hits.map((h) => (
              <button key={h.event_id} onClick={() => setDetail(h)} className="text-left rounded-lg border border-card-border overflow-hidden bg-hover/30 hover:border-muted transition">
                <div className="relative aspect-square bg-black/20 overflow-hidden">
                  {h.snapshot_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={fileUrl(h.snapshot_url)} alt="hit" className="h-full w-full object-cover" />
                  ) : <div className="h-full flex items-center justify-center text-muted"><Icon icon="heroicons-outline:photo" className="text-2xl" /></div>}
                  <span className={`absolute top-1.5 right-1.5 text-[11px] px-1.5 rounded font-medium text-white ${confColor(h.similarity_score) === "green" ? "bg-green-500/80" : confColor(h.similarity_score) === "amber" ? "bg-amber-500/80" : "bg-red-500/80"}`}>{Math.round((h.similarity_score || 0) * 100)}%</span>
                </div>
                <div className="p-2">
                  <div className="text-sm font-medium text-foreground truncate flex items-center gap-1"><Icon icon="heroicons-outline:user" className="text-xs shrink-0" />{h.person_name || "Unknown"}</div>
                  <div className="text-[11px] text-muted truncate flex items-center gap-1"><Icon icon="heroicons-outline:clock" className="shrink-0" />{fmt(h.frame_timestamp)}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>

      {/* hit detail */}
      <Modal open={!!detail} onClose={() => setDetail(null)} wide title="Sighting detail">
        {detail && (
          <div className="grid gap-4 sm:grid-cols-5">
            <div className="sm:col-span-3 aspect-square bg-black/30 rounded-lg overflow-hidden flex items-center justify-center">
              {detail.snapshot_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={fileUrl(detail.snapshot_url)} alt="snapshot" className="max-h-full max-w-full object-contain" />
              )}
            </div>
            <div className="sm:col-span-2 space-y-2 text-sm">
              {[["Person", detail.person_name || "Unknown"], ["Similarity", `${Math.round((detail.similarity_score || 0) * 100)}%`], ["Camera", detail.camera_name || "—"], ["Type", detail.event_type], ["Time", fmt(detail.frame_timestamp)], ["Liveness", detail.liveness_score ?? "—"], ["Age", detail.age || "—"], ["Gender", detail.gender || "—"]].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-card-border pb-1.5"><span className="text-muted">{k}</span><span className="text-foreground text-right">{v}</span></div>
              ))}
            </div>
          </div>
        )}
      </Modal>

      {/* history */}
      <Drawer open={historyOpen} onClose={() => setHistoryOpen(false)} title="History" subtitle={`${jobs.data?.length || 0} investigations`}>
        {!jobs.data?.length ? <EmptyState icon="heroicons-outline:clock" title="No investigations yet" /> : (
          <ul className="divide-y divide-card-border">
            {jobs.data.map((j) => (
              <li key={j.id}><button onClick={() => loadJob(j.id)} className="w-full text-left py-3 flex items-center justify-between hover:text-foreground">
                <span className="text-sm text-muted">{fmt(j.created_at)}</span>
                <Badge color={j.status === "done" ? "green" : "amber"}>{j.result_count} hits</Badge>
              </button></li>
            ))}
          </ul>
        )}
      </Drawer>
    </div>
  );
}
