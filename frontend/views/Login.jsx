"use client";

// FRS-branded, security/AI-themed sign-in. Preserves the platform auth flow
// (email + password, 2FA challenge, first-run setup redirect) but replaces the
// generic card with a full-bleed "face recognition console" look.

import { Icon } from "@iconify/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, apiError } from "@/web/api";
import { useAuth } from "@/web/auth";

function StatusChip({ icon, label, value, tone = "cyan" }) {
  const dot = tone === "green" ? "bg-emerald-400" : "bg-cyan-400";
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
      <Icon icon={icon} className="text-cyan-300/80 text-base shrink-0" />
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-widest text-slate-400">{label}</div>
        <div className="text-xs font-medium text-slate-200 truncate">{value}</div>
      </div>
      <span className={`ml-auto h-1.5 w-1.5 rounded-full ${dot} shadow-[0_0_8px] shadow-current`} style={{ animation: "frsPulse 1.8s ease-in-out infinite" }} />
    </div>
  );
}

// The animated face-scan hero — bracket frame, face glyph, sweeping scan line.
function FaceScan() {
  return (
    <div className="relative mx-auto h-44 w-44">
      <div className="absolute inset-0 rounded-2xl bg-cyan-500/5 border border-cyan-400/20 overflow-hidden">
        {/* subtle grid */}
        <div className="absolute inset-0 opacity-[0.15]"
          style={{ backgroundImage: "linear-gradient(#22d3ee 1px,transparent 1px),linear-gradient(90deg,#22d3ee 1px,transparent 1px)", backgroundSize: "18px 18px" }} />
        <Icon icon="heroicons-solid:user" className="absolute inset-0 m-auto text-[104px] text-cyan-100/25" />
        {/* sweeping scan line */}
        <div className="absolute left-2 right-2 h-[2px] bg-gradient-to-r from-transparent via-cyan-300 to-transparent shadow-[0_0_12px_2px_rgba(34,211,238,0.6)]"
          style={{ animation: "frsScan 3.2s ease-in-out infinite" }} />
      </div>
      {/* corner brackets */}
      {[
        "top-0 left-0 border-t-2 border-l-2 rounded-tl-lg",
        "top-0 right-0 border-t-2 border-r-2 rounded-tr-lg",
        "bottom-0 left-0 border-b-2 border-l-2 rounded-bl-lg",
        "bottom-0 right-0 border-b-2 border-r-2 rounded-br-lg",
      ].map((c) => (
        <span key={c} className={`absolute h-6 w-6 border-cyan-300 ${c}`} />
      ))}
    </div>
  );
}

