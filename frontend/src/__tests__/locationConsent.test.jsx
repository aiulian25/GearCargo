import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { translations } from '../i18n/translations'
import { useTranslation } from '../contexts/LanguageContext'
import { useUserLocation } from '../hooks/useUserLocation'
import { countryName } from '../utils/countryName'
import LocationPrimingModal from '../components/PWA/LocationPrimingModal'
import PrivacyPolicy from '../components/settings/PrivacyPolicy'
import Dashboard from '../pages/Dashboard'
import {
  FALLBACK_LOCATION, GEOLOCATION_OPTIONS, LOCATION_CACHE_STORAGE_KEY, LOCATION_CONSENT_DEFER_MS,
  LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY, LOCATION_CONSENT_GRANTED, LOCATION_CONSENT_STORAGE_KEY,
  LOCATION_SETTINGS_PATH, MANUAL_LOCATION_STATE_KEY,
} from '../config/location'

// Stable across renders, like the real contexts: the Dashboard's effects depend on them.
const { identity, locale, auth, currency } = vi.hoisted(() => ({
  identity: { owner_id: 7, owner_key: 'a'.repeat(64), generation: 'b'.repeat(64) },
  locale: { language: 'en' },
  auth: { user: { location_auto_detect: true } },
  currency: { setCurrencyFromCountry: () => {}, formatCurrency: String },
}))

vi.mock('../contexts/LanguageContext', () => {
  const t = key => {
    const value = key.split('.').reduce((object, part) => object?.[part], translations[locale.language])
    if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
    return value
  }
  return { useTranslation: () => ({ language: locale.language, t }), useCurrency: () => currency }
})
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))
vi.mock('../services/api', () => {
  const answer = data => () => Promise.resolve({ data })
  return {
    vehicleApi: { getAll: answer({ vehicles: [] }), getRecentTransactions: answer({ transactions: [] }) },
    externalApi: { getFuelPrices: answer({ location: 'United Kingdom', country: 'UK', prices: {} }), history: answer({ points: [] }) },
    insuranceApi: { getActive: answer({ policies: [] }), getExpiring: answer({ policies: [] }) },
    configApi: { get: answer({}) },
    dueApi: { get: answer({ items: [] }) },
  }
})
vi.mock('../utils/offlineIdentity', () => ({
  getBoundIdentity: () => identity,
  requireCurrentIdentity: async () => identity,
}))

const AUTO_DETECT_USER = { location_auto_detect: true }
const NO_SAVED_LOCATION_USER = { location_auto_detect: false }
const SAVED_LOCATION_USER = { location_auto_detect: false, location_lat: 44.43, location_lon: 26.1, location_name: 'Bucharest' }
// Stands in for the fuel widget's "Use my location" button.
const ASK_AGAIN = 'ask again'
const THIRD_PARTY_KEYS = [
  'thirdPartyDesc', 'thirdPartyLocation', 'thirdPartyFuelPrices', 'thirdPartyExchangeRates',
  'thirdPartyPasswordCheck', 'thirdPartyManuals', 'thirdPartyFonts', 'noThirdPartyItem2',
]
const NAMED_SERVICES = ['OpenStreetMap Nominatim', 'GOV.UK', 'Frankfurter', 'Have I Been Pwned', 'Google Fonts']
const getCurrentPosition = vi.fn()

function ShownRoute() {
  const { pathname, hash, state } = useLocation()
  return <output data-testid="route">{JSON.stringify({ path: `${pathname}${hash}`, state })}</output>
}

function Harness({ user }) {
  const { t } = useTranslation()
  const { userLocation, locationUnavailable, consentPending, allowLocation, deferLocation, askForLocation } = useUserLocation(user)
  return (
    <MemoryRouter>
      <LocationPrimingModal isOpen={consentPending} onConfirm={allowLocation} onClose={deferLocation} />
      {askForLocation && <button type="button" onClick={askForLocation}>{ASK_AGAIN}</button>}
      {locationUnavailable && <p>{t('locationConsent.unavailable')}</p>}
      <output data-testid="location">{JSON.stringify(userLocation)}</output>
      <ShownRoute />
    </MemoryRouter>
  )
}

