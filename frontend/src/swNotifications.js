/**
 * GearCargo - Push notification helpers (extracted from sw.js for testing).
 *
 * Same arrangement as swSync.js: the service worker keeps the event wiring,
 * the decisions live here where they can be unit-tested without a
 * ServiceWorkerGlobalScope.
 */

/**
 * Read a push message's payload.
 *
 * R4-28: `event.data.json()` was called unguarded, so a push whose body is not
 * JSON threw inside the `push` handler and the notification was dropped
 * silently — the user simply never saw it. A non-JSON body is far more likely
 * to be a plain-text message than nothing at all, so it becomes the body.
 */
export function parsePushData(eventData) {
  if (!eventData) return {}
  try {
    return eventData.json() || {}
  } catch {
    try {
      return { body: eventData.text() }
    } catch {
      return {}
    }
  }
}

/**
 * Find an already-open window showing `urlToOpen`, or null.
 *
 * R4-28: the comparison was `client.url === urlToOpen`, an absolute URL against
 * a path ('https://host/reminders' vs '/reminders'), so it never matched and
 * every notification click opened a duplicate tab. Compares pathnames, and
 * ignores a client whose url cannot be parsed rather than throwing inside the
 * click handler.
 */
export function findClientToFocus(clientList, urlToOpen) {
  const targetPath = pathnameOf(urlToOpen)
  if (targetPath === null) return null

  for (const client of clientList || []) {
    if (typeof client?.focus !== 'function') continue
    if (pathnameOf(client.url) === targetPath) return client
  }
  return null
}

function pathnameOf(url) {
  if (!url) return null
  try {
    // A relative path needs a base; the origin is irrelevant to the comparison
    // because both sides are normalised through the same one.
    return new URL(url, 'https://gearcargo.invalid').pathname
  } catch {
    return null
  }
}
