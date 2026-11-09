// @vitest-environment node
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { defaultLanguage, translations } from '../i18n/translations'

const SOURCE_ROOT = fileURLToPath(new URL('..', import.meta.url))
const SOURCE_FILE = /\.jsx?$/
const SKIPPED_DIRECTORIES = new Set(['__tests__', 'i18n'])
// t() returns the raw key when no language defines it, so a `|| 'English'` fallback never runs.
// Only literal dotted keys can be checked; computed keys such as t(`group.${code}`) are not.
const LITERAL_KEY_CALL = /(?<![\w.$])t\(\s*(['"])([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)\1/g

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return SKIPPED_DIRECTORIES.has(entry.name) ? [] : sourceFiles(path)
    return SOURCE_FILE.test(entry.name) ? [path] : []
  })
}

const translationAt = (tree, key) => key.split('.').reduce((node, part) => node?.[part], tree)

describe('literal translation keys in the source', () => {
  it('every literal t() key resolves to a string in the default language', () => {
    const undefinedKeys = sourceFiles(SOURCE_ROOT).flatMap(file =>
      [...readFileSync(file, 'utf8').matchAll(LITERAL_KEY_CALL)]
        .map(match => match[2])
        .filter(key => typeof translationAt(translations[defaultLanguage], key) !== 'string')
        .map(key => `${relative(SOURCE_ROOT, file)}: ${key}`))
    expect(undefinedKeys).toEqual([])
  })
})