const shownLocation = () => JSON.parse(screen.getByTestId('location').textContent)
const shownRoute = () => JSON.parse(screen.getByTestId('route').textContent)
const consentCopy = () => translations[locale.language].locationConsent
const renderDashboard = () => render(<MemoryRouter><Dashboard /></MemoryRouter>)

beforeEach(() => {
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
  Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition }, configurable: true })
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.restoreAllMocks()
  localStorage.clear()
  locale.language = 'en'
})

it('asks first, starts focus on the dialog and reads nothing until "Use my location"', async () => {
  render(<Harness user={AUTO_DETECT_USER} />)
  const dialog = screen.getByRole('dialog', { name: consentCopy().title })
  expect(dialog.textContent).toContain(consentCopy().description)
  expect(document.activeElement).toBe(dialog)
  expect(getCurrentPosition).not.toHaveBeenCalled()
  expect(shownLocation()).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: consentCopy().allow }))

  expect(getCurrentPosition).toHaveBeenCalledTimes(1)
  expect(getCurrentPosition).toHaveBeenCalledWith(expect.any(Function), expect.any(Function), GEOLOCATION_OPTIONS)
  expect(GEOLOCATION_OPTIONS.enableHighAccuracy).toBe(false)
  expect(localStorage.getItem(LOCATION_CONSENT_STORAGE_KEY)).toBe(LOCATION_CONSENT_GRANTED)
  expect(screen.queryByRole('dialog')).toBeNull()

  const [succeed] = getCurrentPosition.mock.calls[0]
  await act(() => succeed({ coords: { latitude: 51.51, longitude: -0.13 } }))
  expect(shownLocation()).toEqual({ lat: 51.51, lon: -0.13 })
  expect(JSON.parse(localStorage.getItem(LOCATION_CACHE_STORAGE_KEY))).toMatchObject({ lat: 51.51, lon: -0.13, identity })
})

it.each(['en', 'ro', 'es'])('remembers the agreement on this device and says so when the browser refuses (%s)', language => {
  locale.language = language
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  localStorage.setItem(LOCATION_CONSENT_STORAGE_KEY, LOCATION_CONSENT_GRANTED)
  render(<Harness user={AUTO_DETECT_USER} />)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(getCurrentPosition).toHaveBeenCalledTimes(1)
  expect(screen.queryByText(consentCopy().unavailable)).toBeNull()

  const [, fail] = getCurrentPosition.mock.calls[0]
  act(() => fail({ code: 1 }))
  expect(shownLocation()).toEqual(FALLBACK_LOCATION)
  expect(screen.getByText(consentCopy().unavailable)).toBeTruthy()
  expect(screen.queryByRole('button', { name: ASK_AGAIN })).toBeNull()
})

it('reuses a fresh cached position without reading the device again', () => {
  localStorage.setItem(LOCATION_CONSENT_STORAGE_KEY, LOCATION_CONSENT_GRANTED)
  localStorage.setItem(LOCATION_CACHE_STORAGE_KEY, JSON.stringify({ lat: 1, lon: 2, identity, timestamp: Date.now() }))
  render(<Harness user={AUTO_DETECT_USER} />)
  expect(shownLocation()).toEqual({ lat: 1, lon: 2 })
  expect(getCurrentPosition).not.toHaveBeenCalled()
})

