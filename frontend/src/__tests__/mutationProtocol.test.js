import { renderHook, act } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { useMutationIntent } from '../hooks/useMutationIntent'
import { mutationTarget } from '../utils/mutationProtocol'

describe('form mutation intent', () => {
  it('keeps one ID across response loss, resubmit and rerender', () => {
    const { result, rerender } = renderHook(() => useMutationIntent())
    const original = result.current.options()
    rerender()
    expect(result.current.options()).toEqual(original)
    expect(original.headers['If-Match']).toBeUndefined()
  })
  it('keeps the displayed revision in each editor until explicitly reloaded', () => {
    const first = renderHook(() => useMutationIntent())
    const second = renderHook(() => useMutationIntent())
    act(() => { first.result.current.capture({ revision: 123 }); second.result.current.capture({ revision: 123 }) })
    const stale = second.result.current.options()
    act(() => first.result.current.capture({ revision: 124 }))
    expect(first.result.current.options().headers['If-Match']).toBe('"124"')
    expect(second.result.current.options()).toEqual(stale)
    expect(stale.headers['If-Match']).toBe('"123"')
  })
})

it('only applies the protocol to supported write endpoints', () => {
  const origin = 'https://example.test'
  for (const path of ['/api/fuel/3', '/api/attachments/3']) {
    expect(mutationTarget(new URL(path, origin), 'PUT', origin).id).toBe('3')
  }
  expect(mutationTarget(new URL('/api/reminders/3/complete', origin), 'POST', origin).id).toBe('3')
  for (const path of ['/api/auth/login', '/api/vehicles/3?hard=true', '/api/vehicles/3/photo', '/api/backup/import']) {
    expect(mutationTarget(new URL(path, origin), 'POST', origin)).toBeNull()
  }
})
