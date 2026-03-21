/**
 * Notification helpers wrapping iziToast and SweetAlert2.
 * Gracefully degrades when CDN libraries are unavailable.
 */

export function toastSuccess(title, message, options = {}) {
	if (typeof iziToast !== "undefined") {
		iziToast.success({
			title,
			message,
			position: "topRight",
			timeout: 3500,
			...options,
		});
		return;
	}
	console.info(`[success] ${title}: ${message}`);
}

export function toastError(title, message, options = {}) {
	if (typeof iziToast !== "undefined") {
		iziToast.error({
			title,
			message,
			position: "topRight",
			timeout: 5000,
			...options,
		});
		return;
	}
	console.error(`[error] ${title}: ${message}`);
}

export function toastInfo(title, message, options = {}) {
	if (typeof iziToast !== "undefined") {
		iziToast.info({
			title,
			message,
			position: "topRight",
			timeout: 3000,
			...options,
		});
		return;
	}
	console.info(`[info] ${title}: ${message}`);
}

export function toastWarning(title, message, options = {}) {
	if (typeof iziToast !== "undefined") {
		iziToast.warning({
			title,
			message,
			position: "topRight",
			timeout: 4000,
			...options,
		});
		return;
	}
	console.warn(`[warning] ${title}: ${message}`);
}

export async function confirmAction({ title, text, confirmText = "Confirm", cancelText = "Cancel", icon = "question" } = {}) {
	if (typeof Swal !== "undefined") {
		const result = await Swal.fire({
			title,
			text,
			icon,
			showCancelButton: true,
			confirmButtonText: confirmText,
			cancelButtonText: cancelText,
			confirmButtonColor: "#0d9373",
			cancelButtonColor: "#64748b",
		});
		return result.isConfirmed;
	}
	return window.confirm(text || title);
}
