import React, { useState, useCallback } from 'react';
import FileDropZone from '../components/FileDropZone';
import StatusMessage from '../components/StatusMessage';
import { uploadFile, triggerDownload } from '../utils/apiFetch';

export default function CleanerPage() {
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);
  const [resultInfo, setResultInfo] = useState(null);

  const handleFileSelected = useCallback(async (file) => {
    setStatus('uploading');
    setError(null);
    setResultInfo(null);

    const result = await uploadFile(file);

    if (result.success) {
      setStatus('done');
      setResultInfo({ filename: result.filename });
      triggerDownload(result.blob, result.filename);
    } else {
      setStatus('error');
      setError(result.error);
    }
  }, []);

  const handleReset = useCallback(() => {
    setStatus('idle');
    setError(null);
    setResultInfo(null);
  }, []);

  return (
    <div className="cleaner-page">
      <FileDropZone
        onFileSelected={handleFileSelected}
        isDisabled={status === 'uploading'}
      />

      <StatusMessage
        status={status}
        error={error}
        filename={resultInfo?.filename}
        onReset={handleReset}
      />
    </div>
  );
}
