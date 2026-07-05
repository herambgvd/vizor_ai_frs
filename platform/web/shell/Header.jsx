"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, apiError } from "@/web/api";
import { Avatar } from "@/web/kit";
import { menuItems } from "@/menu";
import { useAuth } from "@/web/auth";
import { useTheme } from "@/web/theme";

// Resolves the header brand from white-label branding:
//   custom logo uploaded  -> show the logo image (no mark, no wordmark)
//   name_in_header on     -> "N" mark + app name
//   otherwise (default)   -> "N" mark + "Neubit"
function Brand() {
  const { data } = useQuery({
    queryKey: ["branding"],
    queryFn: () => api.get("/branding").then((r) => r.data),
    staleTime: 60_000,
  });

  const logo = data?.logo_url;
  const name = data?.name_in_header && data?.app_name ? data.app_name : "Neubit";

  return (
    <Link href="/" className="flex items-center gap-2.5">
      {logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={logo} alt={data?.app_name || "Logo"} className="h-6 max-w-[150px] object-contain" />
      ) : (
        <>
          <div className="h-6 w-6 rounded-md bg-white flex items-center justify-center text-black font-bold text-xs">
            N
          </div>
          <span className="font-semibold text-foreground tracking-tight text-[15px]">{name}</span>
        </>
      )}
    </Link>
  );
}

function fmtTs(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
  return d.toLocaleDateString();
}

