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

  const upload = async () => {
    const file = fileInputRef.current?.files?.[0]
    if (!file) return
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

  return (
    <div className="documents">
      <div className="documents-upload">
        <input type="file" ref={fileInputRef} disabled={isUploading} />
        <button className="btn btn-primary" onClick={upload} disabled={isUploading}>
          {isUploading ? 'Uploading...' : 'Upload'}
        </button>
      </div>

      {documents.length === 0 ? (
        <p className="documents-empty">No documents uploaded yet.</p>
      ) : (
        <ul className="documents-list">
          {documents.map((doc) => (
            <li key={doc.id} className="documents-item">
              <span className="documents-filename">{doc.filename}</span>
              <span className={`status-pill status-pill-${doc.status}`}>
                {doc.status}
                {doc.status === 'failed' && doc.error_message && ` · ${doc.error_message}`}
              </span>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="error-text">{error}</p>}
    </div>
  )
}