it.each(['button', 'Escape', 'backdrop'])('"Not now" by %s keeps the no-position fallback and is remembered', way => {
  const view = render(<Harness user={AUTO_DETECT_USER} />)
  const dialog = screen.getByRole('dialog')
  const decline = {
    button: () => fireEvent.click(screen.getByRole('button', { name: translations.en.pwa.notNow })),
    Escape: () => fireEvent.keyDown(document, { key: 'Escape' }),
    backdrop: () => fireEvent.click(dialog.parentElement),
  }
  decline[way]()

  expect(screen.queryByRole('dialog')).toBeNull()
  expect(shownLocation()).toEqual(FALLBACK_LOCATION)
  expect(Number(localStorage.getItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY))).toBeGreaterThan(0)
  view.unmount()
  render(<Harness user={AUTO_DETECT_USER} />)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(getCurrentPosition).not.toHaveBeenCalled()
})

it('a later "Not now" in another tab overrides an earlier "Use my location"', () => {
  render(<><Harness user={AUTO_DETECT_USER} /><Harness user={AUTO_DETECT_USER} /></>)
  const [firstTab, secondTab] = screen.getAllByRole('dialog')
  fireEvent.click(within(secondTab).getByRole('button', { name: consentCopy().allow }))
  fireEvent.click(within(firstTab).getByRole('button', { name: translations.en.pwa.notNow }))
  cleanup()
  getCurrentPosition.mockClear()

  render(<Harness user={AUTO_DETECT_USER} />)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(getCurrentPosition).not.toHaveBeenCalled()
})

it('keeps Tab inside the dialog and gives focus back to the button that reopened it', () => {
  localStorage.setItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY, String(Date.now()))
  render(<Harness user={AUTO_DETECT_USER} />)
  const trigger = screen.getByRole('button', { name: ASK_AGAIN })
  trigger.focus()
  fireEvent.click(trigger)

  const firstAction = screen.getByRole('link', { name: consentCopy().enterManually })
  const lastAction = screen.getByRole('button', { name: consentCopy().allow })
  const pressTab = shiftKey => fireEvent.keyDown(document.activeElement, { key: 'Tab', shiftKey })
  pressTab(true)
  expect(document.activeElement).toBe(lastAction)
  pressTab(false)
  expect(document.activeElement).toBe(firstAction)
  pressTab(true)
  expect(document.activeElement).toBe(lastAction)

  fireEvent.click(screen.getByRole('button', { name: translations.en.pwa.notNow }))
  expect(document.activeElement).toBe(trigger)
})

it('asks again once the seven-day deferral has passed', () => {
  localStorage.setItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY, String(Date.now() - LOCATION_CONSENT_DEFER_MS - 1))
  render(<Harness user={AUTO_DETECT_USER} />)
  expect(screen.getByRole('dialog', { name: consentCopy().title })).toBeTruthy()
})

it('"Use my location" during a deferral clears it and asks again before reading anything', () => {
  localStorage.setItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY, String(Date.now()))
  render(<Harness user={AUTO_DETECT_USER} />)
  expect(screen.queryByRole('dialog')).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: ASK_AGAIN }))

  expect(screen.getByRole('dialog', { name: consentCopy().title })).toBeTruthy()
  expect(localStorage.getItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY)).toBeNull()
  expect(getCurrentPosition).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: consentCopy().allow }))
  expect(getCurrentPosition).toHaveBeenCalledTimes(1)
})

it('moves focus to the fuel widget once its "Use my location" is confirmed and that button is gone', async () => {
  localStorage.setItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY, String(Date.now()))
  renderDashboard()
  const opener = await screen.findByRole('button', { name: consentCopy().allow })
  expect(screen.getByRole('status').contains(opener)).toBe(false)
  opener.focus()
  fireEvent.click(opener)

  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: consentCopy().allow }))

  expect(screen.queryByRole('dialog')).toBeNull()
  expect(opener.isConnected).toBe(false)
  expect(document.activeElement).toBe(screen.getByRole('heading', { name: translations.en.fuelPrices.title }))
})

