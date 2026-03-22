/**
 * Chart.js helpers for rendering trend charts in the outcomes panel.
 * Expects Chart.js to be loaded globally from CDN.
 */

const chartRegistry = new Map();

export function destroyChart(chartId) {
	const existing = chartRegistry.get(chartId);
	if (existing) {
		existing.destroy();
		chartRegistry.delete(chartId);
	}
}

export function destroyAllCharts() {
	for (const [id, chart] of chartRegistry) {
		chart.destroy();
		chartRegistry.delete(id);
	}
}

export function createTrendChart(canvasId, { labels, values, color, isRate = false } = {}) {
	if (typeof Chart === "undefined") return null;

	const canvas = document.getElementById(canvasId);
	if (!canvas) return null;

	destroyChart(canvasId);

	const ctx = canvas.getContext("2d");
	const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
	gradient.addColorStop(0, color + "28");
	gradient.addColorStop(1, color + "04");

	const chart = new Chart(ctx, {
		type: "line",
		data: {
			labels,
			datasets: [{
				data: values,
				borderColor: color,
				backgroundColor: gradient,
				borderWidth: 2.5,
				pointRadius: 0,
				pointHoverRadius: 5,
				pointHoverBackgroundColor: color,
				pointHoverBorderColor: "#fff",
				pointHoverBorderWidth: 2,
				fill: true,
				tension: 0.35,
			}],
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			interaction: { intersect: false, mode: "index" },
			plugins: {
				legend: { display: false },
				tooltip: {
					backgroundColor: "rgba(15, 23, 42, 0.92)",
					titleColor: "#e2e8f0",
					bodyColor: "#e2e8f0",
					borderColor: "rgba(255, 255, 255, 0.08)",
					borderWidth: 1,
					cornerRadius: 8,
					padding: 10,
					displayColors: false,
					callbacks: {
						label(context) {
							const v = context.parsed.y;
							return isRate ? (v * 100).toFixed(1) + "%" : v.toLocaleString();
						},
					},
				},
			},
			scales: {
				x: {
					display: true,
					grid: { display: false },
					ticks: { maxTicksLimit: 4, color: "#94a3b8", font: { size: 10 } },
					border: { display: false },
				},
				y: {
					display: true,
					grid: { color: "rgba(15, 23, 42, 0.05)", drawBorder: false },
					ticks: {
						maxTicksLimit: 4,
						color: "#94a3b8",
						font: { size: 10 },
						callback(value) {
							return isRate ? (value * 100).toFixed(0) + "%" : value;
						},
					},
					border: { display: false },
					beginAtZero: true,
				},
			},
			animation: { duration: 600, easing: "easeOutQuart" },
		},
	});

	chartRegistry.set(canvasId, chart);
	return chart;
}

export function createDonutChart(canvasId, { labels, values, colors } = {}) {
	if (typeof Chart === "undefined") return null;

	const canvas = document.getElementById(canvasId);
	if (!canvas) return null;

	destroyChart(canvasId);

	const chart = new Chart(canvas, {
		type: "doughnut",
		data: {
			labels,
			datasets: [{
				data: values,
				backgroundColor: colors,
				borderWidth: 0,
				hoverOffset: 4,
			}],
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			cutout: "70%",
			plugins: {
				legend: {
					position: "bottom",
					labels: { color: "#64748b", font: { size: 11 }, padding: 12 },
				},
				tooltip: {
					backgroundColor: "rgba(15, 23, 42, 0.92)",
					titleColor: "#e2e8f0",
					bodyColor: "#e2e8f0",
					cornerRadius: 8,
					padding: 10,
				},
			},
			animation: { duration: 500, easing: "easeOutQuart" },
		},
	});

	chartRegistry.set(canvasId, chart);
	return chart;
}
