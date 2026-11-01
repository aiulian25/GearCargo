import { it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useBackgroundSync } from '../hooks/useBackgroundSync'
vi.mock('../utils/pwaSync', () => ({ registerPeriodicReminderSync: vi.fn().mockResolvedValue(false) }))
const replies = {}
let postMessage, close
const state = { count: 0, pausedCount: 0, legacyCount: 0, available: true, lastSyncTime: null }
beforeEach(() => {
  replies.GET_PENDING_SYNC_COUNT = state
  replies.FORCE_SYNC = { ...state, success: true, committedCount: 0 }
  close = vi.fn()
  vi.stubGlobal('MessageChannel', class {
    constructor() { this.port1 = { close }; this.port2 = { peer: this.port1 } }
  })
  postMessage = vi.fn((message, [port]) => { if (replies[message.type]) queueMicrotask(() => port.peer.onmessage({ data: replies[message.type] })) })
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: {
    controller: { postMessage }, ready: Promise.resolve({}), addEventListener: vi.fn(), removeEventListener: vi.fn(),
  } })
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); delete navigator.serviceWorker })
it('replays directly with no SyncManager, and empty success does not invent a timestamp', async () => {
  const { result } = renderHook(() => useBackgroundSync())
  let saved
  await act(async () => { saved = await result.current.triggerSync() })
  expect(saved).toBe(true)
  expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'FORCE_SYNC' }), expect.any(Array))
  expect(result.current.lastSyncTime).toBeNull()
  expect(close).toHaveBeenCalled()
})
it('also replays directly when SyncManager exists', async () => {
  const register = vi.fn()
  navigator.serviceWorker.ready = Promise.resolve({ sync: { register } })
  const { result } = renderHook(() => useBackgroundSync())
  await act(async () => { await result.current.triggerSync() })
  expect(register).not.toHaveBeenCalled()
  expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'FORCE_SYNC' }), expect.any(Array))
})
it('refuses an unsuccessful acknowledgement and retains recovery counts', async () => {
  replies.FORCE_SYNC = { success: false }
  replies.GET_PENDING_SYNC_COUNT = { ...state, pausedCount: 1 }
  const { result } = renderHook(() => useBackgroundSync())
  let saved
  await act(async () => { saved = await result.current.triggerSync() })
  expect(saved).toBe(false)
  expect(result.current.pausedCount).toBe(1)
  expect(result.current.lastSyncTime).toBeNull()
  expect(result.current.syncError).toContain('Review unsent')
})
it('does not claim success without a worker', async () => {
  delete navigator.serviceWorker
  const { result } = renderHook(() => useBackgroundSync())
  let saved
  await act(async () => { saved = await result.current.triggerSync() })
  expect(saved).toBe(false)
  expect(result.current.statusAvailable).toBe(false)
})
it('uses only a persisted commit timestamp, including after remount', async () => {
  replies.GET_PENDING_SYNC_COUNT = { ...state, lastSyncTime: 1700000000000 }
  const first = renderHook(() => useBackgroundSync())
  await act(async () => {})
  expect(first.result.current.lastSyncTime.getTime()).toBe(1700000000000)
  first.unmount()
  const next = renderHook(() => useBackgroundSync())
  await act(async () => {})
  expect(next.result.current.lastSyncTime.getTime()).toBe(1700000000000)
})
it('online event uses current connectivity even before React updates', async () => {
  let online = false
  vi.spyOn(navigator, 'onLine', 'get').mockImplementation(() => online)
  const { result } = renderHook(() => useBackgroundSync())
  await act(async () => { expect(await result.current.triggerSync()).toBe(false) })
  online = true
  await act(async () => window.dispatchEvent(new Event('online')))
  expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'FORCE_SYNC' }), expect.any(Array))
  expect(result.current.isOnline).toBe(true)
})
it('times out a missing acknowledgement and closes the message port', async () => {
  vi.useFakeTimers()
  replies.FORCE_SYNC = null
  const { result } = renderHook(() => useBackgroundSync())
  let work
  await act(async () => { work = result.current.triggerSync() })
  await act(async () => { await vi.advanceTimersByTimeAsync(15001) })
  expect(await work).toBe(false)
  expect(result.current.syncError).toContain('acknowledge')
  expect(close).toHaveBeenCalled()
})

it('refreshes persisted status as soon as the local sign-in is restored', async () => {
  const { result } = renderHook(() => useBackgroundSync())
  await act(async () => {})
  replies.GET_PENDING_SYNC_COUNT = { ...state, pausedCount: 2 }
  await act(async () => window.dispatchEvent(new Event('offline-identity-changed')))
  expect(result.current.pausedCount).toBe(2)
})
