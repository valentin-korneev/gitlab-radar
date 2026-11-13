let toastTimer = null;
function showToast(message, type) {
  const toast = document.querySelector('#global-error');
  toast.textContent = message;
  toast.classList.toggle('success', type === 'success');
  toast.classList.toggle('error', type === 'error');
  toast.hidden = false;
  if (toastTimer) window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toast.hidden = true; }, 4000);
}
function showSuccess(message) {
  showToast(message, 'success');
}
function showError(error) {
  showToast(error.message, 'error');
}


export { showError, showSuccess };
