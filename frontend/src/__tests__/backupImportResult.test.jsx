import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { translations } from '../i18n/translations'
import BackupImportResult from '../components/settings/BackupImportResult'

vi.mock('../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key, params = {}) => {
      const value = key.split('.').reduce((item, part) => item?.[part], translations.en)
      if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
      return value.replace(/\{(\w+)\}/g, (_, name) => params[name] ?? `{${name}}`)
    },
  }),
}))
afterEach(cleanup)

describe('personal backup restore results', () => {
  it('keeps legacy gaps, missing files and all restored category counts visible until explicit refresh', () => {
    const onRefresh = vi.fn()
    render(<BackupImportResult onRefresh={onRefresh} result={{
      source_version: '2.0', vehicles: 1, consumable_entries: 4, todos: 2,
      skipped_records: 1, warnings: [
        { code: 'legacy_incomplete', path: 'version' },
        { code: 'missing_fields', path: 'vehicles[0]', message: 'Unavailable legacy fields: distance_unit' },
        { code: 'media_omitted', path: 'media' },
      ],
    }} />)
    expect(screen.getByRole('status').textContent).toContain('review recovery gaps')
    expect(screen.getByText('Consumables')).toBeTruthy()
    expect(screen.getByText('Tasks')).toBeTruthy()
    expect(screen.getByText('Records not restored')).toBeTruthy()
    expect(screen.getByText('Backup format: 2.0')).toBeTruthy()
    expect(screen.getByText(/Unavailable legacy fields: distance_unit/)).toBeTruthy()
    expect(onRefresh).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Finish review and refresh data' }))
    expect(onRefresh).toHaveBeenCalledTimes(1)
  })

  it('shows a clean restore without inventing warnings', () => {
    render(<BackupImportResult result={{ source_version: '4.0', vehicles: 1, warnings: [] }} onRefresh={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Import completed' })).toBeTruthy()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('has translations for every result category and warning in all supported languages', () => {
    for (const language of ['ro', 'es']) {
      for (const group of ['recordTypes', 'warningTypes']) {
        expect(Object.keys(translations[language].backup[group]).sort())
          .toEqual(Object.keys(translations.en.backup[group]).sort())
      }
    }
  })
})
