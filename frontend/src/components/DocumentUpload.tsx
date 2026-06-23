import { ChangeEvent, FormEvent, useRef, useState } from "react";

import { uploadDocument } from "../api";

type DocumentUploadProps = {
  onUploadComplete: (documentId: number) => void;
};

function DocumentUpload({ onUploadComplete }: DocumentUploadProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedFile(event.target.files?.[0] ?? null);
    setMessage(null);
    setError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setError("Choose a .txt or .epub file.");
      return;
    }

    setIsUploading(true);
    setMessage(null);
    setError(null);
    try {
      const response = await uploadDocument(selectedFile);
      setMessage(`Uploaded ${response.document.title} with ${response.document.record_count} records.`);
      setSelectedFile(null);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
      onUploadComplete(response.document.id);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <form className="upload-box" onSubmit={handleSubmit}>
      <label>
        Upload
        <input
          ref={inputRef}
          type="file"
          accept=".txt,.epub"
          onChange={handleFileChange}
          disabled={isUploading}
        />
      </label>
      <button className="primary-button" type="submit" disabled={isUploading}>
        {isUploading ? "Uploading" : "Upload document"}
      </button>
      {selectedFile ? <p className="inline-note">{selectedFile.name}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}
      {error ? <p className="error-message compact">{error}</p> : null}
    </form>
  );
}

export default DocumentUpload;
