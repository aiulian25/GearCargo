import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { useTranslation } from '../../contexts/LanguageContext'
import { useDateFormat } from '../../hooks/useDateFormat'
import { vehicleApi } from '../../services/api'
import { serverMessage } from '../../utils/serverMessage'
import { useConfirm } from '../ui/ConfirmDialog'

const RELABEL_ACTION = 'relabel'
const KEEP_ACTION = 'keep'

/**
 * Older versions saved every expense as EUR and every policy as USD, whatever was paid. This
 * asks once per currency whether that label is right, and corrects it without converting amounts.
 */
export default function CurrencyReviewPrompt({ onRelabelled }) {
  const { t } = useTranslation()
  const { formatDate } = useDateFormat()
  const confirm = useConfirm()
  const [review, setReview] = useState(null)
  const [resolvingCurrency, setResolvingCurrency] = useState(null)

  useEffect(() => {
    let active = true
    // A failed check only hides the prompt; no record depends on it.
    vehicleApi.getCurrencyReview()
      .then((response) => { if (active) setReview(response.data) })
      .catch(() => {})
    return () => { active = false }
  }, [])

  if (!review?.groups?.length) return null

  const resolveGroup = async (group, action) => {
    const names = { currency: group.currency, account: review.account_currency }
    const confirmed = action === KEEP_ACTION || await confirm({
      title: t('currencyReview.confirmTitle', names),
      message: t('currencyReview.confirmMessage'),
      confirmLabel: t('currencyReview.relabel', names),
    })
    if (!confirmed) return

    setResolvingCurrency(group.currency)
    try {
      const { data } = await vehicleApi.resolveCurrencyReview(group.currency, action)
      setReview(data)
      if (action !== RELABEL_ACTION) return
      toast.success(t('currencyReview.relabelled', { account: data.account_currency, count: data.relabelled }))
      onRelabelled()
    } catch (requestError) {
      toast.error(serverMessage(requestError, t))
    } finally {
      setResolvingCurrency(null)
    }
  }

  return (
    <div className="mb-4 space-y-3">
      {review.groups.map((group) => {
        const names = { currency: group.currency, account: review.account_currency, count: group.count }
        const dates = { from: formatDate(group.first_date), to: formatDate(group.last_date) }
        return (
          <section
            key={group.currency}
            aria-label={t('currencyReview.title')}
            className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4"
          >
            <p className="text-sm">{t('currencyReview.message', names)}</p>
            <p className="text-xs text-(--color-text-secondary) mt-1">{t('currencyReview.dates', dates)}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-primary"
                disabled={resolvingCurrency !== null}
                onClick={() => resolveGroup(group, RELABEL_ACTION)}
              >
                {t('currencyReview.relabel', names)}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={resolvingCurrency !== null}
                onClick={() => resolveGroup(group, KEEP_ACTION)}
              >
                {t('currencyReview.keep', names)}
              </button>
            </div>
          </section>
        )
      })}
    </div>
  )
}
