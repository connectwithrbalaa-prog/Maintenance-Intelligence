# Auth Trust Model

This document explains how Maintenance Intelligence resolves identity, enforces
tenant scope, and separates local development behaviour from production auth.

---

## Identity resolution order

The API middleware resolves the acting identity from three sources, in priority order:

| Priority | Source | When active |
|---|---|---|
| 1 | **JWT Bearer token** | `MI_AUTH_JWT_JWKS_URL` is set and `Authorization: Bearer <token>` header is present |
| 2 | **Trusted proxy headers** | `MI_AUTH_TRUST_FORWARDED_HEADERS=true` (e.g. Oauth2-Proxy, Istio OIDC) |
| 3 | **Dev headers** | `MI_DEV_ALLOW_HEADERS=true` (local development only, never set in production) |

If none of the sources resolves an identity, the request is **anonymous**.
Anonymous requests to all protected endpoints receive `HTTP 403`.

---

## Auth sources in detail

### 1. JWT Bearer (production)

Configure with:

```
MI_AUTH_JWT_JWKS_URL=https://your-idp/.well-known/jwks.json
MI_AUTH_JWT_AUDIENCE=maintenance-intelligence-api   # optional
MI_AUTH_JWT_ISSUER=https://your-idp/                # optional
MI_AUTH_JWT_ALGORITHMS=RS256                        # comma-separated; default RS256
MI_AUTH_JWT_LEEWAY_S=30                             # clock-skew tolerance in seconds
```

Claim mapping (customisable via env):

| Env var | JWT claim | Purpose |
|---|---|---|
| `MI_AUTH_JWT_ORG_CLAIM` | `org_id` | Tenant / organisation ID |
| `MI_AUTH_JWT_ROLES_CLAIM` | `roles` | Role list (also accepts scalar `role`) |
| `MI_AUTH_JWT_SITES_CLAIM` | `site_ids` | Permitted site identifiers |

Standard claims `sub`, `org_id` (or `org`/`tenant_id`), `roles`, `site_ids`, and
`site_id` are extracted automatically.  An invalid or expired token is treated as
anonymous — no `401` is returned so as not to leak the configured source.

JWKS keys are cached per-URL by `PyJWKClient` (5-minute lifespan).

### 2. Trusted proxy headers (production-compatible)

Use when an upstream proxy (OAuth2 Proxy, Envoy, Istio, Azure AD Application Proxy)
authenticates the user and forwards identity claims as headers:

```
MI_AUTH_TRUST_FORWARDED_HEADERS=true
MI_AUTH_SUBJECT_HEADER=x-auth-request-user    # default
MI_AUTH_ROLE_HEADER=x-auth-request-role        # default
MI_AUTH_ORG_HEADER=x-auth-request-org          # default
MI_AUTH_SITE_HEADER=x-auth-request-site        # default
MI_AUTH_SITES_HEADER=x-auth-request-sites      # default (CSV)
```

**Important:** The upstream proxy must strip or ignore these headers from
untrusted client requests.  Never expose the API directly to the internet
when relying on forwarded headers — only the proxy should be internet-facing.

Trusted-header identities must carry an `org_id` claim to pass tenant scope
checks.  Unlike dev headers, there is no bypass for missing claims.

### 3. Dev headers (local development only)

```
MI_DEV_ALLOW_HEADERS=true   # NEVER set in production
```

When enabled, the following client-supplied headers are trusted:

| Header | Purpose |
|---|---|
| `x-user-id` or `x-dev-user` | Subject (required) |
| `x-user-role` | Role (default: `planner`) |
| `x-user-org` | Organisation / tenant ID |
| `x-user-site` | Primary site |
| `x-user-sites` | Comma-separated site list |

Dev-header identities are marked with `auth_source: "dev-header"`.  They receive
a limited scope bypass: if no `org_id` claim is present they pass the org scope
check (which allows demo data to flow without configuring a real tenant).  This
bypass is deliberately absent for JWT and trusted-header identities.

---

## Tenant scope enforcement

Tenant isolation is enforced at the route handler level, not at the database layer.

### Rules

1. If the authenticated identity carries an `org_id`, any query or write `tenant_id`
   parameter **must** match.  Mismatches produce `HTTP 403 Cross-tenant access is not
   permitted`.

2. If the identity carries an `org_id` and no `tenant_id` filter is supplied by the
   caller, the query is **automatically scoped** to the identity's org.  Callers
   cannot opt out of this scoping.

3. If the identity has no `org_id` claim (only possible for dev-header identities),
   data is unscoped — the caller-supplied filter (or no filter) applies.  This is
   the demo/development mode.

### Endpoints with enforced tenant scope

| Router | Enforcement |
|---|---|
| `POST /api/v1/failure-events` | `tenant_id` in payload must match identity org |
| `GET /api/v1/failure-events` | `tenant_id` query param must match identity org |
| `GET /api/v1/reliability/fleet` | `tenant_id` query param must match identity org |
| `POST /api/v1/rca/feedback` | `org_id` from run payload is checked against identity |
| `GET /api/v1/rca/feedback` | rows filtered to identity-visible orgs |
| `POST /api/v1/agents/rca/trigger` | `org_id` of the event is checked against identity |
| `POST /api/v1/agents/pm/proposals/.../approve` | proposal org/site is checked against identity |

---

## Role-based access control

Roles extracted from the identity are compared against:

| Guard | Required roles |
|---|---|
| `APPROVAL_ROLES` | `planner`, `maintainer`, `admin` |
| `ADMIN_ROLES` | `admin`, `maintainer` |

Applied at:

- `/api/v1/agents/rca/trigger` — requires `APPROVAL_ROLES`
- `/api/v1/agents/pm/proposals/{id}/approve` — requires `APPROVAL_ROLES`; admin retry requires `ADMIN_ROLES`
- `/api/v1/agents/pm/proposals/{id}/analyze` — requires any authenticated identity
- Admin-only routes — require `ADMIN_ROLES`

---

## Local demo vs production configuration

| Behaviour | Local demo | Production |
|---|---|---|
| Auth source | `MI_DEV_ALLOW_HEADERS=true` | `MI_AUTH_JWT_JWKS_URL` or `MI_AUTH_TRUST_FORWARDED_HEADERS=true` |
| Tenant isolation | No `org_id` → data is unscoped | Identity must carry `org_id` |
| Org scope bypass | Enabled for dev-header identities | Disabled |
| `GET /api/v1/whoami` | Returns `auth_source: "dev-header"` | Returns `auth_source: "jwt-bearer"` or `"trusted-header"` |
| Missing identity | 403 on protected routes | 403 on protected routes |

---

## Reverse proxy / forwarded header assumptions

When deploying behind a reverse proxy with `MI_AUTH_TRUST_FORWARDED_HEADERS=true`:

1. The proxy must **own** the forwarded headers — strip them from downstream requests.
2. The API must not be reachable except through the proxy.
3. Set `MI_AUTH_TRUST_FORWARDED_HEADERS=false` unless a proxy is in the path.
4. Configure the proxy to include `x-auth-request-org` and `x-auth-request-sites` so
   that tenant scope checks work correctly.

---

## Related issues and docs

- Issue #39: Security: production auth, tenant isolation, and scoped RBAC enforcement
- Issue #27: Audit logging (actor identity is surfaced in audit rows)
- `AGENTS.md` → middleware section for code locations
