/**
 * App.jsx — Root component and routing
 * Follows ProCalcs Design Standards v2.0
 */

import { Routes, Route, Navigate } from 'react-router-dom'
import ProfilesPage from './pages/ProfilesPage'
import ProfileDetailPage from './pages/ProfileDetailPage'
import Layout from './components/Layout'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/profiles" replace />} />
        <Route path="/profiles" element={<ProfilesPage />} />
        <Route path="/profiles/new" element={<ProfileDetailPage mode="create" />} />
        <Route path="/profiles/:clientId" element={<ProfileDetailPage mode="edit" />} />
      </Route>
    </Routes>
  )
}
