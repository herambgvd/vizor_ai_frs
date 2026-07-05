"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Card, Input, PageHeader, Spinner, Toggle } from "@/web/kit";
import { api, apiError } from "@/web/api";

// Config fields per channel — the shape the backend expects under `config`.
const CHANNEL_FIELDS = {
  email: [
    { key: "host", label: "SMTP host", placeholder: "smtp.example.com" },
    { key: "port", label: "Port", placeholder: "587" },
    { key: "username", label: "Username", placeholder: "no-reply@example.com" },
    { key: "password", label: "Password", type: "password" },
    { key: "from_addr", label: "From address", placeholder: "Neubit <no-reply@example.com>" },
    { key: "use_tls", label: "Use TLS", type: "bool" },
  ],
  push: [{ key: "server_key", label: "FCM server key", type: "password" }],
  webhook: [
    { key: "url", label: "Endpoint URL", placeholder: "https://hooks.example.com/neubit" },
    { key: "secret", label: "Signing secret", type: "password" },
  ],
};

const CHANNEL_META = {
  email: { title: "Email (SMTP)", icon: "heroicons-outline:envelope" },
  push: { title: "Push (FCM)", icon: "heroicons-outline:device-phone-mobile" },
  webhook: { title: "Webhook", icon: "heroicons-outline:bolt" },
};

function ChannelCard({ channel }) {
  const qc = useQueryClient();
  const fields = CHANNEL_FIELDS[channel.channel] || [];
  const meta = CHANNEL_META[channel.channel] || { title: channel.channel, icon: "heroicons-outline:cog-6-tooth" };

  const [enabled, setEnabled] = useState(channel.enabled);
  const [config, setConfig] = useState(channel.config || {});
  // Track which fields the admin actually edited, so we can avoid re-sending
  // masked secrets (value "***" means unchanged).
  const [dirty, setDirty] = useState({});

  useEffect(() => {
    setEnabled(channel.enabled);
    setConfig(channel.config || {});
    setDirty({});
  }, [channel]);

  const save = useMutation({
    mutationFn: () => {
      const out = {};
      for (const f of fields) {
        const v = config[f.key];
        if (f.type === "password") {
          if (dirty[f.key] && v !== "***") out[f.key] = v;
        } else {
          out[f.key] = v;
        }
      }
      return api.put(`/messaging/channels/${channel.channel}`, { enabled, config: out });
    },
    onSuccess: () => {
      toast.success(`${meta.title} saved`);
      qc.invalidateQueries({ queryKey: ["messaging-channels"] });
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const test = useMutation({
    mutationFn: () => api.post(`/messaging/channels/${channel.channel}/test`),
    onSuccess: () => toast.success("Test message sent"),
    onError: (e) => toast.error(apiError(e)),
  });

  const setField = (key, value) => {
    setConfig((c) => ({ ...c, [key]: value }));
    setDirty((d) => ({ ...d, [key]: true }));
  };

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-2">
          <Badge color={enabled ? "green" : "slate"}>{enabled ? "Enabled" : "Disabled"}</Badge>
          <h3 className="text-base font-semibold text-foreground">{meta.title}</h3>
        </div>
        <Toggle checked={enabled} onChange={setEnabled} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) =>
          f.type === "bool" ? (
            <div key={f.key} className="flex items-center justify-between rounded-lg border border-card-border px-3 py-2.5">
              <span className="text-sm font-medium text-muted">{f.label}</span>
              <Toggle checked={!!config[f.key]} onChange={(v) => setField(f.key, v)} />
            </div>
          ) : (
            <Input
              key={f.key}
              label={f.label}
              type={f.type || "text"}
              value={config[f.key] ?? ""}
              placeholder={f.placeholder}
              onChange={(e) => setField(f.key, e.target.value)}
            />
          ),
        )}
      </div>

      <div className="flex items-center gap-2 mt-5">
        <Button icon="heroicons-outline:check" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        <Button
          variant="secondary"
          icon="heroicons-outline:paper-airplane"
          disabled={test.isPending || !enabled}
          onClick={() => test.mutate()}
        >
          {test.isPending ? "Sending…" : "Send test"}
        </Button>
      </div>
    </Card>
  );
}

export default function ChannelsPage() {
  const channels = useQuery({
    queryKey: ["messaging-channels"],
    queryFn: () => api.get("/messaging/channels").then((r) => r.data),
  });

  return (
    <div>
      <PageHeader
        title="Channels"
        subtitle="Configure how Neubit delivers notifications — email, push, and webhooks."
      />
      {channels.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
          {(channels.data || []).map((c) => (
            <ChannelCard key={c.channel} channel={c} />
          ))}
        </div>
      )}
    </div>
  );
}
