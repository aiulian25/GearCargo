/**
 * ShareTarget — Web Share Target landing page.
 *
 * The service worker stashes a shared receipt image (from the OS share sheet)
 * in CacheStorage and redirects here. We read it once (then delete it from the
 * cache for privacy), let the user pick a vehicle, and reuse the existing
 * ScanReceiptBanner to upload it to that vehicle and run OCR — landing the photo
 * straight in the OCR upload flow.
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { vehicleApi } from '../services/api'
import { useTranslation } from '../contexts/LanguageContext'
import ScanReceiptBanner from '../components/ui/ScanReceiptBanner'

const SHARE_TARGET_CACHE = 'share-target-cache'
const SHARED_FILE_KEY = '/__shared_receipt'

export default function ShareTarget() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [vehicles, setVehicles] = useState([])
  const [vehicleId, setVehicleId] = useState('')
  const [started, setStarted] = useState(false)
  const [uploadedId, setUploadedId] = useState(null)
  const [loading, setLoading] = useState(true)

  // Read the shared file the SW stashed, then remove it from cache (privacy).
  useEffect(() => {
    let objectUrl
    let cancelled = false
    ;(async () => {
      try {
        if (typeof caches === 'undefined') return
        const cache = await caches.open(SHARE_TARGET_CACHE)
        const res = await cache.match(SHARED_FILE_KEY)
        if (res) {
          const blob = await res.blob()
          if (!cancelled && blob.size > 0) {
            const name = decodeURIComponent(res.headers.get('x-shared-filename') || 'receipt.jpg')
            setFile(new File([blob], name, { type: blob.type || 'image/jpeg' }))
            objectUrl = URL.createObjectURL(blob)
            setPreviewUrl(objectUrl)
          }
          await cache.delete(SHARED_FILE_KEY)
        }
      } catch {
        // Ignore — empty state is shown when no file is available.
      }
    })()
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [])

  // Load the user's vehicles; auto-select when there is only one.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await vehicleApi.getAll()
        const list = res.data.vehicles || []
        if (!cancelled) {
          setVehicles(list)
          if (list.length === 1) setVehicleId(String(list[0].id))
        }
      } catch {
        // Ignore — handled by the "add a vehicle first" notice.
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  const selectedVehicle = vehicles.find((v) => String(v.id) === String(vehicleId))

  // Empty state — nothing was shared (e.g. direct navigation or after reload).
  if (!loading && !file) {
    return (
      <div className="p-4 pb-24 max-w-lg mx-auto">
        <h1 className="text-lg font-semibold mb-2">{t('shareTarget.title')}</h1>
        <div className="card text-center py-10">
          <p className="text-sm text-[var(--color-text-muted)] mb-4">
            {t('shareTarget.noReceiptDesc')}
          </p>
          <button onClick={() => navigate('/vehicles')} className="btn btn-primary">
            {t('shareTarget.browseVehicles')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 pb-24 max-w-lg mx-auto">
      <h1 className="text-lg font-semibold mb-1">{t('shareTarget.title')}</h1>
      <p className="text-sm text-[var(--color-text-muted)] mb-4">{t('shareTarget.description')}</p>

      {/* Receipt preview */}
      {previewUrl && (
        <div className="card mb-4 overflow-hidden">
          <img
            src={previewUrl}
            alt={t('shareTarget.title')}
            className="w-full max-h-64 object-contain rounded-lg bg-[var(--color-bg-tertiary)]"
          />
        </div>
      )}

      {/* No vehicles yet */}
      {!loading && vehicles.length === 0 && (
        <div className="bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 px-4 py-3 rounded-xl text-sm mb-4">
          {t('validation.addVehicleFirst') || 'You need to add a vehicle first.'}
        </div>
      )}

      {/* Vehicle picker + scan */}
      {vehicles.length > 0 && (
        <div className="card space-y-4">
          <div>
            <label htmlFor="share-vehicle" className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('common.vehicle') || 'Vehicle'} *
            </label>
            <select
              id="share-vehicle"
              value={vehicleId}
              onChange={(e) => setVehicleId(e.target.value)}
              disabled={started}
              className="input disabled:opacity-60"
            >
              <option value="">{t('common.selectVehicle') || 'Select vehicle'}</option>
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
          </div>

          {!started ? (
            <button
              type="button"
              onClick={() => setStarted(true)}
              disabled={!vehicleId}
              className="btn btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('shareTarget.scanButton')}
            </button>
          ) : (
            <ScanReceiptBanner
              receiptFile={file}
              vehicleId={parseInt(vehicleId, 10)}
              onUploadComplete={setUploadedId}
            />
          )}

          {/* Saved confirmation */}
          {uploadedId && (
            <div className="border-t border-[var(--color-border)] pt-4 space-y-3">
              <p className="text-sm text-green-600 dark:text-green-400">
                {selectedVehicle
                  ? (t('shareTarget.savedFor') || 'Receipt saved to {vehicle}.').replace('{vehicle}', selectedVehicle.name)
                  : t('shareTarget.saved')}
              </p>
              <button
                type="button"
                onClick={() => navigate(`/vehicles/${vehicleId}/search`)}
                className="btn btn-secondary w-full"
              >
                {t('shareTarget.viewDocuments')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
