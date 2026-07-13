"use client";

import AppLayout from "@/web/shell/AppLayout";
import NotificationWatcher from "@/views/NotificationWatcher";

export default function AppShell({ children }) {
  return (
    <>
      <NotificationWatcher />
      <AppLayout>{children}</AppLayout>
    </>
  );
}
