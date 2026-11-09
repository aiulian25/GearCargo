import toast from 'react-hot-toast'

// The status region under the odometer input; both fuel forms point aria-describedby at it.
export const ODOMETER_HINT_ID = 'odometer-hint'
const MEASURED_STATUS = 'measured'
// Three sentences, still on screen after the form has navigated away.
const FUEL_WARNING_TOAST_DURATION_MS = 15000
const FUEL_WARNING_TOAST_ICON = '⚠️'

// A vehicle without a declared distance unit shows the bare reading.
function readingWithUnit(reading, unit) {
  return [reading, unit].filter(Boolean).join(' ')
}

// A lower reading is often a typo, but a back-dated fill is legitimately lower.
export function belowLatestReadingHint(value, latestReading, unit, t) {
  const hasValue = value !== '' && value != null
  const typedReading = Number(value)
  const isBelowLatest = hasValue && Number.isFinite(typedReading) && latestReading > 0 && typedReading < latestReading
  if (!isBelowLatest) return null
  return t('addFuel.odometerBelowLatest', { reading: readingWithUnit(latestReading.toLocaleString(), unit) })
}

export function measurementReason(entry, t) {
  const status = entry.measurement_status
  if (!status || status === MEASURED_STATUS) return null
  return t(`fuel.measurementStatus.${status}`)
}

export function announceFuelWarnings(warnings, t, unit) {
  for (const warning of warnings || []) {
    toast(t(`fuel.warningTypes.${warning.code}`, { previous: readingWithUnit(warning.previous?.toLocaleString(), unit) }),
      { duration: FUEL_WARNING_TOAST_DURATION_MS, icon: FUEL_WARNING_TOAST_ICON })
  }
}
