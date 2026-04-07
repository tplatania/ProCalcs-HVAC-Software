/**
 * ProfilesPage.jsx — Client profile list view
 * Shows all client profiles in a card grid.
 * Richard and Windell land here first.
 * Follows ProCalcs Design Standards v2.0
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProfiles } from '../hooks/useProfiles'
import Button from '../components/Button'
import StatusBadge from '../components/StatusBadge'
import Spinner from '../components/Spinner'
import styles from './ProfilesPage.module.css'

export default function ProfilesPage() {
  const navigate = useNavigate()
  const { profiles, isLoading, error, loadProfiles, deleteProfile } = useProfiles()
  const [deletingId, setDeletingId]     = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(null)

  useEffect(() => { loadProfiles() }, [loadProfiles])

  async function handleDelete(clientId) {
    if (confirmDelete !== clientId) {
      setConfirmDelete(clientId)
      return
    }
    setDeletingId(clientId)
    setConfirmDelete(null)
    await deleteProfile(clientId)
    setDeletingId(null)
  }

  if (isLoading && profiles.length === 0) {
    return <Spinner fullPage label="Loading profiles..." />
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Client Profiles</h1>
          <p className={styles.subtitle}>
            {profiles.length} profile{profiles.length !== 1 ? 's' : ''} configured
          </p>
        </div>
        <Button onClick={() => navigate('/profiles/new')}>
          + New Profile
        </Button>
      </header>

      {error && (
        <div className={styles.errorBanner}>
          <span>⚠</span> {error}
        </div>
      )}

      {profiles.length === 0 && !isLoading ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>📋</div>
          <h2>No profiles yet</h2>
          <p>Create your first client profile to get started.</p>
          <Button onClick={() => navigate('/profiles/new')}>
            Create First Profile
          </Button>
        </div>
      ) : (
        <div className={styles.grid}>
          {profiles.map(profile => (
            <div key={profile.client_id} className={styles.card}>
              <div className={styles.cardTop}>
                <div className={styles.cardInitial}>
                  {(profile.client_name || '?')[0].toUpperCase()}
                </div>
                <StatusBadge status={profile.is_active ? 'active' : 'inactive'} />
              </div>

              <h2 className={styles.cardName}>{profile.client_name}</h2>
              <p className={styles.cardId}>{profile.client_id}</p>

              <div className={styles.cardMeta}>
                <span className={styles.metaItem}>
                  🏬 {profile.supplier?.supplier_name || 'No supplier set'}
                </span>
                <span className={styles.metaItem}>
                  📦 {profile.part_name_overrides?.length || 0} part overrides
                </span>
              </div>

              <div className={styles.cardActions}>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate(`/profiles/${profile.client_id}`)}
                >
                  Edit
                </Button>
                <Button
                  variant={confirmDelete === profile.client_id ? 'danger' : 'ghost'}
                  size="sm"
                  isLoading={deletingId === profile.client_id}
                  onClick={() => handleDelete(profile.client_id)}
                >
                  {confirmDelete === profile.client_id ? 'Confirm Delete' : 'Delete'}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
