import { beforeEach, describe, expect, it, vi } from 'vitest'
import toast from 'react-hot-toast'
import { notifyPendingCleanup } from '../utils/deletionFeedback'
import { translations } from '../i18n/translations'

vi.mock('react-hot-toast', () => ({ default: vi.fn() }))
beforeEach(() => vi.clearAllMocks())

describe('committed deletion with pending cleanup', () => {
  it.each(['en', 'ro', 'es'])('shows the pending outcome in %s', language => {
    const t = key => key.split('.').reduce((value, part) => value[part], translations[language])
    expect(notifyPendingCleanup({ data: { cleanup: { state: 'pending' } } }, t)).toBe(true)
    expect(toast).toHaveBeenCalledWith(translations[language].common.deletionCleanupPending,
      expect.objectContaining({ duration: 10000 }))
  })
  it('does not replace the normal success response for completed or older servers', () => {
    expect(notifyPendingCleanup({ data: { cleanup: { state: 'completed' } } })).toBe(false)
    expect(notifyPendingCleanup({ data: { message: 'Vehicle deleted' } })).toBe(false)
    expect(toast).not.toHaveBeenCalled()
  })
})
