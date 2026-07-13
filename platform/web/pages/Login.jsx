"use client";

import { Icon } from "@iconify/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, apiError } from "@/web/api";
import { useAuth } from "@/web/auth";

export default function LoginPage() {
  const { login, loginMfa } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  // 2FA challenge state: once the first factor passes for a 2FA user we hold the
  // short-lived mfaToken and swap the form to ask for the authenticator code.
  const [mfaToken, setMfaToken] = useState(null);
  const [code, setCode] = useState("");

  // First run (no users yet) → send the admin to the setup wizard.
  useEffect(() => {
    api
      .get("/auth/setup-status")
      .then((r) => {
        if (r.data?.needs_setup) router.replace("/setup");
      })
      .catch(() => {});
  }, [router]);

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await login(email, password);
      if (res?.mfaRequired) {
        setMfaToken(res.mfaToken);
        setCode("");
        return; // stay on the page, now showing the code step
      }
      toast.success("Welcome back");
      router.push("/");
    } catch (err) {
      toast.error(apiError(err, "Login failed"));
    } finally {
      setBusy(false);
    }
  }

  async function onSubmitCode(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await loginMfa(mfaToken, code.trim());
      toast.success("Welcome back");
      router.push("/");
    } catch (err) {
      toast.error(apiError(err, "Invalid code"));
    } finally {
      setBusy(false);
    }
  }

  if (mfaToken) {
    return (
      <div className="w-full max-w-sm rounded-xl bg-card border border-card-border p-8">
        <div className="mb-7 text-center">
          <div className="mx-auto mb-4 h-11 w-11 rounded-lg bg-white flex items-center justify-center text-black text-lg font-bold">
            <Icon icon="heroicons-outline:shield-check" className="text-2xl" />
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Two-factor authentication</h1>
          <p className="text-sm text-muted mt-1">Enter the 6-digit code from your authenticator app, or a recovery code.</p>
        </div>
        <form onSubmit={onSubmitCode} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-muted mb-1.5">Authentication code</label>
            <input
              type="text"
              inputMode="text"
              autoComplete="one-time-code"
              autoFocus
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full rounded-md border border-card-border bg-transparent px-3 py-2.5 text-sm text-foreground placeholder:text-muted outline-none transition focus:border-muted tracking-widest text-center"
              placeholder="123456"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-foreground text-background hover:opacity-90 disabled:opacity-50 font-medium py-2.5 text-sm transition"
          >
            {busy ? "Verifying…" : "Verify"}
          </button>
          <button
            type="button"
            onClick={() => { setMfaToken(null); setCode(""); }}
            className="w-full text-xs text-muted hover:text-foreground transition"
          >
            Back to sign in
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm rounded-xl bg-card border border-card-border p-8">
      <div className="mb-7 text-center">
        <div className="mx-auto mb-4 h-11 w-11 rounded-lg bg-white flex items-center justify-center text-black text-lg font-bold">
          N
        </div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Sign in to wonin.ai</h1>
        <p className="text-sm text-muted mt-1">Face recognition platform</p>
      </div>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-muted mb-1.5">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-card-border bg-transparent px-3 py-2.5 text-sm text-foreground placeholder:text-muted outline-none transition focus:border-muted"
            placeholder="you@example.com"
          />
        </div>
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="block text-sm font-medium text-muted">Password</label>
            <Link href="/forgot-password" className="text-xs text-muted hover:text-foreground transition">
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <input
              type={show ? "text" : "password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-card-border bg-transparent px-3 py-2.5 pr-10 text-sm text-foreground placeholder:text-muted outline-none transition focus:border-muted"
              placeholder="••••••••"
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
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-foreground text-background hover:opacity-90 disabled:opacity-50 font-medium py-2.5 text-sm transition"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
