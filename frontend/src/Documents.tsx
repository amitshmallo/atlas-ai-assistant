import { useEffect, useRef, useState } from 'react'
import type { AccountInfo, IPublicClientApplication } from '@azure/msal-browser'
import { apiBaseUrl } from './authConfig'
import { acquireApiToken } from './apiAuth'

interface DocumentMetadata {
  id: string
  filename: string
  status: 'processing' | 'ready' | 'failed'
  error_message: string | null
}

// Polls while any document is still `processing` — OCR/chunk/embed/index
// happens out of process in the blob-triggered Azure Function, so the
// frontend has no other way to know when a document becomes searchable.
const POLL_INTERVAL_MS = 4000

export function Documents({
  instance,
  account,
}: {
  instance: IPublicClientApplication
  account: AccountInfo
}) {
  const [documents, setDocuments] = useState<DocumentMetadata[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchDocuments = async () => {
    try {
      const tokenResponse = await acquireApiToken(instance, account)
      const response = await fetch(`${apiBaseUrl}/documents`, {
        headers: { Authorization: `Bearer ${tokenResponse.accessToken}` },
      })
      if (!response.ok) throw new Error(`API returned ${response.status}`)
      setDocuments(await response.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => {
    fetchDocuments()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!documents.some((doc) => doc.status === 'processing')) return
    const timer = setInterval(fetchDocuments, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documents])

  const uploadFile = async (file: File) => {
    setError(null)
    setIsUploading(true)

    try {
      const tokenResponse = await acquireApiToken(instance, account)
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(`${apiBaseUrl}/documents`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${tokenResponse.accessToken}` },
        body: formData,
      })
      if (!response.ok) throw new Error(`API returned ${response.status}`)

      if (fileInputRef.current) fileInputRef.current.value = ''
      await fetchDocuments()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsUploading(false)
    }
  }

  const onFilePicked = () => {
    const file = fileInputRef.current?.files?.[0]
    if (file) uploadFile(file)
  }

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragging(false)
    const file = event.dataTransfer.files?.[0]
    if (file) uploadFile(file)
  }

  const deleteDocument = async (documentId: string, filename: string) => {
    if (!window.confirm(`Delete "${filename}"? Atlas won't be able to search it anymore.`)) return

    setError(null)
    setDeletingId(documentId)
    try {
      const tokenResponse = await acquireApiToken(instance, account)
      const response = await fetch(`${apiBaseUrl}/documents/${documentId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${tokenResponse.accessToken}` },
      })
      if (!response.ok) throw new Error(`API returned ${response.status}`)
      setDocuments((prev) => prev.filter((doc) => doc.id !== documentId))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="documents">
      <div
        className={`documents-dropzone${isDragging ? ' documents-dropzone-active' : ''}${isUploading ? ' documents-dropzone-busy' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={onFilePicked}
          disabled={isUploading}
          className="documents-dropzone-input"
        />
        <span className="documents-dropzone-icon" aria-hidden="true">
          {isUploading ? '⏳' : '📄'}
        </span>
        <p className="documents-dropzone-text">
          {isUploading ? 'Uploading…' : 'Drop a file here, or click to browse'}
        </p>
        <p className="documents-dropzone-hint">PDF, JPEG, PNG, BMP, TIFF, or HEIF</p>
      </div>

      {documents.length === 0 ? (
        <p className="documents-empty">No documents uploaded yet.</p>
      ) : (
        <ul className="documents-list">
          {documents.map((doc) => (
            <li key={doc.id} className="documents-item">
              <span className="documents-filename" title={doc.filename}>
                {doc.filename}
              </span>
              <span className={`status-pill status-pill-${doc.status}`}>
                {doc.status}
                {doc.status === 'failed' && doc.error_message && ` · ${doc.error_message}`}
              </span>
              <button
                type="button"
                className="documents-delete-btn"
                title={`Delete ${doc.filename}`}
                aria-label={`Delete ${doc.filename}`}
                onClick={() => deleteDocument(doc.id, doc.filename)}
                disabled={deletingId === doc.id}
              >
                {deletingId === doc.id ? '…' : '🗑'}
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="error-text">{error}</p>}
    </div>
  )
}
