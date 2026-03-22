# Performance Checklist — Maintenance Intelligence Portal

## Patterns We Prefer

| Pattern | Why |
|---------|-----|
| **Event delegation** on container elements | One listener per container instead of N listeners per child. Survives innerHTML replacements without re-attachment. |
| **Chart.js cleanup** before DOM replacement | Call `chart.destroy()` before replacing innerHTML to prevent canvas/WebGL leaks. |
| **Bounded state caches** | Evict oldest entries from Maps like `detailsById` to prevent unbounded memory growth in long sessions. |
| **Skeleton loaders** with fixed dimensions | Reserve layout space before async content arrives to prevent CLS. |
| **CSS `contain: layout style`** on heavy panels | Limits browser reflow/repaint scope to the panel boundary. |
| **`requestAnimationFrame`** for DOM reads after writes | Batch layout reads after innerHTML to avoid forced synchronous layout. |
| **Debounced input handlers** | Prevents excessive state updates and re-renders on fast typing. |
| **Lazy data fetching** | Only fetch outcomes, triage, handoff data when a run is selected, not on page load. |

## Patterns We Avoid

| Anti-pattern | Risk |
|--------------|------|
| **Per-node `addEventListener` in render loops** | Leaks listeners, scales O(N) per render, slows down re-renders. |
| **Unbounded Maps/Sets in state** | Memory grows linearly with usage over long sessions. |
| **Full innerHTML replacement for minor state changes** | Destroys and recreates entire subtrees; kills Chart.js instances. |
| **`querySelectorAll().forEach()` for event binding** | Slow at scale; must be repeated after every re-render. |
| **Inline `JSON.stringify` on large objects** | Blocks main thread; consider deferring to `requestIdleCallback`. |
| **Dynamic content without reserved dimensions** | Causes CLS spikes when panels load. |

## Performance Budgets (Guidelines)

| Metric | Target |
|--------|--------|
| DOM nodes per screen | < 1,500 |
| Event listeners on `detailView` | Delegated: 4 (click, change, input, submit) |
| Chart.js instances active | ≤ 4 at any time |
| State cache entries (`detailsById`) | ≤ 50 |
| LCP | < 2.5s |
| INP | < 200ms |
| CLS | < 0.1 |

## Web Vitals Instrumentation

The portal includes a lightweight Web Vitals observer at `assets/perfMetrics.js`.
To enable console logging during development, add `?portalDev=1` to the URL. The module tracks LCP, CLS, INP, FCP, and TTFB using native `PerformanceObserver` APIs — no third-party SDKs.

For Grafana integration, emit these metrics to a backend endpoint:
- `portal.lcp{route="/portal"}` — Largest Contentful Paint
- `portal.inp{route="/portal"}` — Interaction to Next Paint
- `portal.cls{route="/portal"}` — Cumulative Layout Shift
- `portal.fcp{route="/portal"}` — First Contentful Paint
- `portal.ttfb{route="/portal"}` — Time to First Byte

## Refactoring Priorities

1. **Extract detail sections** into lazy-rendered functions that only rebuild their own subtree on state change (avoids full `renderDetail` rebuild).
2. **Virtualize run list** if run count exceeds ~50 items (currently renders all cards).
3. **Move JSON.stringify** to a Web Worker for payloads > 50KB.
4. **Split outcomes/triage/handoff** into dynamically imported modules.
