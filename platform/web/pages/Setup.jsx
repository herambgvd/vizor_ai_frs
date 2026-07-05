"use client";

import { Icon } from "@iconify/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, apiError, tokens } from "@/web/api";
import { useAuth } from "@/web/auth";

// First-run wizard: creates the very first administrator, then signs them in.
// Only reachable while the deployment has zero users (backend enforces this too).
export default function SetupPage() {
  const router = useRouter();
  const { reload } = useAuth();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", confirm: "" });
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);

  // If setup is already done, don't show the wizard.
  useEffect(() => {
    api
      .get("/auth/setup-status")
      .then((r) => {
        if (!r.data?.needs_setup) router.replace("/login");
        else setChecking(false);
      })
      .catch(() => setChecking(false));
  }, [router]);

  const mismatch = form.confirm.length > 0 && form.password !== form.confirm;
  const canSubmit = form.email && form.password && !mismatch && !busy;

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/auth/setup", {
        email: form.email,
        password: form.password,
        full_name: form.full_name || null,
      });
      tokens.set(data.access_token, data.refresh_token);
      await reload();
      toast.success("Welcome — your workspace is ready");
      router.replace("/");
    } catch (err) {
      toast.error(apiError(err, "Setup failed"));
    } finally {
      setBusy(false);
    }
  }

  if (checking) return null;

  const field =
    "w-full rounded-md border border-card-border bg-transparent px-3 py-2.5 text-sm text-foreground placeholder:text-muted outline-none transition focus:border-muted";

  return (
    <div className="w-full max-w-md rounded-xl bg-card border border-card-border p-8">
      <div className="mb-7 text-center">
        <div className="mx-auto mb-4 h-11 w-11 rounded-lg bg-white flex items-center justify-center text-black text-lg font-bold">
          N
        </div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Welcome — let's get set up</h1>
        <p className="text-sm text-muted mt-1">Create the first administrator account.</p>
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-muted mb-1.5">Full name</label>
          <input
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            className={field}
            placeholder="Jane Doe"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-muted mb-1.5">Email</label>
          <input
            type="email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            className={field}
            placeholder="admin@example.com"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-muted mb-1.5">Password</label>
          <div className="relative">
            <input
              type={show ? "text" : "password"}
              required
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className={`${field} pr-10`}
              placeholder="At least 8 chars, a letter and a number"
            />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              className="absolute inset-y-0 right-0 flex items-center px-3 text-muted hover:text-foreground transition"
              aria-label={show ? "Hide password" : "Show password"}
            >
              <Icon icon={show ? "heroicons-outline:eye-slash" : "heroicons-outline:eye"} className="text-lg" />
            </button>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-muted mb-1.5">Confirm password</label>
          <input
            type="password"
            required
            value={form.confirm}
            onChange={(e) => setForm({ ...form, confirm: e.target.value })}
            className={field}
            placeholder="Re-enter password"
          />
          {mismatch && <p className="text-xs text-red-500 mt-1">Passwords do not match.</p>}
        </div>
        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-md bg-foreground text-background hover:opacity-90 disabled:opacity-50 font-medium py-2.5 text-sm transition"
        >
          {busy ? "Creating…" : "Create admin & continue"}
        </button>
      </form>
    </div>
  );
}
