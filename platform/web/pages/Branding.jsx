"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Icon } from "@iconify/react";

import { Button, Card, Input, PageHeader, Spinner, Toggle } from "@/web/kit";
import { api, apiError } from "@/web/api";

const DEFAULTS = { app_name: "", primary_color: "#4f46e5", accent_color: "#22d3ee", name_in_header: false };

export default function BrandingPage() {
  const qc = useQueryClient();
  const fileRef = useRef(null);
  const [form, setForm] = useState(DEFAULTS);

  const branding = useQuery({
    queryKey: ["branding"],
    queryFn: () => api.get("/branding").then((r) => r.data),
  });

  // Hydrate the form whenever the server data lands / refreshes.
  useEffect(() => {
    if (branding.data) {
      setForm({
        app_name: branding.data.app_name || "",
        primary_color: branding.data.primary_color || DEFAULTS.primary_color,
        accent_color: branding.data.accent_color || DEFAULTS.accent_color,
        name_in_header: !!branding.data.name_in_header,
      });
    }
  }, [branding.data]);

  const save = useMutation({
    mutationFn: (body) => api.put("/branding", body),
    onSuccess: () => {
      toast.success("Branding saved");
      qc.invalidateQueries({ queryKey: ["branding"] });
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const uploadLogo = useMutation({
    mutationFn: (file) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.post("/branding/logo", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
    },
    onSuccess: () => {
      toast.success("Logo updated");
      qc.invalidateQueries({ queryKey: ["branding"] });
    },
    onError: (e) => toast.error(apiError(e)),
  });

  function onPickLogo(e) {
    const file = e.target.files?.[0];
    if (file) uploadLogo.mutate(file);
    e.target.value = ""; // allow re-selecting the same file
  }

  const logoUrl = branding.data?.logo_url;

  if (branding.isLoading) {
    return (
      <div>
        <PageHeader title="Branding" subtitle="White-label the look of your deployment." />
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Branding"
        subtitle="White-label the app name, colors, and logo shown to your users."
        actions={
          <Button
            icon="heroicons-outline:check"
            disabled={save.isPending}
            onClick={() => save.mutate(form)}
          >
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Editor */}
        <div className="lg:col-span-2 space-y-6">
          <Card className="p-6 space-y-5">
            <Input
              label="App name"
              value={form.app_name}
              onChange={(e) => setForm({ ...form, app_name: e.target.value })}
              placeholder="wonin.ai"
              hint="Always used for the browser tab title."
            />

            <div className="flex items-center justify-between rounded-lg border border-card-border px-3 py-2.5">
              <div>
                <div className="text-sm font-medium text-foreground">Show app name in header</div>
                <div className="text-xs text-muted">
                  Replace the default mark with your app name. A custom logo overrides this.
                </div>
              </div>
              <Toggle
                checked={form.name_in_header}
                onChange={(v) => setForm({ ...form, name_in_header: v })}
              />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <ColorField
                label="Primary color"
                value={form.primary_color}
                onChange={(v) => setForm({ ...form, primary_color: v })}
              />
              <ColorField
                label="Accent color"
                value={form.accent_color}
                onChange={(v) => setForm({ ...form, accent_color: v })}
              />
            </div>
          </Card>

          <Card className="p-6">
            <h3 className="text-base font-semibold text-foreground mb-1">Logo</h3>
            <p className="text-sm text-muted mb-4">
              PNG or SVG works best. Uploads apply immediately.
            </p>
            <div className="flex items-center gap-5">
              <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-xl border border-card-border border-card-border bg-hover bg-hover">
                {logoUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={logoUrl} alt="Logo" className="h-full w-full object-contain" />
                ) : (
                  <Icon
                    icon="heroicons-outline:photo"
                    className="text-3xl text-muted text-muted"
                  />
                )}
              </div>
              <div>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  onChange={onPickLogo}
                  className="hidden"
                />
                <Button
                  variant="secondary"
                  icon="heroicons-outline:arrow-up-tray"
                  disabled={uploadLogo.isPending}
                  onClick={() => fileRef.current?.click()}
                >
                  {uploadLogo.isPending ? "Uploading…" : "Upload logo"}
                </Button>
              </div>
            </div>
          </Card>
        </div>

        {/* Live preview */}
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted mb-2">
            Live preview
          </p>
          <Card className="overflow-hidden">
            {/* Mini app-bar */}
            <div
              className="flex items-center gap-3 px-4 py-3"
              style={{ backgroundColor: form.primary_color }}
            >
              <div className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-md bg-white/10">
                {logoUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={logoUrl} alt="Logo" className="h-full w-full object-contain" />
                ) : (
                  <Icon icon="heroicons-outline:sparkles" className="text-lg text-foreground" />
                )}
              </div>
              <span className="font-semibold text-foreground truncate">
                {form.app_name || "Your App"}
              </span>
              <span
                className="ml-auto rounded-full px-2.5 py-0.5 text-xs font-medium text-foreground"
                style={{ backgroundColor: form.accent_color }}
              >
                Live
              </span>
            </div>
            <div className="p-4 space-y-3">
              <div className="h-2.5 w-3/4 rounded-full bg-hover bg-hover" />
              <div className="h-2.5 w-1/2 rounded-full bg-hover bg-hover" />
              <div className="flex gap-2 pt-2">
                <span
                  className="rounded-lg px-3 py-1.5 text-xs font-medium text-foreground"
                  style={{ backgroundColor: form.primary_color }}
                >
                  Primary
                </span>
                <span
                  className="rounded-lg px-3 py-1.5 text-xs font-medium text-foreground"
                  style={{ backgroundColor: form.accent_color }}
                >
                  Accent
                </span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

// A color swatch that wraps a native <input type="color"> in the kit look and
// keeps a text field in sync for precise hex entry.
function ColorField({ label, value, onChange }) {
  return (
    <div>
      <span className="block text-sm font-medium text-muted text-muted mb-1">
        {label}
      </span>
      <div className="flex items-center gap-2 rounded-lg border border-card-border border-card-border px-2 py-1.5">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 w-10 cursor-pointer rounded border-0 bg-transparent p-0"
        />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full bg-transparent text-sm text-foreground text-foreground outline-none"
        />
      </div>
    </div>
  );
}
