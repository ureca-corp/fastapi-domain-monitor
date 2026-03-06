## Frontend Workspace

This dashboard frontend is built with Vite, React, Tailwind CSS v4, and shadcn/ui.

### Development

```bash
bun dev
```

The Vite dev server runs with HMR on [http://localhost:3000](http://localhost:3000).

By default, API and WebSocket requests target `/domain-monitor` during development. If you are running the FastAPI app somewhere else, set one of these environment variables:

- `VITE_MONITOR_BACKEND_ORIGIN=http://127.0.0.1:8000`
  - Proxies `/domain-monitor/api` and `/domain-monitor/ws` through the Vite dev server.
- `VITE_MONITOR_BASE_URL=http://127.0.0.1:8000/domain-monitor`
  - Bypasses the proxy and talks to the backend directly.

### Build

```bash
bun run build
```

This produces a plain static bundle in `frontend/dist`.

### Sync Into The Python Package

```bash
bun run build:monitor
```

This copies the Vite output into `src/fastapi_domain_monitor/static/dashboard`, which is what the FastAPI plugin serves in packaged builds.
