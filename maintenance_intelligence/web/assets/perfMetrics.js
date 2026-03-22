/**
 * Lightweight Web Vitals instrumentation for the Maintenance Intelligence portal.
 * Uses the native PerformanceObserver API — no third-party SDKs.
 *
 * Usage:
 *   import { observeWebVitals } from './perfMetrics.js';
 *   observeWebVitals({ onMetric: (metric) => console.log(metric) });
 *
 * Each metric callback receives: { name, value, rating, entries }
 *   - name: 'LCP' | 'INP' | 'CLS' | 'FCP' | 'TTFB'
 *   - value: numeric value in ms (LCP/INP/FCP/TTFB) or unitless (CLS)
 *   - rating: 'good' | 'needs-improvement' | 'poor'
 *   - entries: raw PerformanceEntry array
 */

const THRESHOLDS = {
	LCP:  [2500, 4000],
	INP:  [200, 500],
	CLS:  [0.1, 0.25],
	FCP:  [1800, 3000],
	TTFB: [800, 1800],
};

function rate(name, value) {
	const t = THRESHOLDS[name];
	if (!t) return 'unknown';
	if (value <= t[0]) return 'good';
	if (value <= t[1]) return 'needs-improvement';
	return 'poor';
}

function tryObserve(type, callback) {
	try {
		const po = new PerformanceObserver((list) => callback(list.getEntries()));
		po.observe({ type, buffered: true });
		return po;
	} catch {
		return null;
	}
}

export function observeWebVitals({ onMetric } = {}) {
	if (typeof PerformanceObserver === 'undefined' || !onMetric) return;

	tryObserve('largest-contentful-paint', (entries) => {
		const last = entries[entries.length - 1];
		if (last) onMetric({ name: 'LCP', value: last.startTime, rating: rate('LCP', last.startTime), entries });
	});

	let clsValue = 0;
	tryObserve('layout-shift', (entries) => {
		for (const entry of entries) {
			if (!entry.hadRecentInput) clsValue += entry.value;
		}
		onMetric({ name: 'CLS', value: clsValue, rating: rate('CLS', clsValue), entries });
	});

	tryObserve('first-input', (entries) => {
		const first = entries[0];
		if (first) {
			const delay = first.processingStart - first.startTime;
			onMetric({ name: 'FID', value: delay, rating: rate('INP', delay), entries });
		}
	});

	tryObserve('event', (entries) => {
		let worstINP = 0;
		for (const entry of entries) {
			const duration = entry.duration;
			if (duration > worstINP) worstINP = duration;
		}
		if (worstINP > 0) onMetric({ name: 'INP', value: worstINP, rating: rate('INP', worstINP), entries });
	});

	tryObserve('paint', (entries) => {
		const fcp = entries.find((e) => e.name === 'first-contentful-paint');
		if (fcp) onMetric({ name: 'FCP', value: fcp.startTime, rating: rate('FCP', fcp.startTime), entries: [fcp] });
	});

	const nav = performance.getEntriesByType?.('navigation')?.[0];
	if (nav) {
		onMetric({ name: 'TTFB', value: nav.responseStart, rating: rate('TTFB', nav.responseStart), entries: [nav] });
	}
}

export function logWebVitals() {
	observeWebVitals({
		onMetric: ({ name, value, rating }) => {
			const color = rating === 'good' ? '#0d9373' : rating === 'poor' ? '#dc2626' : '#d97706';
			console.log(`%c[WebVital] ${name}: ${typeof value === 'number' ? value.toFixed(1) : value} (${rating})`, `color: ${color}; font-weight: bold`);
		},
	});
}
