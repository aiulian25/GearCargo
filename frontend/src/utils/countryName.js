import { ISO_REGION_CODES } from '../config/location'

/** The country's name in the app language, or undefined so the server names it instead. */
export function countryName(country, language) {
  try {
    return new Intl.DisplayNames([language], { type: 'region', fallback: 'none' }).of(ISO_REGION_CODES[country] ?? country)
  } catch {
    // Intl throws for anything that is not a region code, such as a three-letter country_preference.
    return undefined
  }
}
