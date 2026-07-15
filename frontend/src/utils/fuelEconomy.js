const KM_PER_MILE = 1.609344
// L/100km → MPG conversion factors. US and Imperial (UK) gallons differ, so a
// miles user's MPG must use the right one or the figure is ~20% off (F16).
const MPG_US = 235.215   // US gallon (3.785 L)
const MPG_UK = 282.481   // Imperial gallon (4.546 L)

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
 * The US is the exception — everyone else on miles (the UK and other Imperial
 * regions) uses Imperial MPG. Signals are checked in order of reliability:
 * explicit country_preference, then currency (USD→us / GBP→uk). Falls back to
 * 'uk' (the app's default region: default currency GBP, £), so a miles user is
 * only ever shown US MPG when there's a positive US signal.
 */
export function resolveFuelSystem({ country, currency } = {}) {
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
// Storage is ALWAYS litres (single canonical unit, like km for distance).
// These helpers convert at the display/input boundary when the user's
// volume_unit preference is 'gallons'; the gallon system (UK 4.54609 L vs
// US 3.78541 L) follows the same resolveFuelSystem signals as MPG (F16).

export const LITERS_PER_GALLON_UK = 4.54609
export const LITERS_PER_GALLON_US = 3.78541

export function usesGallons(user) {
  return user?.volume_unit === 'gallons'
}

function gallonFactor(user) {
  const system = resolveFuelSystem({
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

/** Localized short unit label: 'L' or 'gal'. */
export function volumeUnitLabel(user, t) {
  return usesGallons(user)
    ? ((t && t('units.gallons')) || 'gal')
    : ((t && t('units.liters')) || 'L')
}
