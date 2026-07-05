"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Avatar, Badge, Button, Card, Input, PageHeader, Spinner, Toggle } from "@/web/kit";
import { api, apiError } from "@/web/api";
import { useAuth } from "@/web/auth";
import { useTheme } from "@/web/theme";

const TABS = [
  { key: "profile", label: "Profile", icon: "heroicons-outline:user-circle" },
  { key: "security", label: "Security", icon: "heroicons-outline:lock-closed" },
  { key: "sessions", label: "Sessions", icon: "heroicons-outline:computer-desktop" },
  { key: "preferences", label: "Preferences", icon: "heroicons-outline:adjustments-horizontal" },
];

// Friendly device label parsed from a User-Agent string.
function deviceLabel(ua) {
  if (!ua) return "Unknown device";
  const os = /Windows/i.test(ua)
    ? "Windows"
    : /iPhone|iPad|iOS/i.test(ua)
    ? "iOS"
    : /Mac OS X|Macintosh/i.test(ua)
    ? "macOS"
    : /Android/i.test(ua)
    ? "Android"
    : /Linux/i.test(ua)
    ? "Linux"
    : "Unknown OS";
  const browser = /Edg\//i.test(ua)
    ? "Edge"
    : /Chrome\//i.test(ua)
    ? "Chrome"
    : /Firefox\//i.test(ua)
    ? "Firefox"
    : /Safari\//i.test(ua)
    ? "Safari"
    : "Browser";
  return `${browser} on ${os}`;
}

