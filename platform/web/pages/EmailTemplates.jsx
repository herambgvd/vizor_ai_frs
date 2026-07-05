"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Card, Input, Modal, PageHeader, Spinner, Textarea } from "@/web/kit";
import { api, apiError } from "@/web/api";

function TemplateModal({ name, onClose }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ subject: "", html: "" });

  const detail = useQuery({
    queryKey: ["messaging-template", name],
    queryFn: () => api.get(`/messaging/templates/${name}`).then((r) => r.data),
    enabled: !!name,
  });

  useEffect(() => {
    if (detail.data) setForm({ subject: detail.data.subject || "", html: detail.data.html || "" });
  }, [detail.data]);

  const save = useMutation({
    mutationFn: () => api.put(`/messaging/templates/${name}`, form),
    onSuccess: () => {
      toast.success("Template saved");
      qc.invalidateQueries({ queryKey: ["messaging-templates"] });
      qc.invalidateQueries({ queryKey: ["messaging-template", name] });
      onClose();
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const revert = useMutation({
    mutationFn: () => api.delete(`/messaging/templates/${name}`),
    onSuccess: () => {
      toast.success("Reverted to default");
      qc.invalidateQueries({ queryKey: ["messaging-templates"] });
      qc.invalidateQueries({ queryKey: ["messaging-template", name] });
      onClose();
    },
    onError: (e) => toast.error(apiError(e)),
  });

  return (
    <Modal
      open={!!name}
      onClose={onClose}
      wide
      title={`Template · ${name}`}
      footer={
        <>
          {detail.data?.is_override && (
            <Button
              variant="danger"
              icon="heroicons-outline:arrow-uturn-left"
              className="mr-auto"
              disabled={revert.isPending}
              onClick={() => revert.mutate()}
            >
              {revert.isPending ? "Reverting…" : "Revert to default"}
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button disabled={save.isPending || detail.isLoading} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      {detail.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="space-y-4">
          <Input
            label="Subject"
            value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })}
            placeholder="Subject line…"
          />
          <Textarea
            label="HTML body"
            rows={14}
            className="font-mono !text-xs"
            value={form.html}
            onChange={(e) => setForm({ ...form, html: e.target.value })}
            placeholder="<html>…</html>"
          />
        </div>
      )}
    </Modal>
  );
}

// Read-only preview: renders the actual email HTML in an isolated iframe so its
// own styles don't leak into the app (and vice-versa) — an enterprise touch.
function PreviewModal({ name, onClose }) {
  // Rendered with sample data + branded shell on the server (not raw Jinja).
  const detail = useQuery({
    queryKey: ["messaging-template-preview", name],
    queryFn: () => api.get(`/messaging/templates/${name}/preview`).then((r) => r.data),
    enabled: !!name,
  });
  const d = detail.data;

  return (
    <Modal
      open={!!name}
      onClose={onClose}
      wide
      title={`Preview · ${name}`}
      footer={<Button variant="secondary" onClick={onClose}>Close</Button>}
    >
      {detail.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <span className="block text-xs font-medium text-muted mb-1">Subject</span>
            <div className="rounded-lg border border-card-border bg-hover px-3 py-2 text-sm text-foreground">
              {d?.subject || "—"}
            </div>
          </div>
          <div>
            <span className="block text-xs font-medium text-muted mb-1">Rendered email</span>
            <iframe
              title="Email preview"
              srcDoc={d?.html || "<p style='font-family:sans-serif;color:#666'>This template has no body.</p>"}
              className="w-full h-[440px] rounded-lg border border-card-border bg-white"
            />
          </div>
        </div>
      )}
    </Modal>
  );
}

// Friendly metadata per known template — icon + "when is this sent" description.
const TEMPLATE_META = {
  alert: {
    icon: "heroicons-outline:bell-alert",
    desc: "Sent when an alert rule fires.",
  },
  report_ready: {
    icon: "heroicons-outline:document-chart-bar",
    desc: "Sent when a report finishes generating.",
  },
  welcome: {
    icon: "heroicons-outline:hand-raised",
    desc: "Sent to a new user after their account is created.",
  },
};

function titleCase(name) {
  return (name || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function EmailTemplatesPage() {
  const [openTemplate, setOpenTemplate] = useState(null);
  const [previewName, setPreviewName] = useState(null);

  const templates = useQuery({
    queryKey: ["messaging-templates"],
    queryFn: () => api.get("/messaging/templates").then((r) => r.data),
  });

  return (
    <div>
      <PageHeader
        title="Email Templates"
        subtitle="Customize the transactional emails your platform sends, or revert them to defaults."
      />

      {templates.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {(templates.data || []).map((t) => {
            const meta = TEMPLATE_META[t.name] || {
              icon: "heroicons-outline:envelope",
              desc: "Transactional email.",
            };
            return (
              <Card key={t.name} className="p-5 flex flex-col">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="h-9 w-9 shrink-0 rounded-lg bg-hover border border-card-border flex items-center justify-center text-muted">
                      <Icon icon={meta.icon} className="text-lg" />
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-base font-semibold text-foreground truncate">{titleCase(t.name)}</h3>
                      <p className="text-xs text-muted line-clamp-2">{meta.desc}</p>
                    </div>
                  </div>
                  <Badge color={t.overridden ? "green" : "slate"}>
                    {t.overridden ? "Customized" : "Default"}
                  </Badge>
                </div>

                <div className="mt-4 rounded-lg border border-card-border bg-hover px-3 py-2">
                  <div className="text-[11px] font-medium uppercase tracking-wide text-muted mb-0.5">
                    Subject
                  </div>
                  <code className="block font-mono text-xs text-foreground break-all">
                    {t.subject || "—"}
                  </code>
                </div>

                <div className="mt-4 pt-4 border-t border-card-border flex items-center gap-2">
                  <Button variant="secondary" icon="heroicons-outline:eye" onClick={() => setPreviewName(t.name)}>
                    Preview
                  </Button>
                  <Button
                    variant="secondary"
                    icon="heroicons-outline:pencil-square"
                    onClick={() => setOpenTemplate(t.name)}
                  >
                    Edit
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <PreviewModal name={previewName} onClose={() => setPreviewName(null)} />
      <TemplateModal name={openTemplate} onClose={() => setOpenTemplate(null)} />
    </div>
  );
}
