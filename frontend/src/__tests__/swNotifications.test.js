/**
 * Unit tests for the push-notification decisions extracted from sw.js (R4-28).
 *
 * Both defects were silent: a non-JSON push threw inside the handler and the
 * notification never appeared, and the focus comparison never matched so every
 * click opened another tab. Neither would surface in a build or a lint.
 */
import { describe, it, expect, vi } from 'vitest'

import { findClientToFocus, parsePushData } from '../swNotifications'

function jsonData(payload) {
  return { json: () => payload, text: () => JSON.stringify(payload) }
}

function textData(text) {
  return {
    json: () => { throw new SyntaxError('Unexpected token') },
    text: () => text,
  }
}

describe('parsePushData', () => {
  it('reads a JSON payload', () => {
    expect(parsePushData(jsonData({ title: 'Service due', body: 'MOT' })))
      .toEqual({ title: 'Service due', body: 'MOT' })
  })

  it('falls back to the raw text when the payload is not JSON', () => {
    expect(parsePushData(textData('Your MOT is due'))).toEqual({ body: 'Your MOT is due' })
  })

  it('returns an empty payload when there is no data at all', () => {
    expect(parsePushData(null)).toEqual({})
    expect(parsePushData(undefined)).toEqual({})
  })

  it('survives a payload that can be neither parsed nor read', () => {
    const hostile = {
      json: () => { throw new Error('nope') },
      text: () => { throw new Error('nope either') },
    }

    expect(parsePushData(hostile)).toEqual({})
  })

  it('never throws, whatever the push contains', () => {
    for (const data of [jsonData(null), textData(''), {}]) {
      expect(() => parsePushData(data)).not.toThrow()
    }
  })
})

describe('findClientToFocus', () => {
  const focusable = (url) => ({ url, focus: vi.fn() })

  it('matches an absolute client URL against the notification path', () => {
    const client = focusable('https://gearcargo.example.com/reminders')

    // Was: client.url === '/reminders' — never true, so a duplicate tab opened.
    expect(findClientToFocus([client], '/reminders')).toBe(client)
  })

  it('ignores the query string and hash of the open tab', () => {
    const client = focusable('https://gearcargo.example.com/reminders?filter=due#top')

    expect(findClientToFocus([client], '/reminders')).toBe(client)
  })

  it('does not match a different page', () => {
    const client = focusable('https://gearcargo.example.com/vehicles')

    expect(findClientToFocus([client], '/reminders')).toBeNull()
  })

  it('returns the first focusable match', () => {
    const stale = { url: 'https://gearcargo.example.com/reminders' }   // no focus()
    const usable = focusable('https://gearcargo.example.com/reminders')

    expect(findClientToFocus([stale, usable], '/reminders')).toBe(usable)
  })

  it('handles an empty or missing client list', () => {
    expect(findClientToFocus([], '/reminders')).toBeNull()
    expect(findClientToFocus(undefined, '/reminders')).toBeNull()
  })

  it('skips a client whose url cannot be parsed instead of throwing', () => {
    const broken = { url: undefined, focus: vi.fn() }
    const usable = focusable('https://gearcargo.example.com/reminders')

    expect(findClientToFocus([broken, usable], '/reminders')).toBe(usable)
  })
})
