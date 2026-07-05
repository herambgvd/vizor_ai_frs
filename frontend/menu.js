// Edge-UI top navigation. Three top-level entries; Settings groups the admin
// sub-pages into a dropdown. Notifications live in the header bell, and System
// resources are shown on the Dashboard — so neither needs a menu entry.
// Items/children with a `perm` are only shown when the user's role grants it.
export const menuItems = [
  // Dedicated FRS portal — its modules are the primary navigation (flat,
  // perm-gated), alongside Dashboard and Audit.
  { title: "Dashboard", icon: "heroicons-outline:home", link: "/" },
  { title: "Cameras", icon: "heroicons-outline:video-camera", link: "/cameras", perm: "frs.camera.read" },
  { title: "Live", icon: "heroicons-outline:signal", link: "/live", perm: "frs.event.read" },
  { title: "Events", icon: "heroicons-outline:bolt", link: "/events", perm: "frs.event.read" },
  { title: "Investigate", icon: "heroicons-outline:magnifying-glass", link: "/investigate", perm: "frs.event.read" },
  { title: "Transit", icon: "heroicons-outline:arrows-right-left", link: "/transit", perm: "frs.transit.read" },
  { title: "Tour", icon: "heroicons-outline:map", link: "/tour", perm: "frs.event.read" },
  { title: "Groups", icon: "heroicons-outline:user-group", link: "/groups", perm: "frs.group.read" },
  { title: "POI", icon: "heroicons-outline:users", link: "/persons", perm: "frs.person.read" },
  { title: "Reports", icon: "heroicons-outline:document-chart-bar", link: "/reports", perm: "frs.event.read" },
  { title: "Audit", icon: "heroicons-outline:clipboard-document-list", link: "/audit", perm: "audit.read" },
  {
    title: "Settings",
    icon: "heroicons-outline:cog-6-tooth",
    children: [
      { title: "Recognition Settings", icon: "heroicons-outline:face-smile", link: "/frs-settings", perm: "frs.settings.manage" },
      { title: "Users", icon: "heroicons-outline:users", link: "/users", perm: "user.read" },
      { title: "Roles & Permissions", icon: "heroicons-outline:shield-check", link: "/roles", perm: "role.read" },
      { title: "API Keys", icon: "heroicons-outline:key", link: "/api-keys", perm: "apikey.manage" },
      { title: "Branding", icon: "heroicons-outline:swatch", link: "/branding", perm: "branding.manage" },
      { title: "Channels", icon: "heroicons-outline:bell-alert", link: "/channels", perm: "settings.manage" },
      { title: "Email Templates", icon: "heroicons-outline:envelope", link: "/email-templates", perm: "settings.manage" },
      { title: "General", icon: "heroicons-outline:adjustments-horizontal", link: "/general", perm: "settings.manage" },
      { title: "System Health", icon: "heroicons-outline:heart", link: "/system-health", perm: "system.read" },
      { title: "License", icon: "heroicons-outline:check-badge", link: "/license" },
    ],
  },
];
