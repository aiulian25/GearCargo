/**
 * Unit tests for useBackgroundSync's triggerSync (R4-16).
 *
 * The hook runs in the WINDOW, where `self === window` and `self.registration`
 * is undefined — so `'sync' in self.registration` threw
 * `TypeError: Cannot use 'in' operator`, which the catch turned into a
 * syncError and a `false` return. The FORCE_SYNC fallback below it was
 * unreachable, so neither the manual "Sync now" button nor the `online`
 * handler ever asked the service worker to replay a queued offline write.
 *
 * These lock both branches: a browser with Background Sync registers the
 * Workbox tag; one without it falls back to the FORCE_SYNC message.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { useBackgroundSync } from '../hooks/useBackgroundSync'

vi.mock('../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../utils/pwaSync', () => ({
  registerPeriodicReminderSync: vi.fn().mockResolvedValue(false),
}))

vi.mock('react-hot-toast', () => ({
  default: { error: vi.fn(), success: vi.fn() },
}))

const SYNC_TAG = 'workbox-background-sync:gearcargo-sync-queue'

/** A MessageChannel whose port1 immediately answers whatever the SW is asked. */
function stubMessageChannel(reply = { count: 0 }) {
  vi.stubGlobal('MessageChannel', class {
    constructor() {
      this.port1 = {}
      this.port2 = {}
      queueMicrotask(() => this.port1.onmessage?.({ data: reply }))
    }
  })
}

function stubServiceWorker({ registration, controller = {} } = {}) {
  const postMessage = vi.fn()
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: {
      controller: controller && { ...controller, postMessage },
      ready: Promise.resolve(registration),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    },
  })
  return postMessage
}

beforeEach(() => {
  stubMessageChannel()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  delete navigator.serviceWorker
})

describe('useBackgroundSync().triggerSync', () => {
  it('registers the Workbox sync tag on the ready registration', async () => {
    const register = vi.fn().mockResolvedValue(undefined)
    stubServiceWorker({ registration: { sync: { register } } })

    const { result } = renderHook(() => useBackgroundSync())

    let resolved
    await act(async () => {
      resolved = await result.current.triggerSync()
    })

    expect(resolved).toBe(true)              // was: false, via a TypeError
    expect(register).toHaveBeenCalledTimes(1)
    expect(register).toHaveBeenCalledWith(SYNC_TAG)
    expect(result.current.syncError).toBeNull()
    expect(result.current.lastSyncTime).toBeInstanceOf(Date)
  })

  it('falls back to the FORCE_SYNC message when Background Sync is unavailable', async () => {
    // Safari and Firefox: a registration with no `sync`.
    const postMessage = stubServiceWorker({ registration: {} })

    const { result } = renderHook(() => useBackgroundSync())

    let resolved
    await act(async () => {
      resolved = await result.current.triggerSync()
    })

    expect(resolved).toBe(true)
    expect(result.current.syncError).toBeNull()
    expect(postMessage).toHaveBeenCalledWith(
      { type: 'FORCE_SYNC' },
      expect.any(Array)
    )
  })

  it('still succeeds when the browser exposes no service worker at all', async () => {
    delete navigator.serviceWorker

    const { result } = renderHook(() => useBackgroundSync())

    let resolved
    await act(async () => {
      resolved = await result.current.triggerSync()
    })

    expect(resolved).toBe(true)
    expect(result.current.syncError).toBeNull()
  })

  it('reports a failing registration instead of claiming success', async () => {
    const register = vi.fn().mockRejectedValue(new Error('sync registration blocked'))
    stubServiceWorker({ registration: { sync: { register } } })

    const { result } = renderHook(() => useBackgroundSync())

    let resolved
    await act(async () => {
      resolved = await result.current.triggerSync()
    })

    expect(resolved).toBe(false)
    expect(result.current.syncError).toBe('sync registration blocked')
  })

  it('does nothing while offline', async () => {
    const register = vi.fn()
    stubServiceWorker({ registration: { sync: { register } } })
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)

    const { result } = renderHook(() => useBackgroundSync())

    let resolved
    await act(async () => {
      resolved = await result.current.triggerSync()
    })

    expect(resolved).toBe(false)
    expect(register).not.toHaveBeenCalled()
  })
})
