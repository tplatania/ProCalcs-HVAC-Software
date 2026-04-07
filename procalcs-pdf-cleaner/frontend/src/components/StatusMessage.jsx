import React from 'react';

export default function StatusMessage({ status, error, filename, onReset }) {
  if (status === 'idle') return null;

  if (status === 'uploading') {
    return (
      <div className="status-message status-message--loading">
        <span className="status-spinner" />
        <p>Cleaning your file — stripping dimensions, text, furniture...</p>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="status-message status-message--error">
        <span className="status-icon">⚠️</span>
        <p>{error}</p>
        <button className="btn-reset" onClick={onReset}>
          Try Again
        </button>
      </div>
    );
  }

  if (status === 'done') {
    return (
      <div className="status-message status-message--success">
        <span className="status-icon">✅</span>
        <p>
          <strong>{filename}</strong> — cleaned and downloaded.
        </p>
        <button className="btn-reset" onClick={onReset}>
          Clean Another File
        </button>
      </div>
    );
  }

  return null;
}
