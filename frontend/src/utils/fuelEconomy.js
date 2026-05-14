const KM_PER_MILE = 1.609344
const L_PER_100KM_TO_MPG_FACTOR = 235.214583

export function normalizeDistanceUnit(unit) {
  const normalized = String(unit || '').trim().toLowerCase()
  if (normalized === 'mi' || normalized === 'mile' || normalized === 'miles') {
    return 'miles'
  }
  return 'km'
}

export function lPer100KmToMpg(lPer100Km) {
  const value = Number(lPer100Km)
  if (!Number.isFinite(value) || value <= 0) {
    return null
  }
  return L_PER_100KM_TO_MPG_FACTOR / value
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

export function formatFuelEconomy(valueLPer100Km, distanceUnit, decimals = 1) {
  const value = Number(valueLPer100Km)
  if (!Number.isFinite(value) || value <= 0) {
    return '-'
  }

  if (normalizeDistanceUnit(distanceUnit) === 'miles') {
    const mpg = lPer100KmToMpg(value)
    return mpg ? `${mpg.toFixed(decimals)} MPG` : '-'
  }

  return `${value.toFixed(decimals)} L/100km`
}
