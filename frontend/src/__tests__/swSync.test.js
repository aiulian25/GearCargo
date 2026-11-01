// @vitest-environment node
import { it, expect, vi } from 'vitest'
import { replayQueuedRequest } from '../swSync'
const entry = () => ({ request: new Request('https://example.test/api/fuel', { method: 'POST', body: '{}' }) })
it.each([[201, 'success'], [401, 'sign_in_required'], [403, 'sign_in_required'], [409, 'mutation_conflict'],
  [400, 'validation_failed'], [422, 'validation_failed'], [404, 'rejected'], [429, 'retry'], [500, 'retry'], [503, 'retry']])('classifies HTTP %s as %s without announcing a save', async (httpStatus, status) => {
  const notifyClients = vi.fn()
  const result = await replayQueuedRequest(entry(), { fetchFn: async () => new Response('{}', { status: httpStatus }), notifyClients })
  expect(result.status).toBe(status)
  expect(notifyClients).not.toHaveBeenCalled()
})
it('propagates transport failures to the durable queue', async () => {
  await expect(replayQueuedRequest(entry(), { fetchFn: async () => { throw new Error('offline') } })).rejects.toThrow('offline')
})
it('bounds Retry-After dates and numbers', async () => {
  const result = await replayQueuedRequest(entry(), { now: () => 1000000,
    fetchFn: async () => new Response('{}', { status: 429, headers: { 'Retry-After': '999999999' } }) })
  expect(result.retryAt).toBe(1000000 + 86400000)
})

it.each(['null', '<html>error</html>', '"failure"'])('retains validation responses with a non-object body: %s', async body => {
  const result = await replayQueuedRequest(entry(), { fetchFn: async () => new Response(body, { status: 422 }) })
  expect(result.status).toBe('validation_failed')
  expect(result.error).toEqual({ httpStatus: 422, code: null })
})
