/**
 * useProfiles.js — Custom hook for client profile CRUD
 * Encapsulates all API calls and state for profile management.
 * Components import this hook — they never call apiFetch directly.
 * Follows ProCalcs Design Standards v2.0
 */

import { useState, useCallback } from 'react'
import { apiFetch } from '../utils/apiFetch'

const BASE = '/api/v1/profiles'

export function useProfiles() {
  const [profiles, setProfiles]   = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError]         = useState(null)

  // ================================
  // Load all profiles
  // ================================
  const loadProfiles = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    const { success, data, error: err } = await apiFetch(`${BASE}/`)
    if (success) {
      setProfiles(data || [])
    } else {
      setError(err || 'Failed to load profiles.')
    }
    setIsLoading(false)
  }, [])

  // ================================
  // Create a profile
  // ================================
  const createProfile = useCallback(async (profileData) => {
    setIsLoading(true)
    setError(null)
    const result = await apiFetch(`${BASE}/`, {
      method: 'POST',
      body: JSON.stringify(profileData),
    })
    setIsLoading(false)
    if (result.success) {
      await loadProfiles()
    } else {
      setError(result.error || 'Failed to create profile.')
    }
    return result
  }, [loadProfiles])

  // ================================
  // Update a profile
  // ================================
  const updateProfile = useCallback(async (clientId, profileData) => {
    setIsLoading(true)
    setError(null)
    const result = await apiFetch(`${BASE}/${clientId}`, {
      method: 'PUT',
      body: JSON.stringify(profileData),
    })
    setIsLoading(false)
    if (result.success) {
      await loadProfiles()
    } else {
      setError(result.error || 'Failed to update profile.')
    }
    return result
  }, [loadProfiles])

  // ================================
  // Delete a profile
  // ================================
  const deleteProfile = useCallback(async (clientId) => {
    setIsLoading(true)
    setError(null)
    const result = await apiFetch(`${BASE}/${clientId}`, { method: 'DELETE' })
    setIsLoading(false)
    if (result.success) {
      setProfiles(prev => prev.filter(p => p.client_id !== clientId))
    } else {
      setError(result.error || 'Failed to delete profile.')
    }
    return result
  }, [])

  return {
    profiles,
    isLoading,
    error,
    loadProfiles,
    createProfile,
    updateProfile,
    deleteProfile,
  }
}
