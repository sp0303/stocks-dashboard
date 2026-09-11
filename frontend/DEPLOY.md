# Serving the built frontend

The app has real path routes (`/screener`, `/orb`), so the server must return
`index.html` for any path it does not have a file for. Otherwise a hard refresh on
`/orb` returns 404 — the route only works when navigated to from inside the app.

**Vite dev server** (`npm run dev`) already does this. Nothing to configure.

**nginx** — one line:

```nginx
location / {
    root /var/www/portfolio-dashboard/frontend/dist;
    try_files $uri $uri/ /index.html;
}
```

**Caddy**: `try_files {path} /index.html`

**Static hosts with no fallback setting** (GitHub Pages and similar) fall back to
`public/404.html`, which bounces to `/` while remembering the path.

Note that `vite.config.js` sets `base: '/'`. With the previous `base: './'`, assets
loaded from `/orb` would resolve to `/orb/assets/…` and fail. If the app is ever served
from a sub-path, set `base` to that sub-path rather than back to `'./'`.
