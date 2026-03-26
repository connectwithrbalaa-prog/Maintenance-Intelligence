# Deployment And Configuration

This document describes the frontend runtime assumptions and local deployment behavior for Oil & Gas Insights.

## Stack

- Vite 5
- React 18
- React Router 6
- Recharts for analytics visualizations

## Development Server

The Vite development server is configured in `vite.config.ts` with:

- Host: `::`
- Port: `8080`
- HMR overlay disabled

Start locally with:

```bash
npm install
npm run dev
```

## Production Build

Create a production build with:

```bash
npm run build
```

Preview the built app with:

```bash
npm run preview
```

## Backend Routing

During local development, Vite proxies `/backend/*` to:

- `http://72.62.231.202:8001`

The proxy rewrites `/backend/...` to `/...` before forwarding the request.

## Frontend API Resolution

The shared API module currently tries backend calls in this order:

1. `/backend`
2. `http://72.62.231.202:8001`

This gives the app two useful modes:

- Local proxy mode through Vite during development
- Direct HTTP fallback when the proxy is not available

## Headers And Dev Identity

The current frontend API client sends development-oriented headers, including:

- `x-dev-user: admin`
- `Content-Type: application/json`

If the backend requires additional auth, tenancy, or role headers in a target environment, the frontend API layer in `src/lib/api.ts` should be updated to use environment-specific values instead of hard-coded development defaults.

## Path Alias

Vite resolves the `@` alias to `./src`.

Examples:

- `@/lib/api`
- `@/components/...`

## Deployment Checklist

Before deploying a new build:

1. Confirm the backend base URL or proxy target is correct for the environment.
2. Confirm `/healthz`, portal, PM, and reporting endpoints are reachable.
3. Run `npm run build` and verify a successful production bundle.
4. Validate route navigation for `/runs`, `/pm-advisor`, `/outcomes`, and `/system-health`.
5. Confirm feedback and PM approval POST requests work with the environment's auth model.

## Known Build Note

The current production bundle builds successfully, but Vite reports a non-blocking warning that the main JavaScript chunk exceeds 500 kB after minification. If bundle size becomes a deployment concern, consider route-level code splitting or manual chunking.
