"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, apiError } from "@/web/api";

// Two-step reset: (1) request a token by email, (2) enter the token + new password.
// An invite/reset email links here with ?token=... so we jump straight to step 2.
export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState("request"); // "request" | "reset"
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  // If the user arrived from an emailed link (?token=...), prefill + skip to step 2.
  // Read from window.location directly to avoid the useSearchParams Suspense rule.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const t = new URLSearchParams(window.location.search).get("token");
    if (t) {
      setToken(t);
      setStep("reset");
    }
  }, []);

  async function requestReset(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/auth/forgot-password", { email });
      toast.success("If that account exists, a reset token was emailed");
      setStep("reset");
    } catch (err) {
      toast.error(apiError(err, "Could not request reset"));
    } finally {
      setBusy(false);
    }
  }

  async function doReset(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: password });
      toast.success("Password updated — sign in");
      router.push("/login");
    } catch (err) {
      toast.error(apiError(err, "Reset failed"));
    } finally {
      setBusy(false);
    }
  }

  const field =
    "w-full rounded-md border border-card-border bg-transparent px-3 py-2.5 text-sm text-foreground placeholder:text-muted outline-none transition focus:border-muted";

  return (
    <div className="w-full max-w-sm rounded-xl bg-card border border-card-border p-8">
      <div className="mb-7 text-center">
        <div className="mx-auto mb-4 h-11 w-11 rounded-lg bg-white flex items-center justify-center text-black text-lg font-bold">
          N
        </div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Reset your password</h1>
        <p className="text-sm text-muted mt-1">
          {step === "request" ? "We'll email you a reset token." : "Enter the token from your email."}
        </p>
      </div>

      {step === "request" ? (
        <form onSubmit={requestReset} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-muted mb-1.5">Email</label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={field} placeholder="you@example.com" />
          </div>
          <button type="submit" disabled={busy} className="w-full rounded-md bg-foreground text-background hover:opacity-90 disabled:opacity-50 font-medium py-2.5 text-sm transition">
            {busy ? "Sending…" : "Send reset token"}
          </button>
        </form>
      ) : (
        <form onSubmit={doReset} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-muted mb-1.5">Reset token</label>
            <input required value={token} onChange={(e) => setToken(e.target.value)} className={field} placeholder="paste token from email" />
          </div>
          <div>
            <label className="block text-sm font-medium text-muted mb-1.5">New password</label>
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className={field} placeholder="••••••••" />
          </div>
          <button type="submit" disabled={busy} className="w-full rounded-md bg-foreground text-background hover:opacity-90 disabled:opacity-50 font-medium py-2.5 text-sm transition">
            {busy ? "Updating…" : "Set new password"}
          </button>
          <button type="button" onClick={() => setStep("request")} className="w-full text-xs text-muted hover:text-foreground transition">
            Didn't get it? Request again
          </button>
        </form>
      )}

      <div className="mt-6 text-center">
        <Link href="/login" className="text-xs text-muted hover:text-foreground transition">
          ← Back to sign in
        </Link>
      </div>
    </div>
  );
}
