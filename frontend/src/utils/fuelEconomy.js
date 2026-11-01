export const KM_PER_MILE = 1.609344
export const LITERS_PER_GALLON_UK = 4.54609
export const LITERS_PER_GALLON_US = 3.785411784
// L/100km → MPG conversion factors. US and Imperial (UK) gallons differ, so a
// miles user's MPG must use the right one or the figure is ~20% off (F16).
const MPG_US = 100 * LITERS_PER_GALLON_US / KM_PER_MILE
const MPG_UK = 100 * LITERS_PER_GALLON_UK / KM_PER_MILE

export function normalizeDistanceUnit(unit) {
  const normalized = String(unit || '').trim().toLowerCase()
  if (normalized === 'mi' || normalized === 'mile' || normalized === 'miles') {
    return 'miles'
  }
  return 'km'
}

/**
 * Resolve which gallon system a user is on: 'us' or 'uk'.
 *
 * Explicit US/imperial volume choice wins. For legacy preferences, signals are:
 * explicit country_preference, then currency (USD→us / GBP→uk). Falls back to
 * 'uk' (the app's default region: default currency GBP, £), so a miles user is
 * only ever shown US MPG when there's a positive US signal.
 */
export function resolveFuelSystem({ country, currency, volumeUnit } = {}) {
  if (volumeUnit === 'gallons_us') return 'us'
  if (volumeUnit === 'gallons_uk') return 'uk'
  const c = String(country || '').toUpperCase()
  if (c === 'US' || c === 'USA') return 'us'
  if (c === 'GB' || c === 'UK') return 'uk'
  if (String(currency || '').toUpperCase() === 'USD') return 'us'
  return 'uk'
}

function mpgFactor(system) {
  return system === 'us' ? MPG_US : MPG_UK
}

export function lPer100KmToMpg(lPer100Km, system = 'uk') {
  const value = Number(lPer100Km)
  if (!Number.isFinite(value) || value <= 0) {
    return null
  }
  return mpgFactor(system) / value
}

export function kmToMiles(km) {
  const value = Number(km)
  if (!Number.isFinite(value)) {
    return null
  }
  return value / KM_PER_MILE
}

export function milesToKm(miles) {
  const value = Number(miles)
  if (!Number.isFinite(value)) {
    return null
  }
  return value * KM_PER_MILE
}

export function getFuelEconomyUnit(distanceUnit) {
  return normalizeDistanceUnit(distanceUnit) === 'miles' ? 'MPG' : 'L/100km'
}

/**
 * Format an L/100km value for display.
 *
 * For miles users the value is converted to MPG using the correct gallon system
 * ('uk' default | 'us'); `mpgLabel` supplies the already-localized unit string
 * (units.mpgUk / units.mpgUs) so the util stays i18n-free. km users always see
 * the universal "L/100km".
 */
export function formatFuelEconomy(valueLPer100Km, distanceUnit, decimals = 1, options = {}) {
  const { system = 'uk', mpgLabel = 'MPG' } = options
  const value = Number(valueLPer100Km)
  if (!Number.isFinite(value) || value <= 0) {
    return '-'
  }

  if (normalizeDistanceUnit(distanceUnit) === 'miles') {
    const mpg = lPer100KmToMpg(value, system)
    return mpg ? `${mpg.toFixed(decimals)} ${mpgLabel}` : '-'
  }

  return `${value.toFixed(decimals)} L/100km`
}

// ── Volume unit (F27) ────────────────────────────────────────────────────────
// Storage is ALWAYS litres; distances retain each vehicle's declared unit.
// These helpers convert at the display/input boundary when the user's
// volume_unit preference is gallons_us/gallons_uk. Legacy 'gallons' retains
// the existing regional fallback; no stored quantities are converted.


export function usesGallons(user) {
  return ['gallons', 'gallons_us', 'gallons_uk'].includes(user?.volume_unit)
}

function gallonFactor(user) {
  const system = resolveFuelSystem({
    volumeUnit: user?.volume_unit,
    country: user?.country_preference,
    currency: user?.currency,
  })
  return system === 'us' ? LITERS_PER_GALLON_US : LITERS_PER_GALLON_UK
}

/** Stored litres → the user's display volume (litres pass through). */
export function litersToDisplayVolume(liters, user) {
  const v = Number(liters)
  if (!Number.isFinite(v)) return null
  return usesGallons(user) ? v / gallonFactor(user) : v
}

/** Form input in the user's unit → litres for the API payload. */
export function displayVolumeToLiters(value, user) {
  const v = Number(value)
  if (!Number.isFinite(v)) return null
  return usesGallons(user) ? v * gallonFactor(user) : v
}

/** Stored price-per-litre → the user's per-unit price (per gallon if active). */
export function pricePerLiterToDisplay(price, user) {
  const v = Number(price)
  if (!Number.isFinite(v)) return null
  return usesGallons(user) ? v * gallonFactor(user) : v
}

/** Form per-unit price → price-per-litre for the API payload. */
export function displayPriceToPerLiter(price, user) {
  const v = Number(price)
  if (!Number.isFinite(v)) return null
  return usesGallons(user) ? v / gallonFactor(user) : v
}

/** Localized volume label, including the gallon standard. */
export function volumeUnitLabel(user, t) {
  if (!usesGallons(user)) return (t && t('units.liters')) || 'L'
  const system = resolveFuelSystem({ volumeUnit: user?.volume_unit, country: user?.country_preference, currency: user?.currency })
  return system === 'us' ? ((t && t('units.gallonsUs')) || 'US gal') : ((t && t('units.gallonsUk')) || 'imp gal')
}

const sameInput = (left, right) => {
  if (left == null || left === '' || right == null || right === '') return String(left ?? '') === String(right ?? '')
  return Number.isFinite(Number(left)) && Number.isFinite(Number(right))
    ? Number(left) === Number(right) : left === right
}

/** Build an edit patch without converting unchanged rounded display values. */
export function fuelFormPayload(data, user, initialValues = null) {
  const payload = { ...data }
  if (initialValues) {
    for (const key of Object.keys(payload)) {
      const numeric = ['liters', 'price_per_liter', 'total_cost', 'mileage'].includes(key)
      if (numeric ? sameInput(data[key], initialValues[key]) : data[key] === initialValues[key]) delete payload[key]
    }
  }
  if ('liters' in payload) payload.liters = data.liters === '' ? null : displayVolumeToLiters(data.liters, user)
  if ('price_per_liter' in payload) payload.price_per_liter = data.price_per_liter === '' ? null : displayPriceToPerLiter(data.price_per_liter, user)
  if ('total_cost' in payload) payload.total_cost = data.total_cost === '' ? null : Number(data.total_cost)
  if ('mileage' in payload) payload.mileage = data.mileage === '' ? null : Number(data.mileage)
  return payload
}

/** Quantity edits recalculate from unchanged canonical quantities where possible. */
export function editedFuelTotal(data, user, initialValues, originalEntry) {
  const volumeChanged = !initialValues || !sameInput(data.liters, initialValues.liters)
  const priceChanged = !initialValues || !sameInput(data.price_per_liter, initialValues.price_per_liter)
  if (!volumeChanged && !priceChanged) return null
  const liters = volumeChanged ? displayVolumeToLiters(data.liters, user) : originalEntry?.liters
  const price = priceChanged ? displayPriceToPerLiter(data.price_per_liter, user) : originalEntry?.price_per_liter
  if (data.liters === '' || data.price_per_liter === '' || liters == null || price == null) return null
  return (Number(Number(liters).toFixed(2)) * Number(Number(price).toFixed(3))).toFixed(2)
}
