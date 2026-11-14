import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import toast from 'react-hot-toast'
import CurrencyReviewPrompt from '../components/vehicles/CurrencyReviewPrompt'
import { supportedLanguages, translations } from '../i18n/translations'
import { vehicleApi } from '../services/api'

const { confirm } = vi.hoisted(() => ({ confirm: vi.fn() }))

vi.mock('../services/api', () => ({
  vehicleApi: { getCurrencyReview: vi.fn(), resolveCurrencyReview: vi.fn() },
}))
vi.mock('../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key, params = {}) => {
      const text = key.split('.').reduce((node, part) => node?.[part], translations.en)
      if (typeof text !== 'string') throw new Error(`Missing translation: ${key}`)
      return Object.entries(params).reduce((result, [name, value]) => result.replaceAll(`{${name}}`, value), text)
    },
  }),
}))
vi.mock('../hooks/useDateFormat', () => ({ useDateFormat: () => ({ formatDate: value => `on ${value}` }) }))
vi.mock('../components/ui/ConfirmDialog', () => ({ useConfirm: () => confirm }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const EUR_GROUP = { currency: 'EUR', count: 24, first_date: '2026-01-10', last_date: '2026-07-26' }
const USD_GROUP = { currency: 'USD', count: 1, first_date: '2026-02-01', last_date: '2026-02-01' }
const review = groups => ({ data: { account_currency: 'GBP', groups } })
const onRelabelled = vi.fn()

function renderPrompt() {
  return render(<CurrencyReviewPrompt onRelabelled={onRelabelled} />)
}

beforeEach(() => {
  vi.clearAllMocks()
  vehicleApi.getCurrencyReview.mockResolvedValue(review([EUR_GROUP, USD_GROUP]))
  confirm.mockResolvedValue(true)
})
afterEach(cleanup)

describe('currency review prompt', () => {
  it('names the built-in label, the count, the dates and the person\'s own currency', async () => {
    renderPrompt()

    expect(await screen.findByText(/Older records marked EUR: 24\. Your currency is GBP\./)).toBeTruthy()
    expect(screen.getByText('Dated on 2026-01-10 to on 2026-07-26.')).toBeTruthy()
    expect(screen.getByText(/Older records marked USD: 1\./)).toBeTruthy()
    expect(screen.getAllByRole('button', { name: 'Mark them as GBP' })).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'They are in EUR' })).toBeTruthy()
  })

  it.each([
    ['there is nothing to review', () => vehicleApi.getCurrencyReview.mockResolvedValue(review([]))],
    ['the check fails', () => vehicleApi.getCurrencyReview.mockRejectedValue(new Error('offline'))],
  ])('stays out of the way when %s', async (_case, arrange) => {
    arrange()
    const { container } = renderPrompt()

    await waitFor(() => expect(vehicleApi.getCurrencyReview).toHaveBeenCalledOnce())
    expect(container.textContent).toBe('')
  })

  it('relabels a group only after the person confirms that amounts stay as entered', async () => {
    vehicleApi.resolveCurrencyReview.mockResolvedValue({ data: { account_currency: 'GBP', groups: [USD_GROUP], relabelled: 24 } })
    renderPrompt()

    fireEvent.click((await screen.findAllByRole('button', { name: 'Mark them as GBP' }))[0])

    await waitFor(() => expect(vehicleApi.resolveCurrencyReview).toHaveBeenCalledWith('EUR', 'relabel'))
    expect(confirm).toHaveBeenCalledWith({
      title: 'Mark these records as GBP?',
      message: translations.en.currencyReview.confirmMessage,
      confirmLabel: 'Mark them as GBP',
    })
    await waitFor(() => expect(screen.queryByText(/Older records marked EUR/)).toBeNull())
    expect(screen.getByText(/Older records marked USD/)).toBeTruthy()
    expect(toast.success).toHaveBeenCalledWith('Records now marked GBP: 24.')
    expect(onRelabelled).toHaveBeenCalledOnce()
  })

  it('changes nothing when the confirmation is declined', async () => {
    confirm.mockResolvedValue(false)
    renderPrompt()

    fireEvent.click((await screen.findAllByRole('button', { name: 'Mark them as GBP' }))[0])

    await waitFor(() => expect(confirm).toHaveBeenCalledOnce())
    expect(vehicleApi.resolveCurrencyReview).not.toHaveBeenCalled()
    expect(screen.getByText(/Older records marked EUR/)).toBeTruthy()
  })

  it('keeps a group as recorded without a confirmation and without reloading the page data', async () => {
    vehicleApi.resolveCurrencyReview.mockResolvedValue({ data: { account_currency: 'GBP', groups: [USD_GROUP], relabelled: 0 } })
    renderPrompt()

    fireEvent.click(await screen.findByRole('button', { name: 'They are in EUR' }))

    await waitFor(() => expect(vehicleApi.resolveCurrencyReview).toHaveBeenCalledWith('EUR', 'keep'))
    await waitFor(() => expect(screen.queryByText(/Older records marked EUR/)).toBeNull())
    expect(confirm).not.toHaveBeenCalled()
    expect(toast.success).not.toHaveBeenCalled()
    expect(onRelabelled).not.toHaveBeenCalled()
  })

  it('explains a refusal in the app language and leaves the prompt usable', async () => {
    vehicleApi.resolveCurrencyReview.mockRejectedValue({
      response: { data: { error: 'English server text', message_key: 'currencyReview.nothingToReview' } },
    })
    renderPrompt()

    fireEvent.click((await screen.findAllByRole('button', { name: 'Mark them as GBP' }))[0])

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(translations.en.currencyReview.nothingToReview))
    expect(screen.getByText(/Older records marked EUR/)).toBeTruthy()
    await waitFor(() => expect(screen.getByRole('button', { name: 'They are in EUR' }).disabled).toBe(false))
    expect(onRelabelled).not.toHaveBeenCalled()
  })

  it('keeps the same placeholders in every language', () => {
    const placeholders = text => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort()
    for (const language of supportedLanguages) {
      for (const [key, english] of Object.entries(translations.en.currencyReview)) {
        expect(placeholders(translations[language].currencyReview[key]), `${language}.${key}`).toEqual(placeholders(english))
      }
    }
  })
})
