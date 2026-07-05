# @web — shared edge-UI (frontend boilerplate)

The frontend counterpart of `boilerplate/edge`. Every scenario's frontend reuses
this — auth, theme, UI kit, shell/nav, and all the platform admin pages — so we
build the edge UI **once**, not per scenario.

## How a scenario consumes it (like `pip install -e /edge`, but for the UI)

The scenario's frontend **bind-mounts** this folder into its app tree at `/app/web`
(see `frs/backend/docker-compose.yml` → frontend service). Because the app's
`jsconfig.json` maps `@/* → ./*`, everything here is importable as `@/web/...`.

```yaml
# docker-compose (frontend service)
volumes:
  - ../frontend:/app
  - ../../boilerplate/web:/app/web   # <- shared edge-ui
  - /app/node_modules
```

The scenario also:
- adds `"./web/**/*.{js,jsx}"` to `tailwind.config.js` `content`
- gitignores `web/` (it's a mount, not source)
- imports the shared font + `@/web/theme.css` + `@/web/Providers` in `app/layout.js`

## What's here

- `kit.jsx` — UI primitives (Card, Button, Input, Select, Modal, Table, Badge, …)
- `api.js`, `auth.js`, `theme.jsx` — API client, auth context, theme toggle
- `theme.css` — light/dark tokens
- `menu.js` — base nav (scenarios extend it with their own items)
- `Providers.jsx`, `shell/` (Header, AppLayout, AuthLayout), `SystemResources.jsx`
- `pages/` — the platform admin **page components** (Dashboard, Users, Roles,
  ApiKeys, Branding, Channels, EmailTemplates, License, Audit, Notifications,
  Login, ForgotPassword, NotFound, ErrorView, Loading)

## Thin route wiring in a scenario

Next.js App Router is file-based, so each route is a 1-line re-export:

```js
// app/(app)/users/page.jsx
export { default } from "@/web/pages/Users";
```

Scenario-specific screens (e.g. FRS cameras/POIs/live-wall) live in the scenario's
own `app/` + `components/`, and import shared bits via `@/web/kit`, `@/web/api`, etc.
