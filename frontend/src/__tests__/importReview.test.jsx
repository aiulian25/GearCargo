import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { translations } from '../i18n/translations'
import ImportReview from '../components/settings/ImportReview'
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({
  t: key => key.split('.').reduce((value, part) => value?.[part], translations.en) || key,
}) }))
afterEach(cleanup)
it('separates repeats, suggestions and changed source records with explicit apply or cancel', () => {
  const onApply = vi.fn(), onCancel = vi.fn()
  render(<ImportReview preview={{ new_records: 2, exact_repeats: 3, possible_duplicates: 1, conflicts: 1,
    records: [{ kind: 'service_entries', archive_id: 2, source_id: '42', reason: 'source_changed', existing_id: 7 }],
  }} onApply={onApply} onCancel={onCancel} />)
  expect(screen.getByText('Exact source repeats')).toBeTruthy()
  expect(screen.getByText('Possible duplicates (advisory)')).toBeTruthy()
  expect(screen.getByText(/Source record changed/)).toBeTruthy()
  expect(onApply).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Keep existing and import new records' }))
  expect(onApply).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(onCancel).toHaveBeenCalledTimes(1)
})
it('cannot accept a unit conflict, including one outside the visible row limit', () => {
  render(<ImportReview preview={{ conflicts: 101, blocked: true, records_truncated: true, records: [] }} />)
  expect(screen.getByRole('alert').textContent).toContain('distance units differ')
  expect(screen.getByRole('button', { name: 'Keep existing and import new records' }).disabled).toBe(true)
})
it('localizes every review and result category', () => {
  for (const language of ['ro', 'es']) {
    expect(Object.keys(translations[language].backup.importReview).sort()).toEqual(Object.keys(translations.en.backup.importReview).sort())
  }
})
it('explains statement collisions even outside the visible row limit', () => {
  render(<ImportReview preview={{ conflicts: 101, blocked: true, statement_collision: true, records_truncated: true, records: [] }} />)
  expect(screen.getByRole('alert').textContent).toBe(translations.en.reconciliation.sourceCollision)
  expect(screen.getByRole('alert').textContent).not.toContain('distance units')
  expect(screen.getByRole('button', { name: 'Keep existing and import new records' }).disabled).toBe(true)
})