// Header notifications bell: unread badge + click-to-open dropdown of recent
// notifications (mark one / mark all read) with a "View all" link to the page.
function NotificationsBell() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const { data } = useQuery({
    queryKey: ["notifications-bell"],
    queryFn: () => api.get("/messaging/notifications", { params: { page_size: 8 } }).then((r) => r.data),
    refetchInterval: 30000,
  });
  const items = data?.items || [];
  const unread = items.filter((n) => !n.read);

  useEffect(() => {
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["notifications-bell"] });
  const markRead = useMutation({ mutationFn: (id) => api.post(`/messaging/notifications/${id}/read`), onSuccess: invalidate });
  const markAll = useMutation({ mutationFn: () => Promise.all(unread.map((n) => api.post(`/messaging/notifications/${n.id}/read`))), onSuccess: invalidate });

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={`relative p-2 rounded-md transition ${open ? "text-foreground bg-hover" : "text-muted hover:text-foreground hover:bg-hover"}`}
        aria-label="Notifications"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Icon icon="heroicons-outline:bell" className="text-lg" />
        {unread.length > 0 && (
          <span className="absolute top-0.5 right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-semibold flex items-center justify-center">
            {unread.length > 9 ? "9+" : unread.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 rounded-lg border border-card-border bg-card shadow-2xl z-30 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-card-border">
            <span className="text-sm font-semibold text-foreground">Notifications{unread.length > 0 ? ` · ${unread.length}` : ""}</span>
            {unread.length > 0 && (
              <button onClick={() => markAll.mutate()} disabled={markAll.isPending} className="text-xs text-blue-400 hover:underline disabled:opacity-50">Mark all read</button>
            )}
          </div>
          {items.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-muted">
              <Icon icon="heroicons-outline:bell-slash" className="text-2xl mx-auto mb-2" />No notifications
            </div>
          ) : (
            <ul className="max-h-96 overflow-y-auto divide-y divide-card-border">
              {items.map((n) => (
                <li key={n.id}>
                  <button
                    onClick={() => { if (!n.read) markRead.mutate(n.id); }}
                    className={`w-full text-left px-4 py-3 hover:bg-hover transition ${n.read ? "" : "bg-hover/40"}`}
                  >
                    <div className="flex items-start gap-2">
                      {n.read ? <span className="w-2 shrink-0" /> : <span className="mt-1.5 h-2 w-2 rounded-full bg-blue-500 shrink-0" />}
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-foreground truncate">{n.title}</div>
                        {n.body && <div className="text-xs text-muted mt-0.5 line-clamp-2">{n.body}</div>}
                        <div className="text-[11px] text-muted mt-1">{fmtTs(n.ts)}</div>
                      </div>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Link href="/notifications" onClick={() => setOpen(false)} className="block px-4 py-2.5 text-center text-sm text-blue-400 hover:bg-hover border-t border-card-border">
            View all
          </Link>
        </div>
      )}
    </div>
  );
}

// A top-level nav entry: a plain link, or a dropdown when it has children.
function NavEntry({ item, pathname, can }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  // Close the dropdown on navigation.
  useEffect(() => setOpen(false), [pathname]);

  const linkClass = (active) =>
    `flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2.5 text-[13px] transition ${
      active ? "border-foreground text-foreground font-medium" : "border-transparent text-muted hover:text-foreground"
    }`;

  if (!item.children) {
    return (
      <Link href={item.link} className={linkClass(pathname === item.link)}>
        <Icon icon={item.icon} className="text-base shrink-0" />
        {item.title}
      </Link>
    );
  }

  const children = item.children.filter((c) => !c.perm || can(c.perm));
  if (!children.length) return null;
  const active = children.some((c) => pathname === c.link);

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} className={linkClass(active)}>
        <Icon icon={item.icon} className="text-base shrink-0" />
        {item.title}
        <Icon icon="heroicons-outline:chevron-down" className={`text-xs transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute left-0 mt-1 w-56 rounded-lg border border-card-border bg-card shadow-2xl py-1 z-30">
          {children.map((c) => (
            <Link
              key={c.link}
              href={c.link}
              className={`flex items-center gap-2.5 px-3 py-2 text-[13px] transition ${
                pathname === c.link
                  ? "bg-hover text-foreground font-medium"
                  : "text-muted hover:text-foreground hover:bg-hover"
              }`}
            >
              <Icon icon={c.icon} className="text-base shrink-0" />
              {c.title}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Header() {
  const { user, logout, can, reload } = useAuth();
  const { theme, toggle } = useTheme();
  const router = useRouter();
  const pathname = usePathname();
  const [openUser, setOpenUser] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);
  const userRef = useRef(null);

  // Close the account menu on an outside click or Escape.
  useEffect(() => {
    if (!openUser) return;
    function onDoc(e) {
      if (userRef.current && !userRef.current.contains(e.target)) setOpenUser(false);
    }
    function onKey(e) {
      if (e.key === "Escape") setOpenUser(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [openUser]);

  // Close it on navigation.
  useEffect(() => setOpenUser(false), [pathname]);

  const items = menuItems.filter((m) => (m.link && !m.perm) || (m.perm && can(m.perm)) || m.children);
  const displayName = user?.full_name || user?.email;

  async function onPickAvatar(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file later
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
    <header className="sticky top-0 z-20 border-b border-card-border bg-background/70 backdrop-blur">
      <div className="w-full px-6 lg:px-8">
        {/* Row 1 — brand + account */}
        <div className="h-14 flex items-center justify-between">
          <Brand />

          <div className="flex items-center gap-1">
            <button
              onClick={() => window.dispatchEvent(new Event("palette:open"))}
              className="hidden sm:flex items-center gap-2 rounded-md border border-card-border text-muted hover:text-foreground hover:bg-hover transition px-2.5 py-1.5 mr-1"
              aria-label="Search"
            >
              <Icon icon="heroicons-outline:magnifying-glass" className="text-base" />
              <span className="text-xs">Search</span>
              <kbd className="text-[10px] border border-card-border rounded px-1 py-0.5">⌘K</kbd>
            </button>
            <button
              onClick={toggle}
              className="p-2 rounded-md text-muted hover:text-foreground hover:bg-hover transition"
              aria-label="Toggle theme"
            >
              <Icon icon={theme === "dark" ? "heroicons-outline:sun" : "heroicons-outline:moon"} className="text-lg" />
            </button>
            <NotificationsBell />
            <div className="relative" ref={userRef}>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={onPickAvatar}
              />
              <button
                onClick={() => setOpenUser((o) => !o)}
                className="flex items-center gap-2.5 pl-2 pr-1"
                aria-haspopup="menu"
                aria-expanded={openUser}
              >
                <Avatar src={user?.avatar_url} name={displayName} size={28} />
                <div className="text-left hidden sm:block leading-tight">
                  <div className="text-[13px] font-medium text-foreground">{displayName}</div>
                  <div className="text-[11px] text-muted">{user?.role?.name}</div>
                </div>
                <Icon
                  icon="heroicons-outline:chevron-down"
                  className={`text-sm text-muted shrink-0 transition ${openUser ? "rotate-180" : ""}`}
                />
              </button>
              {openUser && (
                <div className="absolute right-0 mt-2 w-56 rounded-lg border border-card-border bg-card shadow-2xl py-1 z-30">
                  <div className="flex items-center gap-3 px-4 py-3 border-b border-card-border">
                    <Avatar src={user?.avatar_url} name={displayName} size={36} />
                    <div className="min-w-0">
                      <div className="text-[13px] font-medium text-foreground truncate">{displayName}</div>
                      <div className="text-[11px] text-muted truncate">{user?.email}</div>
                    </div>
                  </div>
                  <Link
                    href="/account"
                    onClick={() => setOpenUser(false)}
                    className="w-full flex items-center gap-2.5 px-4 py-2 text-[13px] text-muted hover:text-foreground hover:bg-hover transition"
                  >
                    <Icon icon="heroicons-outline:user-circle" className="text-base shrink-0" />
                    Account
                  </Link>
                  <button
                    disabled={uploading}
                    onClick={() => fileRef.current?.click()}
                    className="w-full flex items-center gap-2.5 px-4 py-2 text-[13px] text-muted hover:text-foreground hover:bg-hover transition disabled:opacity-50"
                  >
                    <Icon icon="heroicons-outline:camera" className="text-base shrink-0" />
                    {uploading ? "Uploading…" : user?.avatar_url ? "Change photo" : "Add photo"}
                  </button>
                  {user?.avatar_url && (
                    <button
                      disabled={uploading}
                      onClick={removeAvatar}
                      className="w-full flex items-center gap-2.5 px-4 py-2 text-[13px] text-muted hover:text-foreground hover:bg-hover transition disabled:opacity-50"
                    >
                      <Icon icon="heroicons-outline:trash" className="text-base shrink-0" />
                      Remove photo
                    </button>
                  )}
                  <div className="my-1 border-t border-card-border" />
                  <button
                    onClick={async () => {
                      await logout();
                      router.replace("/login");
                    }}
                    className="w-full flex items-center gap-2.5 px-4 py-2 text-[13px] text-red-500 hover:bg-hover transition"
                  >
                    <Icon icon="heroicons-outline:arrow-right-on-rectangle" className="text-base shrink-0" />
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Row 2 — top-level nav. No overflow clipping here, or it would hide the
            Settings dropdown that extends below the bar. */}
        <nav className="flex items-center gap-1 -mb-px">
          {items.map((m) => (
            <NavEntry key={m.title} item={m} pathname={pathname} can={can} />
          ))}
        </nav>
      </div>
    </header>
  );
}
