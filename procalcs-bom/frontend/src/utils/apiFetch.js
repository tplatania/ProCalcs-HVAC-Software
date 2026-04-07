/**
 * apiFetch.js — Centralized API call wrapper
 * All backend calls go through here.
 * Handles base URL, headers, error normalization, and JSON parsing.
 * Follows ProCalcs Design Standards v2.0
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

/**
 * Wrapper around fetch for all ProCalcs BOM API calls.
 * Returns { success, data, error } — matches backend response shape.
 *
 * @param {string} endpoint  - e.g. '/api/v1/profiles/'
 * @param {object} options   - fetch options (method, body, etc.)
 * @returns {Promise<{success: boolean, data: any, error: string|null}>}
 */
export async function apiFetch(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`

  const defaultHeaders = { 'Content-Type': 'application/json' }

  const config = {
    ...options,
    headers: { ...defaultHeaders, ...options.headers },
  }

  try {
    const response = await fetch(url, config)
    const json = await response.json()

    // Backend always returns { success, data, error }
    if (!response.ok) {
      return {
        success: false,
        data: null,
        error: json?.error || `Request failed with status ${response.status}`,
      }
    }

    return {
      success: json?.success ?? true,
      data: json?.data ?? null,
      error: json?.error ?? null,
    }

  } catch (err) {
    // Network failure or JSON parse error
    console.error('apiFetch error:', endpoint, err)
    return {
      success: false,
      data: null,
      error: 'Network error — please check your connection and try again.',
    }
  }
}
