/**
 * Spinner.jsx — Full-page or inline loading indicator
 */

import styles from './Spinner.module.css'

export default function Spinner({ fullPage = false, label = 'Loading...' }) {
  if (fullPage) {
    return (
      <div className={styles.fullPage}>
        <div className={styles.ring} />
        <span className={styles.label}>{label}</span>
      </div>
    )
  }
  return <div className={styles.ring} aria-label={label} />
}
