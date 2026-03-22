/**
 * DOM utility helpers for the Maintenance Intelligence portal.
 */

export function $(selector, parent = document) {
	return parent.querySelector(selector);
}

export function $$(selector, parent = document) {
	return [...parent.querySelectorAll(selector)];
}

export function createElement(tag, attrs = {}, children = []) {
	const el = document.createElement(tag);
	for (const [key, value] of Object.entries(attrs)) {
		if (key === "className") {
			el.className = value;
		} else if (key === "textContent") {
			el.textContent = value;
		} else if (key === "innerHTML") {
			el.innerHTML = value;
		} else if (key.startsWith("on") && typeof value === "function") {
			el.addEventListener(key.slice(2).toLowerCase(), value);
		} else if (key === "dataset" && typeof value === "object") {
			Object.assign(el.dataset, value);
		} else {
			el.setAttribute(key, value);
		}
	}
	for (const child of children) {
		if (typeof child === "string") {
			el.appendChild(document.createTextNode(child));
		} else if (child instanceof Node) {
			el.appendChild(child);
		}
	}
	return el;
}

export function renderSkeletonCards(count = 4) {
	return Array.from({ length: count }, (_, i) => `
		<div class="skeleton-card" style="animation-delay: ${i * 80}ms">
			<div class="skeleton skeleton-text short" style="height: 12px; margin-bottom: 12px"></div>
			<div class="skeleton skeleton-text long" style="height: 16px; margin-bottom: 10px"></div>
			<div class="skeleton skeleton-text medium" style="height: 12px; margin-bottom: 8px"></div>
			<div class="skeleton skeleton-text short" style="height: 12px"></div>
		</div>
	`).join("");
}

export function renderDetailSkeleton() {
	return `
		<div style="display:grid;gap:16px;padding:8px 0">
			<div class="skeleton skeleton-text long" style="height:20px"></div>
			<div class="skeleton skeleton-text medium" style="height:14px"></div>
			<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
				<div class="skeleton-card"><div class="skeleton skeleton-metric"></div></div>
				<div class="skeleton-card"><div class="skeleton skeleton-metric"></div></div>
			</div>
			<div class="skeleton skeleton-chart"></div>
			<div class="skeleton skeleton-text long" style="height:14px"></div>
			<div class="skeleton skeleton-text medium" style="height:14px"></div>
			<div class="skeleton skeleton-text short" style="height:14px"></div>
		</div>
	`;
}

export function debounce(fn, delay = 200) {
	let timer;
	return function (...args) {
		clearTimeout(timer);
		timer = setTimeout(() => fn.apply(this, args), delay);
	};
}
