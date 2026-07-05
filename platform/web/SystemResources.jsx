"use client";

import { useQuery } from "@tanstack/react-query";
import { Icon } from "@iconify/react";

import { Badge, Card } from "@/web/kit";
import { api } from "@/web/api";

function toGB(bytes) {
  if (bytes == null) return "0";
  return (bytes / 1024 ** 3).toFixed(1);
}

function ringColor(percent) {
  if (percent >= 90) return "#ef4444"; // red-500
  if (percent >= 70) return "#f59e0b"; // amber-500
  return "#22c55e"; // green-500
}

// Compact radial gauge: a track ring + a colored progress arc with the % in the
// middle. Pure SVG so it stays crisp and theme-agnostic.
function Ring({ percent, size = 58, stroke = 6 }) {
  const p = Math.min(100, Math.max(0, Math.round(percent ?? 0)));
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (p / 100) * circ;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className="stroke-hover" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          stroke={ringColor(p)}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.6s ease" }}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-xs font-semibold text-foreground">
        {p}%
      </span>
    </div>
  );
}

function ResourceTile({ icon, label, percent, name, sub }) {
  return (
    <Card className="p-4 flex items-center gap-3">
      <Ring percent={percent} />
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 text-foreground text-sm font-medium">
          <Icon icon={icon} className="text-muted text-base shrink-0" />
          {label}
        </div>
        {name && (
          <div className="text-xs text-muted mt-0.5 truncate" title={name}>
            {name}
          </div>
        )}
        {sub && <div className="text-[11px] text-muted truncate">{sub}</div>}
      </div>
    </Card>
  );
}

function GpuTile({ gpus }) {
  if (!gpus.length) {
    return (
      <Card className="p-4 flex items-center gap-3">
        <div className="h-[58px] w-[58px] rounded-full bg-hover flex items-center justify-center shrink-0">
          <Icon icon="heroicons-outline:cpu-chip" className="text-xl text-muted" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-medium text-foreground">GPU</div>
          <div className="mt-1">
            <Badge color="slate">CPU host</Badge>
          </div>
        </div>
      </Card>
    );
  }
  const g = gpus[0];
  const extra = gpus.length - 1;
  const sub = [
    `${toGB(g.mem_used)} / ${toGB(g.mem_total)} GB`,
    g.temp != null ? `${Math.round(g.temp)}°C` : null,
    extra > 0 ? `+${extra} more` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Card className="p-4 flex items-center gap-3">
      <Ring percent={g.util_percent} />
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 text-foreground text-sm font-medium">
          <Icon icon="heroicons-outline:cpu-chip" className="text-blue-500 text-base shrink-0" />
          <span className="truncate">{g.name || `GPU ${g.index}`}</span>
        </div>
        <div className="text-xs text-muted mt-0.5 truncate">{sub}</div>
      </div>
    </Card>
  );
}

function SkeletonTile() {
  return (
    <Card className="p-4 flex items-center gap-3">
      <div className="h-[58px] w-[58px] rounded-full bg-hover animate-pulse shrink-0" />
      <div className="space-y-2">
        <div className="h-3 w-16 rounded bg-hover animate-pulse" />
        <div className="h-2.5 w-20 rounded bg-hover animate-pulse" />
      </div>
    </Card>
  );
}

// Live host resources as compact radial gauges (CPU / RAM / Disk / GPU). Emits a
// FRAGMENT of tiles (no wrapper) so the caller can lay them out in its own grid —
// e.g. sharing a single row with the Users metric on the dashboard.
export default function SystemResources() {
  const res = useQuery({
    queryKey: ["system-resources"],
    queryFn: () => api.get("/system/resources").then((r) => r.data),
    refetchInterval: 3000,
  });

  const data = res.data;
  const gpus = data?.gpus || [];

  if (res.isLoading) {
    return (
      <>
        <SkeletonTile />
        <SkeletonTile />
        <SkeletonTile />
        <SkeletonTile />
      </>
    );
  }

  const cpuSub = [
    data?.cpu_cores ? `${data.cpu_cores} cores` : null,
    data?.cpu_freq_ghz ? `${data.cpu_freq_ghz} GHz` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <>
      <ResourceTile
        icon="heroicons-outline:cpu-chip"
        label="CPU"
        percent={data?.cpu_percent}
        name={data?.cpu_name}
        sub={cpuSub}
      />
      <ResourceTile
        icon="heroicons-outline:circle-stack"
        label="RAM"
        percent={data?.ram?.percent}
        sub={`${toGB(data?.ram?.used)} / ${toGB(data?.ram?.total)} GB`}
      />
      <ResourceTile
        icon="heroicons-outline:server"
        label="Disk"
        percent={data?.disk?.percent}
        sub={`${toGB(data?.disk?.used)} / ${toGB(data?.disk?.total)} GB`}
      />
      <GpuTile gpus={gpus} />
    </>
  );
}
