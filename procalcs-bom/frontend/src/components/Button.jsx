/**
 * Button.jsx — Shared button component
 * Variants: primary | secondary | danger | ghost
 * Automatically disables and shows spinner during async ops.
 */

import styles from './Button.module.css'

export default function Button({
  children,
  variant = 'primary',
  isLoading = false,
  disabled = false,
  onClick,
  type = 'button',
  size = 'md',
}) {
  const isDisabled = disabled || isLoading

  return (
    <button
      type={type}
      className={`${styles.btn} ${styles[variant]} ${styles[size]}`}
      onClick={onClick}
      disabled={isDisabled}
      aria-busy={isLoading}
    >
      {isLoading && (
        <span className={styles.spinner} aria-hidden="true" />
      )}
      {children}
    </button>
  )
}
