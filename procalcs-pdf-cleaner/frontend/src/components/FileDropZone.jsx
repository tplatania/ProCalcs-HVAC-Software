import React, { useState, useRef, useCallback } from 'react';

const ALLOWED_EXTENSIONS = ['.dwg', '.dxf'];

export default function FileDropZone({ onFileSelected, isDisabled }) {
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef(null);

  const validateFile = (file) => {
    if (!file) return 'No file selected.';
    const ext = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Only ${ALLOWED_EXTENSIONS.join(', ')} files are accepted.`;
    }
    return null;
  };

  const handleFile = useCallback((file) => {
    const error = validateFile(file);
    if (error) {
      alert(error);
      return;
    }
    onFileSelected(file);
  }, [onFileSelected]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(false);
    if (isDisabled) return;
    const file = e.dataTransfer?.files?.[0];
    if (file) handleFile(file);
  }, [isDisabled, handleFile]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    if (!isDisabled) setIsDragOver(true);
  }, [isDisabled]);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleClick = () => {
    if (!isDisabled) inputRef.current?.click();
  };

  const handleInputChange = (e) => {
    const file = e.target?.files?.[0];
    if (file) handleFile(file);
    e.target.value = '';
  };

  const zoneClass = [
    'drop-zone',
    isDragOver ? 'drop-zone--active' : '',
    isDisabled ? 'drop-zone--disabled' : '',
  ].filter(Boolean).join(' ');

  return (
    <div
      className={zoneClass}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={handleClick}
      role="button"
      tabIndex={0}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".dwg,.dxf"
        onChange={handleInputChange}
        style={{ display: 'none' }}
      />
      <div className="drop-zone__content">
        <span className="drop-zone__icon">📐</span>
        <p className="drop-zone__text">
          {isDisabled
            ? 'Processing...'
            : 'Drop your DWG or DXF file here — or click to browse'}
        </p>
      </div>
    </div>
  );
}
