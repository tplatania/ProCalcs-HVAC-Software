/**
 * Centralized API fetch wrapper.
 * Handles errors, timeouts, and response parsing.
 */

const API_BASE = '/api/v1/tools';
const DEFAULT_TIMEOUT_MS = 120000; // 2 min — large files take time

export async function uploadFile(file) {
  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort(),
    DEFAULT_TIMEOUT_MS
  );

  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/pdf-to-cad`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData?.error || `Upload failed (${response.status})`,
      };
    }

    // Response is a file download (blob)
    const blob = await response.blob();
    const filename = getFilenameFromResponse(response) || 'cleaned.dxf';

    return {
      success: true,
      blob,
      filename,
    };
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      return { success: false, error: 'Upload timed out. Try a smaller file.' };
    }
    return { success: false, error: err.message || 'Network error' };
  }
}

function getFilenameFromResponse(response) {
  const disposition = response.headers.get('Content-Disposition');
  if (!disposition) return null;
  const match = disposition.match(/filename="?([^";\n]+)"?/);
  return match?.[1] || null;
}

export function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
