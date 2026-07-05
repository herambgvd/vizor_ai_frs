"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button, Card, Input, PageHeader, Spinner, Toggle } from "@/web/kit";
import { api, apiError } from "@/web/api";

// Renders one setting control based on its declared `type`.
function Field({ item, value, onChange }) {
  if (item.type === "bool") {
    return (
      <div className="flex items-center justify-between gap-4 py-3 border-b border-card-border last:border-0">
        <div className="min-w-0">
          <div className="text-sm font-medium text-foreground">{item.label}</div>
          {item.description && <div className="text-xs text-muted mt-0.5">{item.description}</div>}
        </div>
        <Toggle checked={!!value} onChange={(v) => onChange(v)} />
      </div>
    );
  }
  return (
    <div className="py-3 border-b border-card-border last:border-0">
      <Input
        label={item.label}
        type={item.type === "number" ? "number" : "text"}
        value={value ?? ""}
        onChange={(e) => onChange(item.type === "number" ? Number(e.target.value) : e.target.value)}
        hint={item.description}
      />
    </div>
  );
}

export default function SettingsGeneralPage() {
  const qc = useQueryClient();
  const cfg = useQuery({
    queryKey: ["settings-config"],
    queryFn: () => api.get("/settings").then((r) => r.data),
  });

  const [values, setValues] = useState({});
  useEffect(() => {
    if (cfg.data?.values) setValues(cfg.data.values);
  }, [cfg.data]);

  const save = useMutation({
    mutationFn: () => api.put("/settings", { values }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings-config"] });
      qc.invalidateQueries({ queryKey: ["public-settings"] });
      toast.success("Settings saved");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const catalog = cfg.data?.catalog || [];
  const groups = [...new Set(catalog.map((c) => c.group))];

  return (
    <div>
      <PageHeader
        title="General settings"
        subtitle="Platform-wide options an administrator can change."
        actions={
          <Button variant="primary" disabled={save.isPending || cfg.isLoading} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save changes"}
          </Button>
        }
      />

      {cfg.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="space-y-6 max-w-2xl">
          {groups.map((group) => (
            <Card key={group} className="p-5">
              <h2 className="text-sm font-semibold text-foreground mb-1">{group}</h2>
              <div>
                {catalog
                  .filter((c) => c.group === group)
                  .map((item) => (
                    <Field
                      key={item.key}
                      item={item}
                      value={values[item.key]}
                      onChange={(v) => setValues((prev) => ({ ...prev, [item.key]: v }))}
                    />
                  ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
