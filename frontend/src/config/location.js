/**
 * Dashboard fuel-price location: this device's position (only after this
 * device agreed), the saved location, or no position at all.
 */

// Per device and kept at sign-out, like theme and language (docs/PRIVATE_BROWSER_DATA.md).
export const LOCATION_CONSENT_STORAGE_KEY = 'gearcargo_location_consent'
export const LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY = 'gearcargo_location_consent_deferred_at'
export const LOCATION_CONSENT_GRANTED = 'granted'
export const LOCATION_CONSENT_DEFERRED = 'deferred'
// "Not now" lasts as long as the install prompt's.
export const LOCATION_CONSENT_DEFER_MS = 7 * 24 * 60 * 60 * 1000

// Identity-scoped and cleared at sign-out by utils/privateStorage.js;
// browser-tests/privateStorageLifecycle.mjs checks this literal.
export const LOCATION_CACHE_STORAGE_KEY = 'gearcargo_user_location'
export const LOCATION_CACHE_MAX_AGE_MS = 10 * 60 * 1000

// Prices are national averages, so a network-based position is enough and shares less than GPS.
export const GEOLOCATION_OPTIONS = Object.freeze({ enableHighAccuracy: false, timeout: 10 * 1000, maximumAge: 5 * 60 * 1000 })

// No coordinates: the server answers for the request country without a geocoder lookup.
export const FALLBACK_LOCATION = Object.freeze({ lat: null, lon: null })

// Request country when the account has no country_preference, as VehicleDetail does.
export const FALLBACK_COUNTRY = 'UK'
// The fuel-price service says UK where Intl.DisplayNames expects the ISO code GB.
export const ISO_REGION_CODES = Object.freeze({ UK: 'GB' })

// The Location Settings card on the Profile tab.
export const LOCATION_SETTINGS_ANCHOR = 'location-settings'
export const LOCATION_SETTINGS_PATH = `/settings/profile#${LOCATION_SETTINGS_ANCHOR}`
// Router state from the consent dialog's link: the card opens with auto-detect off, unsaved.
export const MANUAL_LOCATION_STATE_KEY = 'manualLocation'
