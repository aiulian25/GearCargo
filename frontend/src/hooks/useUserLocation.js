import { useCallback, useEffect, useState } from 'react'
import { getBoundIdentity, requireCurrentIdentity } from '../utils/offlineIdentity'
import { sameIdentity } from '../utils/offlinePolicy'
import {
  FALLBACK_LOCATION, GEOLOCATION_OPTIONS, LOCATION_CACHE_MAX_AGE_MS, LOCATION_CACHE_STORAGE_KEY,
  LOCATION_CONSENT_DEFERRED, LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY, LOCATION_CONSENT_DEFER_MS,
  LOCATION_CONSENT_GRANTED, LOCATION_CONSENT_STORAGE_KEY,
} from '../config/location'

function readConsent() {
  if (localStorage.getItem(LOCATION_CONSENT_STORAGE_KEY) === LOCATION_CONSENT_GRANTED) return LOCATION_CONSENT_GRANTED
  const deferredAt = Number(localStorage.getItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY))
  const deferralActive = Date.now() - deferredAt < LOCATION_CONSENT_DEFER_MS
  return deferralActive ? LOCATION_CONSENT_DEFERRED : null
}

function savedLocation(user) {
  const hasCoordinates = user.location_lat && user.location_lon
  if (!hasCoordinates) return FALLBACK_LOCATION
  return { lat: user.location_lat, lon: user.location_lon }
}

function cachedLocation(identity) {
  try {
    const cached = JSON.parse(localStorage.getItem(LOCATION_CACHE_STORAGE_KEY))
    const fresh = cached?.timestamp && Date.now() - cached.timestamp < LOCATION_CACHE_MAX_AGE_MS
    if (!fresh || !sameIdentity(cached.identity, identity)) return null
    return { lat: cached.lat, lon: cached.lon }
  } catch {
    localStorage.removeItem(LOCATION_CACHE_STORAGE_KEY)
    return null
  }
}

/** Reads this device's position only after this device agreed; auto-detect off never reads it. */
export function useUserLocation(user) {
  const [consent, setConsent] = useState(readConsent)
  const [userLocation, setUserLocation] = useState(null)
  const [positionFailed, setPositionFailed] = useState(false)
  const autoDetect = user?.location_auto_detect !== false
  const deviceLocationAvailable = 'geolocation' in navigator && window.isSecureContext
  const wantsDevicePosition = autoDetect && deviceLocationAvailable
  // Also offered while the dialog is open, so focus can go back to the button that reopened it.
  const canAskAgain = wantsDevicePosition && consent !== LOCATION_CONSENT_GRANTED

  useEffect(() => {
    if (!autoDetect) {
      setUserLocation(savedLocation(user))
      return
    }
    if (!deviceLocationAvailable || consent === LOCATION_CONSENT_DEFERRED) {
      setUserLocation(FALLBACK_LOCATION)
      return
    }
    if (consent !== LOCATION_CONSENT_GRANTED) return
    const identity = getBoundIdentity()
    // Reused as-is: reading the device again moments later would send a second
    // lookup into the server's one-request-per-second Nominatim throttle.
    const cached = cachedLocation(identity)
    if (cached) {
      setUserLocation(cached)
      return
    }
    let cancelled = false
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try { await requireCurrentIdentity(identity) } catch { return }
        if (cancelled || !sameIdentity(identity, getBoundIdentity())) return
        const location = { lat: position.coords.latitude, lon: position.coords.longitude }
        setUserLocation(location)
        setPositionFailed(false)
        localStorage.setItem(LOCATION_CACHE_STORAGE_KEY, JSON.stringify({ ...location, identity, timestamp: Date.now() }))
      },
      (error) => {
        if (cancelled || !sameIdentity(identity, getBoundIdentity())) return
        console.warn('Geolocation error:', error)
        setUserLocation(FALLBACK_LOCATION)
        setPositionFailed(true)
      },
      GEOLOCATION_OPTIONS,
    )
    return () => { cancelled = true }
  }, [autoDetect, consent, deviceLocationAvailable, user])

  // Each choice removes the other's key, so the latest one wins even when another tab made the earlier one.
  const allowLocation = useCallback(() => {
    localStorage.setItem(LOCATION_CONSENT_STORAGE_KEY, LOCATION_CONSENT_GRANTED)
    localStorage.removeItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY)
    setConsent(LOCATION_CONSENT_GRANTED)
  }, [])
  const deferLocation = useCallback(() => {
    localStorage.setItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY, String(Date.now()))
    localStorage.removeItem(LOCATION_CONSENT_STORAGE_KEY)
    setConsent(LOCATION_CONSENT_DEFERRED)
  }, [])
  const askAgain = useCallback(() => {
    localStorage.removeItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY)
    setConsent(null)
  }, [])

  return {
    userLocation,
    // This device agreed, but the browser refused or could not supply a position.
    locationUnavailable: wantsDevicePosition && positionFailed,
    consentPending: wantsDevicePosition && !consent,
    allowLocation,
    deferLocation,
    askForLocation: canAskAgain ? askAgain : null,
  }
}
