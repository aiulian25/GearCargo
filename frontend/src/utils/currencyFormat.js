import { localeFor } from './dateFormat'

/** Prices per litre and per distance keep cents even in zero-decimal currencies. */
export const UNIT_PRICE_FRACTION_DIGITS = 2
const FALLBACK_FRACTION_DIGITS = 2
// ISO 4217 gives HUF two minor units, but fillér coins were withdrawn in 1999 and everyday prices are whole forints.
const WHOLE_UNIT_CURRENCIES = new Set(['HUF'])
const WHOLE_UNIT_FRACTION_DIGITS = 0

function fixedFractionDigits(currency, decimals) {
  if (decimals != null) return decimals
  if (WHOLE_UNIT_CURRENCIES.has(currency)) return WHOLE_UNIT_FRACTION_DIGITS
  return null
}

/**
 * An omitted `currency` uses the bound default. A present key is authoritative: undefined, null,
 * '' or a malformed code prints the number with that code or the unknown label, never another
 * currency. A non-object second argument throws.
 */
export function createCurrencyFormatter({ language, currency: defaultCurrency, unknownCurrencyLabel = '' } = {}) {
  const locale = localeFor(language)
  // ponytail: one Intl.NumberFormat per call; cache by locale, currency and digits if a long list profiles slow.
  return (amount, options = {}) => {
    const currency = 'currency' in options ? options.currency : defaultCurrency
    const digits = fixedFractionDigits(currency, options.decimals)
    const fractionDigitRange = digits == null ? {} : { minimumFractionDigits: digits, maximumFractionDigits: digits }
    const value = Number(amount ?? 0)
    try {
      return new Intl.NumberFormat(locale, { style: 'currency', currency, ...fractionDigitRange }).format(value)
    } catch {
      const number = new Intl.NumberFormat(locale, {
        minimumFractionDigits: FALLBACK_FRACTION_DIGITS, maximumFractionDigits: FALLBACK_FRACTION_DIGITS, ...fractionDigitRange,
      }).format(value)
      return `${number} ${currency || unknownCurrencyLabel}`
    }
  }
}
