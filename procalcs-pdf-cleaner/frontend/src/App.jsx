import React from 'react';
import CleanerPage from './pages/CleanerPage';

export default function App() {
  return (
    <div className="app-container">
      <header className="app-header">
        <h1>ProCalcs CAD Cleaner</h1>
        <p className="app-subtitle">
          Strip the noise. Keep the walls.
        </p>
      </header>
      <main>
        <CleanerPage />
      </main>
    </div>
  );
}
