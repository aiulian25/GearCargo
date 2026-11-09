import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { createCurrencyFormatter, UNIT_PRICE_FRACTION_DIGITS } from '../utils/currencyFormat'
import { LanguageProvider, useCurrency } from '../contexts/LanguageContext'
import VehicleTimeline from '../pages/vehicles/VehicleTimeline'
import VehicleConsumables from '../pages/vehicles/VehicleConsumables'
import { translations } from '../i18n/translations'
import { consumableApi, vehicleApi } from '../services/api'

vi.mock('../services/db', () => ({ db: { settings: { get: vi.fn().mockResolvedValue(undefined), put: vi.fn() } } }))
vi.mock('../services/api', () => ({ default: { get: vi.fn(), put: vi.fn() }, vehicleApi: { getById: vi.fn(), getTimeline: vi.fn() },
  consumableApi: { getByVehicle: vi.fn() } }))

const NO_BREAK_SPACE = ' '
const UNKNOWN_LABEL = 'Unknown currency'
afterEach(() => { cleanup(); localStorage.clear() })

it.each([
  ['en', 'RON', `RON${NO_BREAK_SPACE}1,234.50`], ['en', 'EUR', '€1,234.50'],
  ['en', 'JPY', 'JP¥1,235'], ['en', 'HUF', `HUF${NO_BREAK_SPACE}1,235`],
  ['ro', 'RON', `1.234,50${NO_BREAK_SPACE}RON`], ['ro', 'EUR', `1.234,50${NO_BREAK_SPACE}EUR`],
  ['ro', 'JPY', `1.235${NO_BREAK_SPACE}JPY`], ['ro', 'HUF', `1.235${NO_BREAK_SPACE}HUF`],
  ['es', 'RON', `1234,50${NO_BREAK_SPACE}RON`], ['es', 'EUR', `1234,50${NO_BREAK_SPACE}€`],
  ['es', 'JPY', `1235${NO_BREAK_SPACE}JPY`], ['es', 'HUF', `1235${NO_BREAK_SPACE}HUF`],
])('formats 1234.5 in %s %s with the locale separators and the currency minor units', (language, currency, expected) => {
  expect(createCurrencyFormatter({ language, currency: 'GBP' })(1234.5, { currency })).toBe(expected)
})

it('keeps the three minor units of a currency stored before the precision rule', () => {
  expect(createCurrencyFormatter({ language: 'en', currency: 'GBP' })(1234.5, { currency: 'KWD' })).toBe(`KWD${NO_BREAK_SPACE}1,234.500`)
})

it('lets explicit decimals win over the currency minor units', () => {
  const format = createCurrencyFormatter({ language: 'en', currency: 'EUR' })
  expect(format(0.1234, { decimals: 3 })).toBe('€0.123')
  expect(format(12.6, { decimals: 0 })).toBe('€13')
  expect(format(12.3, { currency: 'JPY', decimals: UNIT_PRICE_FRACTION_DIGITS })).toBe('JP¥12.30')
  expect(format(612.9, { currency: 'HUF', decimals: UNIT_PRICE_FRACTION_DIGITS })).toBe(`HUF${NO_BREAK_SPACE}612.90`)
})

it('uses the bound currency only when the key is omitted and never relabels a present one', () => {
  const format = createCurrencyFormatter({ language: 'en', currency: 'GBP', unknownCurrencyLabel: UNKNOWN_LABEL })
  expect(format(5)).toBe('£5.00')
  expect(format(5, { decimals: 0 })).toBe('£5')
  for (const currency of [undefined, null, '']) expect(format(5, { currency })).toBe(`5.00 ${UNKNOWN_LABEL}`)
  expect(format(5, { currency: '£' })).toBe('5.00 £')
  expect(() => format(5, 'EUR')).toThrow(TypeError)
})

it('treats a missing amount as zero, accepts API decimal strings and falls back to British English', () => {
  const format = createCurrencyFormatter({ language: 'de', currency: 'GBP' })
  expect(format(null)).toBe('£0.00')
  expect(format('12.50')).toBe('£12.50')
})

function Probe() {
  const { formatCurrency } = useCurrency()
  return <p>{`${formatCurrency(5)} | ${formatCurrency(1234.5, { currency: 'GBP' })} | ${formatCurrency(5, { currency: null })}`}</p>
}

it('binds the active language, the active currency and the localized unknown label', async () => {
  localStorage.setItem('language', 'ro')
  render(<LanguageProvider><Probe /></LanguageProvider>)
  expect(await screen.findByText(`5,00 RON | 1.234,50 GBP | 5,00 ${translations.ro.financial.unknownCurrency}`)).toBeTruthy()
})

it('shows each timeline row in its stored currency, not the active one', async () => {
  vehicleApi.getById.mockResolvedValue({ data: { id: 1, name: 'Timeline car' } })
  vehicleApi.getTimeline.mockResolvedValue({ data: {
    entries: [{ id: 1, type: 'fuel', title: 'Fill', cost: 50, currency: 'EUR', date: '2026-01-02' }],
    insurance: [{ id: 2, type: 'insurance', title: 'Policy', cost: 100, currency: 'USD', date: '2026-01-01' }],
    total: 2, has_next: false,
  } })
  render(<LanguageProvider><MemoryRouter initialEntries={['/vehicles/1/timeline']}><Routes>
    <Route path="/vehicles/:id/timeline" element={<VehicleTimeline />} />
  </Routes></MemoryRouter></LanguageProvider>)
  expect(await screen.findByText('€50.00')).toBeTruthy()
  expect(screen.getByText('US$100.00')).toBeTruthy()
  expect(screen.queryByText('£50.00')).toBeNull()
  expect(screen.queryByText('£100.00')).toBeNull()
})

it('shows a consumable in its stored currency, not the active one', async () => {
  vehicleApi.getById.mockResolvedValue({ data: { id: 1, name: 'Consumables car', distance_unit: 'km' } })
  consumableApi.getByVehicle.mockResolvedValue({ data: { entries: [
    { id: 3, consumable_type: 'wipers', amount: 30, currency: 'EUR', date: '2026-01-03', quantity: 1 },
  ] } })
  render(<LanguageProvider><MemoryRouter initialEntries={['/vehicles/1/consumables']}><Routes>
    <Route path="/vehicles/:id/consumables" element={<VehicleConsumables />} />
  </Routes></MemoryRouter></LanguageProvider>)
  expect(await screen.findByText('€30.00')).toBeTruthy()
  expect(screen.queryByText('£30.00')).toBeNull()
})

it.each(['en', 'ro', 'es'])('explains the refused currency precision in %s', language => {
  expect(translations[language].validation.unsupportedCurrencyPrecision).toMatch(/\S/)
})
