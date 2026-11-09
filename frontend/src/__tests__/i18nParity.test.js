import { describe, expect, it } from 'vitest'
import { defaultLanguage, supportedLanguages, translations } from '../i18n/translations'

const leafEntries = (tree, prefix = '') => Object.entries(tree).flatMap(([key, value]) => {
  const path = `${prefix}${key}`
  const isGroup = value !== null && typeof value === 'object'
  return isGroup ? leafEntries(value, `${path}.`) : [[path, value]]
})

const keysOf = language => leafEntries(translations[language]).map(([path]) => path)

const referenceKeys = keysOf(defaultLanguage)
const translatedLanguages = supportedLanguages.filter(language => language !== defaultLanguage)

describe('translation parity across the whole tree', () => {
  it('defines a translation tree for exactly the supported languages', () => {
    expect(Object.keys(translations).sort()).toEqual([...supportedLanguages].sort())
  })

  it.each(translatedLanguages)('%s defines every key the default language defines', language => {
    const languageKeys = new Set(keysOf(language))
    expect(referenceKeys.filter(key => !languageKeys.has(key))).toEqual([])
  })

  it.each(translatedLanguages)('%s defines no key the default language lacks', language => {
    const knownKeys = new Set(referenceKeys)
    expect(keysOf(language).filter(key => !knownKeys.has(key))).toEqual([])
  })

  it.each(supportedLanguages)('%s translates every key to a non-empty string', language => {
    const blankKeys = leafEntries(translations[language])
      .filter(([, value]) => typeof value !== 'string' || value.trim() === '')
      .map(([path]) => path)
    expect(blankKeys).toEqual([])
  })
})