function fmt(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

// --- Profile tab -------------------------------------------------------------
function ProfileTab() {
  const { user, reload } = useAuth();
  const [name, setName] = useState(user?.full_name || "");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => setName(user?.full_name || ""), [user?.full_name]);

  const save = useMutation({
    mutationFn: () => api.patch("/auth/me", { full_name: name }),
    onSuccess: async () => {
      await reload();
      toast.success("Profile updated");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  async function onPickAvatar(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.post("/auth/me/avatar", fd);
      await reload();
      toast.success("Photo updated");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setUploading(false);
    }
  }
  async function removeAvatar() {
    setUploading(true);
    try {
      await api.delete("/auth/me/avatar");
      await reload();
      toast.success("Photo removed");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3 items-start">
      <Card className="p-6 space-y-4 lg:col-span-1">
        <h2 className="text-sm font-semibold text-foreground">Profile photo</h2>
        <div className="flex flex-col items-center gap-4 py-2">
          <Avatar src={user?.avatar_url} name={user?.full_name || user?.email} size={96} />
          <div className="flex items-center gap-2">
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onPickAvatar} />
            <Button variant="secondary" icon="heroicons-outline:camera" disabled={uploading} onClick={() => fileRef.current?.click()}>
              {uploading ? "Uploading…" : user?.avatar_url ? "Change" : "Upload"}
            </Button>
            {user?.avatar_url && (
              <Button variant="ghost" icon="heroicons-outline:trash" disabled={uploading} onClick={removeAvatar}>
                Remove
              </Button>
            )}
          </div>
        </div>
      </Card>

      <Card className="p-6 space-y-5 lg:col-span-2">
        <h2 className="text-sm font-semibold text-foreground">Details</h2>
        <Input label="Full name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <span className="block text-sm font-medium text-foreground mb-1.5">Email</span>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted truncate">{user?.email}</span>
              <Badge color={user?.email_verified ? "green" : "amber"}>
                {user?.email_verified ? "Verified" : "Unverified"}
              </Badge>
            </div>
          </div>
          <div>
            <span className="block text-sm font-medium text-foreground mb-1.5">Role</span>
            <span className="text-sm text-muted">{user?.role?.name || "—"}</span>
          </div>
        </div>

        <div className="pt-2">
          <Button
            variant="primary"
            disabled={save.isPending || name === (user?.full_name || "")}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </Card>
    </div>
  );
}

// --- Password tab ------------------------------------------------------------
function SecurityTab() {
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const change = useMutation({
    mutationFn: () =>
      api.post("/auth/change-password", {
        current_password: form.current_password,
        new_password: form.new_password,
      }),
    onSuccess: () => {
      toast.success("Password changed. Other devices will be signed out.");
      setForm({ current_password: "", new_password: "", confirm: "" });
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const mismatch = form.confirm.length > 0 && form.new_password !== form.confirm;
  const canSubmit = form.current_password && form.new_password && !mismatch && !change.isPending;

  return (
    <div className="grid gap-6 lg:grid-cols-2 items-start">
      <Card className="p-6 space-y-4">
        <h2 className="text-sm font-semibold text-foreground">Change password</h2>
        <Input
          label="Current password"
          type="password"
          value={form.current_password}
          onChange={(e) => setForm({ ...form, current_password: e.target.value })}
        />
        <Input
          label="New password"
          type="password"
          value={form.new_password}
          onChange={(e) => setForm({ ...form, new_password: e.target.value })}
          hint="At least 8 characters, with a letter and a number. Cannot reuse a recent password."
        />
        <Input
          label="Confirm new password"
          type="password"
          value={form.confirm}
          onChange={(e) => setForm({ ...form, confirm: e.target.value })}
        />
        {mismatch && <p className="text-xs text-red-500">Passwords do not match.</p>}
        <Button variant="primary" disabled={!canSubmit} onClick={() => change.mutate()}>
          {change.isPending ? "Updating…" : "Update password"}
        </Button>
      </Card>

      <TwoFactorCard />
    </div>
  );
}

// --- Two-factor authentication ----------------------------------------------
// Groups a base32 secret into 4-char blocks for easier manual entry.
function groupSecret(s) {
  return (s || "").replace(/(.{4})/g, "$1 ").trim();
}

function RecoveryCodes({ codes, onClose }) {
  return (
    <div className="rounded-md border border-card-border bg-hover/40 p-4 space-y-3">
      <div className="flex items-start gap-2">
        <Icon icon="heroicons-outline:key" className="text-base text-amber-500 mt-0.5 shrink-0" />
        <div>
          <div className="text-sm font-medium text-foreground">Save your recovery codes</div>
          <p className="text-xs text-muted mt-0.5">
            Each code works once if you lose your authenticator. Store them somewhere safe — they
            won&apos;t be shown again.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-1.5 font-mono text-[13px] text-foreground">
        {codes.map((c) => (
          <div key={c} className="rounded bg-card border border-card-border px-2 py-1 text-center">
            {c}
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <Button
          variant="secondary"
          icon="heroicons-outline:clipboard-document"
          onClick={() => {
            navigator.clipboard?.writeText(codes.join("\n"));
            toast.success("Recovery codes copied");
          }}
        >
          Copy all
        </Button>
        <Button variant="ghost" onClick={onClose}>
          Done
        </Button>
      </div>
    </div>
  );
}

function TwoFactorCard() {
  const qc = useQueryClient();
  const { reload } = useAuth();
  const status = useQuery({
    queryKey: ["my-2fa"],
    queryFn: () => api.get("/auth/me/2fa").then((r) => r.data),
  });
  const enabled = status.data?.enabled;

  // Local flow state: 'idle' | 'enrolling' (secret shown, awaiting code) | codes shown.
  const [setup, setSetup] = useState(null); // { secret, otpauth_uri }
  const [code, setCode] = useState("");
  const [newCodes, setNewCodes] = useState(null);
  // For the enabled state: disabling / regenerating both need a current code.
  const [manageCode, setManageCode] = useState("");

  const begin = useMutation({
    mutationFn: () => api.post("/auth/me/2fa/setup").then((r) => r.data),
    onSuccess: (d) => {
      setSetup(d);
      setCode("");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const confirm = useMutation({
    mutationFn: () => api.post("/auth/me/2fa/confirm", { code: code.trim() }).then((r) => r.data),
    onSuccess: async (d) => {
      setSetup(null);
      setNewCodes(d.recovery_codes);
      await Promise.all([reload(), qc.invalidateQueries({ queryKey: ["my-2fa"] })]);
      toast.success("Two-factor authentication enabled");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const disable = useMutation({
    mutationFn: () => api.post("/auth/me/2fa/disable", { code: manageCode.trim() }),
    onSuccess: async () => {
      setManageCode("");
      await Promise.all([reload(), qc.invalidateQueries({ queryKey: ["my-2fa"] })]);
      toast.success("Two-factor authentication disabled");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const regen = useMutation({
    mutationFn: () =>
      api.post("/auth/me/2fa/recovery-codes", { code: manageCode.trim() }).then((r) => r.data),
    onSuccess: async (d) => {
      setManageCode("");
      setNewCodes(d.recovery_codes);
      await qc.invalidateQueries({ queryKey: ["my-2fa"] });
      toast.success("New recovery codes generated");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  return (
    <Card className="p-6 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
            Two-factor authentication
            <Badge color={enabled ? "green" : "neutral"}>{enabled ? "On" : "Off"}</Badge>
          </h2>
          <p className="text-xs text-muted mt-0.5">
            Require a time-based code from an authenticator app at sign-in.
          </p>
        </div>
        <Icon icon="heroicons-outline:shield-check" className={`text-2xl ${enabled ? "text-green-500" : "text-muted"}`} />
      </div>

      {/* Freshly generated recovery codes take over the card until dismissed. */}
      {newCodes ? (
        <RecoveryCodes codes={newCodes} onClose={() => setNewCodes(null)} />
      ) : status.isLoading ? (
        <div className="flex justify-center py-4">
          <Spinner />
        </div>
      ) : enabled ? (
        // --- enabled: regenerate codes / disable ---
        <div className="space-y-3">
          <p className="text-xs text-muted">
            {status.data?.recovery_codes_remaining ?? 0} recovery code(s) remaining. Enter a current
            authenticator or recovery code to make changes.
          </p>
          <Input
            label="Authentication code"
            value={manageCode}
            onChange={(e) => setManageCode(e.target.value)}
            placeholder="123456"
          />
          <div className="flex gap-2">
            <Button variant="secondary" disabled={!manageCode.trim() || regen.isPending} onClick={() => regen.mutate()}>
              {regen.isPending ? "Working…" : "Regenerate recovery codes"}
            </Button>
            <Button variant="danger" disabled={!manageCode.trim() || disable.isPending} onClick={() => disable.mutate()}>
              {disable.isPending ? "Working…" : "Disable 2FA"}
            </Button>
          </div>
        </div>
      ) : setup ? (
        // --- enrolling: show secret, ask for first code ---
        <div className="space-y-3">
          <p className="text-xs text-muted">
            In your authenticator app (Google Authenticator, Authy, 1Password…), add a new account
            and enter this setup key:
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 rounded-md border border-card-border bg-hover/40 px-3 py-2 font-mono text-sm tracking-wider text-foreground break-all">
              {groupSecret(setup.secret)}
            </code>
            <Button
              variant="ghost"
              icon="heroicons-outline:clipboard-document"
              onClick={() => {
                navigator.clipboard?.writeText(setup.secret);
                toast.success("Setup key copied");
              }}
            />
          </div>
          <Input
            label="Enter the 6-digit code to confirm"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="123456"
          />
          <div className="flex gap-2">
            <Button variant="primary" disabled={!code.trim() || confirm.isPending} onClick={() => confirm.mutate()}>
              {confirm.isPending ? "Verifying…" : "Verify & enable"}
            </Button>
            <Button variant="ghost" onClick={() => setSetup(null)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        // --- disabled: start enrolment ---
        <Button variant="primary" icon="heroicons-outline:shield-check" disabled={begin.isPending} onClick={() => begin.mutate()}>
          {begin.isPending ? "Preparing…" : "Enable two-factor authentication"}
        </Button>
      )}
    </Card>
  );
}

// --- Sessions tab ------------------------------------------------------------
function SessionsTab() {
  const qc = useQueryClient();
  const sessions = useQuery({
    queryKey: ["my-sessions"],
    queryFn: () => api.get("/auth/me/sessions").then((r) => r.data),
  });

  const revoke = useMutation({
    mutationFn: (id) => api.delete(`/auth/me/sessions/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-sessions"] });
      toast.success("Session revoked");
    },
    onError: (e) => toast.error(apiError(e)),
  });
  const revokeOthers = useMutation({
    mutationFn: () => api.post("/auth/me/sessions/revoke-others"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-sessions"] });
      toast.success("Signed out of other devices");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const items = sessions.data || [];
  const hasOthers = items.some((s) => !s.current);

  return (
    <Card className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Active sessions</h2>
          <p className="text-xs text-muted mt-0.5">Devices currently signed in to your account.</p>
        </div>
        {hasOthers && (
          <Button variant="secondary" disabled={revokeOthers.isPending} onClick={() => revokeOthers.mutate()}>
            {revokeOthers.isPending ? "Working…" : "Sign out others"}
          </Button>
        )}
      </div>

      {sessions.isLoading ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : (
        <ul className="divide-y divide-card-border">
          {items.map((s) => (
            <li key={s.id} className="flex items-center gap-3 py-3">
              <div className="h-9 w-9 rounded-full bg-hover flex items-center justify-center shrink-0">
                <Icon icon="heroicons-outline:computer-desktop" className="text-base text-muted" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium text-foreground flex items-center gap-2">
                  {deviceLabel(s.user_agent)}
                  {s.current && <Badge color="green">This device</Badge>}
                </div>
                <div className="text-xs text-muted truncate">
                  {s.ip || "unknown IP"} · active {fmt(s.last_used_at || s.created_at)}
                </div>
              </div>
              {!s.current && (
                <Button variant="ghost" icon="heroicons-outline:trash" disabled={revoke.isPending} onClick={() => revoke.mutate(s.id)}>
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// --- Preferences tab ---------------------------------------------------------
function PrefRow({ title, desc, children }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-card-border last:border-0">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">{title}</div>
        {desc && <div className="text-xs text-muted mt-0.5">{desc}</div>}
      </div>
      {children}
    </div>
  );
}

function PreferencesTab() {
  const { user, reload } = useAuth();
  const { theme, toggle } = useTheme();
  const prefs = user?.preferences || {};

  const save = useMutation({
    mutationFn: (patch) => api.patch("/auth/me/preferences", { preferences: patch }),
    onSuccess: async () => {
      await reload();
      toast.success("Preferences saved");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const notifyEmail = prefs.notify_email !== false; // default on
  const notifyInapp = prefs.notify_inapp !== false; // default on

  return (
    <div className="grid gap-6 lg:grid-cols-2 items-start">
      <Card className="p-6">
        <h2 className="text-sm font-semibold text-foreground mb-1">Appearance</h2>
        <PrefRow title="Theme" desc="Choose how the interface looks on this device.">
          <div className="flex items-center gap-1 rounded-md border border-card-border p-1">
            {["light", "dark"].map((t) => (
              <button
                key={t}
                onClick={() => {
                  if (theme !== t) toggle();
                  save.mutate({ theme: t });
                }}
                className={`px-3 py-1 rounded text-xs font-medium capitalize transition ${
                  theme === t ? "bg-hover text-foreground" : "text-muted hover:text-foreground"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </PrefRow>
      </Card>

      <Card className="p-6">
        <h2 className="text-sm font-semibold text-foreground mb-1">Notifications</h2>
        <PrefRow title="Email notifications" desc="Receive important alerts by email.">
          <Toggle checked={notifyEmail} onChange={(v) => save.mutate({ notify_email: v })} />
        </PrefRow>

        <PrefRow title="In-app notifications" desc="Show alerts in the notification center.">
          <Toggle checked={notifyInapp} onChange={(v) => save.mutate({ notify_inapp: v })} />
        </PrefRow>
      </Card>
    </div>
  );
}

export default function AccountPage() {
  const [tab, setTab] = useState("profile");

  return (
    <div>
      <PageHeader title="My account" subtitle="Manage your profile, security and preferences." />

      <div className="flex gap-1 border-b border-card-border mb-6">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-2 px-3 py-2.5 text-[13px] border-b-2 -mb-px transition ${
              tab === t.key
                ? "border-foreground text-foreground font-medium"
                : "border-transparent text-muted hover:text-foreground"
            }`}
          >
            <Icon icon={t.icon} className="text-base" />
            {t.label}
          </button>
        ))}
      </div>

      {tab === "profile" && <ProfileTab />}
      {tab === "security" && <SecurityTab />}
      {tab === "sessions" && <SessionsTab />}
      {tab === "preferences" && <PreferencesTab />}
    </div>
  );
}
