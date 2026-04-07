/**
 * Layout.jsx — Shell with sidebar nav and content area
 * Wraps all pages. Sidebar shows ProCalcs branding and nav.
 */

import { Outlet, NavLink } from 'react-router-dom'
import styles from './Layout.module.css'

export default function Layout() {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>PC</span>
          <div>
            <div className={styles.brandName}>ProCalcs</div>
            <div className={styles.brandSub}>BOM Manager</div>
          </div>
        </div>

        <nav className={styles.nav}>
          <NavLink
            to="/profiles"
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
            }
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
            Client Profiles
          </NavLink>
        </nav>

        <div className={styles.sidebarFooter}>
          <span>Richard &amp; Windell</span>
          <span className={styles.footerSub}>Profile Managers</span>
        </div>
      </aside>

      <main className={styles.content}>
        <Outlet />
      </main>
    </div>
  )
}
