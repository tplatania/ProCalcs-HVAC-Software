/**
 * StatusBadge.jsx — Color-coded status indicator
 * Used on profile cards to show active/inactive state.
 */

import styles from './StatusBadge.module.css'

const VARIANTS = {
  active:   { label: 'Active',   cls: 'active'   },
  inactive: { label: 'Inactive', cls: 'inactive' },
  new:      { label: 'New',      cls: 'new'      },
  error:    { label: 'Error',    cls: 'error'    },
}

export default function StatusBadge({ status = 'active', label }) {
  const variant = VARIANTS[status] ?? VARIANTS.active
  return (
    <span className={`${styles.badge} ${styles[variant.cls]}`}>
      <span className={styles.dot} />
      {label ?? variant.label}
    </span>
  )
}