export default function FrsLogin() {
  const { login, loginMfa } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mfaToken, setMfaToken] = useState(null);
  const [code, setCode] = useState("");

  useEffect(() => {
    api.get("/auth/setup-status").then((r) => { if (r.data?.needs_setup) router.replace("/setup"); }).catch(() => {});
  }, [router]);

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await login(email, password);
      if (res?.mfaRequired) { setMfaToken(res.mfaToken); setCode(""); return; }
      toast.success("Access granted");
      router.push("/");
    } catch (err) { toast.error(apiError(err, "Authentication failed")); }
    finally { setBusy(false); }
  }

  async function onSubmitCode(e) {
    e.preventDefault();
    setBusy(true);
    try { await loginMfa(mfaToken, code.trim()); toast.success("Access granted"); router.push("/"); }
    catch (err) { toast.error(apiError(err, "Invalid code")); }
    finally { setBusy(false); }
  }

  const fieldCls = "w-full rounded-lg border border-white/10 bg-white/[0.04] pl-11 pr-3 py-3 text-sm text-slate-100 placeholder:text-slate-500 outline-none transition focus:border-cyan-400/60 focus:bg-white/[0.06]";

  return (
    <div className="fixed inset-0 overflow-auto bg-black text-slate-200">
      <style>{`
        @keyframes frsScan { 0%{top:6%} 50%{top:90%} 100%{top:6%} }
        @keyframes frsPulse { 0%,100%{opacity:1} 50%{opacity:.35} }
        @keyframes frsFloat { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)} }
      `}</style>

      {/* background layers: deep gradient + circuit lines + accent glows */}
      <div className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(1000px 520px at 18% 12%, rgba(34,211,238,0.08), transparent 62%), radial-gradient(800px 460px at 88% 92%, rgba(34,211,238,0.05), transparent 62%)" }} />
      <div className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{ backgroundImage: "linear-gradient(#5eead4 1px,transparent 1px),linear-gradient(90deg,#5eead4 1px,transparent 1px)", backgroundSize: "44px 44px" }} />

      <div className="relative min-h-full flex items-center justify-center p-4 sm:p-8">
        <div className="w-full max-w-5xl grid lg:grid-cols-2 rounded-2xl overflow-hidden border border-cyan-500/15 bg-white/[0.02] backdrop-blur-xl shadow-[0_30px_120px_-20px_rgba(8,145,178,0.35)]">

          {/* ── LEFT: brand + face-scan console ── */}
          <div className="relative hidden lg:flex flex-col justify-between gap-8 p-10 bg-gradient-to-br from-[#0c0c0e] via-[#080808] to-black border-r border-cyan-500/10">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/30">
                <Icon icon="heroicons-solid:viewfinder-circle" className="text-white text-2xl" />
              </div>
              <div>
                <div className="text-lg font-semibold tracking-tight text-white leading-none">Neubit</div>
                <div className="text-[11px] uppercase tracking-[0.2em] text-cyan-300/70 mt-1">Face Recognition</div>
              </div>
            </div>

            <div className="text-center" style={{ animation: "frsFloat 6s ease-in-out infinite" }}>
              <FaceScan />
              <div className="mt-5 inline-flex items-center gap-2 rounded-full border border-cyan-400/25 bg-cyan-400/10 px-3 py-1 text-[11px] uppercase tracking-widest text-cyan-200">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" style={{ animation: "frsPulse 1.4s ease-in-out infinite" }} />
                Biometric console armed
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <StatusChip icon="heroicons-outline:cpu-chip" label="AI Engine" value="Online · Realtime" tone="green" />
              <StatusChip icon="heroicons-outline:user-group" label="Recognition" value="Neural matching" />
              <StatusChip icon="heroicons-outline:finger-print" label="Liveness" value="Spoof-protected" />
              <StatusChip icon="heroicons-outline:shield-check" label="Session" value="Encrypted" tone="green" />
            </div>
          </div>

          {/* ── RIGHT: sign-in ── */}
          <div className="p-8 sm:p-11 flex flex-col justify-center">
            {/* mobile brand */}
            <div className="lg:hidden flex items-center gap-3 mb-8">
              <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center">
                <Icon icon="heroicons-solid:viewfinder-circle" className="text-white text-xl" />
              </div>
              <div className="text-base font-semibold text-white">Neubit <span className="text-cyan-300/70 font-normal">FRS</span></div>
            </div>

            {mfaToken ? (
              <form onSubmit={onSubmitCode} className="space-y-5">
                <div>
                  <div className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/10 border border-cyan-400/30 mb-4">
                    <Icon icon="heroicons-outline:shield-check" className="text-cyan-300 text-2xl" />
                  </div>
                  <h1 className="text-xl font-semibold tracking-tight text-white">Two-factor verification</h1>
                  <p className="text-sm text-slate-400 mt-1">Enter the 6-digit code from your authenticator, or a recovery code.</p>
                </div>
                <div className="relative">
                  <Icon icon="heroicons-outline:key" className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input value={code} onChange={(e) => setCode(e.target.value)} autoFocus inputMode="numeric" placeholder="Authentication code" className={`${fieldCls} tracking-[0.3em]`} />
                </div>
                <button type="submit" disabled={busy || !code.trim()} className="w-full rounded-lg bg-gradient-to-r from-cyan-400 to-blue-600 py-3 text-sm font-semibold text-white shadow-lg shadow-cyan-500/25 transition hover:brightness-110 disabled:opacity-50 disabled:pointer-events-none">
                  {busy ? "Verifying…" : "Verify & sign in"}
                </button>
                <button type="button" onClick={() => setMfaToken(null)} className="w-full text-center text-xs text-slate-400 hover:text-slate-200">← Back to sign in</button>
              </form>
            ) : (
              <form onSubmit={onSubmit} className="space-y-5">
                <div>
                  <div className="text-[11px] uppercase tracking-[0.25em] text-cyan-300/70 mb-1.5">Secure sign-in</div>
                  <h1 className="text-2xl font-semibold tracking-tight text-white">Log in</h1>
                  <p className="text-sm text-slate-400 mt-1">Access the face-recognition console.</p>
                </div>
                <div className="relative">
                  <Icon icon="heroicons-outline:user" className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus autoComplete="username" placeholder="Email address" className={fieldCls} />
                </div>
                <div className="relative">
                  <Icon icon="heroicons-outline:lock-closed" className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" placeholder="Password" className={`${fieldCls} pr-11`} />
                  <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                    <Icon icon={show ? "heroicons-outline:eye-slash" : "heroicons-outline:eye"} />
                  </button>
                </div>
                <div className="flex justify-end">
                  <Link href="/forgot-password" className="text-xs text-cyan-300/80 hover:text-cyan-200">Forgot password?</Link>
                </div>
                <button type="submit" disabled={busy || !email || !password} className="group w-full rounded-lg bg-gradient-to-r from-cyan-400 to-blue-600 py-3 text-sm font-semibold text-white shadow-lg shadow-cyan-500/25 transition hover:brightness-110 disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center gap-2">
                  <Icon icon="heroicons-outline:finger-print" className="text-base" />
                  {busy ? "Authenticating…" : "Log in"}
                </button>
              </form>
            )}

            <div className="mt-8 flex items-center justify-between text-[11px] text-slate-500">
              <span>© {new Date().getFullYear()} Neubit · Face Recognition</span>
              <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" style={{ animation: "frsPulse 1.6s ease-in-out infinite" }} /> System secure</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