it('announces a browser refusal in the fuel widget\'s live region, next to the place shown', async () => {
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  localStorage.setItem(LOCATION_CONSENT_STORAGE_KEY, LOCATION_CONSENT_GRANTED)
  renderDashboard()
  const liveRegion = await screen.findByRole('status')
  expect(liveRegion.getAttribute('aria-live')).toBe('polite')
  expect(within(liveRegion).queryByText(consentCopy().unavailable)).toBeNull()

  const [, fail] = getCurrentPosition.mock.calls[0]
  await act(async () => fail({ code: 1 }))

  expect(liveRegion.isConnected).toBe(true)
  expect(within(liveRegion).getByText(consentCopy().unavailable)).toBeTruthy()
  expect(await within(liveRegion).findByText(countryName('UK', 'en'))).toBeTruthy()
})

it('"Enter my location manually" opens the saved-location setting in manual mode and counts as "Not now"', () => {
  render(<Harness user={AUTO_DETECT_USER} />)
  const link = screen.getByRole('link', { name: consentCopy().enterManually })
  expect(link.getAttribute('href')).toBe(LOCATION_SETTINGS_PATH)

  fireEvent.click(link)

  expect(shownRoute()).toEqual({ path: LOCATION_SETTINGS_PATH, state: { [MANUAL_LOCATION_STATE_KEY]: true } })
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(localStorage.getItem(LOCATION_CONSENT_DEFERRED_AT_STORAGE_KEY)).not.toBeNull()
  expect(getCurrentPosition).not.toHaveBeenCalled()
})

it.each([
  ['no saved coordinates', NO_SAVED_LOCATION_USER, FALLBACK_LOCATION],
  ['saved coordinates', SAVED_LOCATION_USER, { lat: 44.43, lon: 26.1 }],
])('auto-detect off never asks or reads the position (%s)', (_case, user, expected) => {
  localStorage.setItem(LOCATION_CONSENT_STORAGE_KEY, LOCATION_CONSENT_GRANTED)
  render(<Harness user={user} />)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('button', { name: ASK_AGAIN })).toBeNull()
  expect(shownLocation()).toEqual(expected)
  expect(getCurrentPosition).not.toHaveBeenCalled()
})

it('never asks where the browser cannot locate', () => {
  Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true })
  render(<Harness user={AUTO_DETECT_USER} />)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('button', { name: ASK_AGAIN })).toBeNull()
  expect(shownLocation()).toEqual(FALLBACK_LOCATION)
})

// The fallback label must name the country whose prices are shown, in the app language.
it.each([
  ['en', 'UK', 'United Kingdom'],
  ['ro', 'UK', 'Regatul Unit'],
  ['es', 'RO', 'Rumanía'],
  ['en', 'ROU', undefined],
])('names the fallback country in the app language (%s, %s)', (language, country, expected) => {
  expect(countryName(country, language)).toBe(expected)
})

it.each(['en', 'ro', 'es'])('has complete location consent copy in %s', language => {
  locale.language = language
  render(<Harness user={AUTO_DETECT_USER} />)
  const dialog = screen.getByRole('dialog', { name: consentCopy().title })
  expect(dialog.textContent).toContain(consentCopy().description)
  expect(dialog.textContent).toContain(consentCopy().note)
  expect(screen.getByRole('button', { name: consentCopy().allow })).toBeTruthy()
  expect(screen.getByRole('button', { name: translations[language].pwa.notNow })).toBeTruthy()
  expect(screen.getByRole('link', { name: consentCopy().enterManually })).toBeTruthy()
})

it.each(['en', 'ro', 'es'])('names every third-party service in the %s privacy policy', language => {
  locale.language = language
  const privacy = translations[language].privacy
  render(<PrivacyPolicy isOpen onClose={() => {}} />)
  expect(screen.getByRole('heading', { name: privacy.thirdPartyTitle })).toBeTruthy()
  for (const key of THIRD_PARTY_KEYS) expect(screen.getByText(privacy[key])).toBeTruthy()
  const policyText = document.body.textContent
  for (const service of NAMED_SERVICES) expect(policyText).toContain(service)
})
