// Each form owns its intent and the revision it actually displayed. Never look
// up a newer revision immediately before saving: that would hide stale edits.
export function mutationOptions(record, key = crypto.randomUUID()) {
  const revision = typeof record === 'number' ? record : record?.revision
  return { headers: {
    'Idempotency-Key': key,
    'X-GearCargo-Mutation-Version': '1',
    ...(Number.isSafeInteger(revision) && revision > 0 ? { 'If-Match': `"${revision}"` } : {}),
  } }
}

export function mutationTarget(url, method, origin) {
  if (url.origin !== origin || url.search) return null
  const visit = url.pathname.match(/^\/api\/appointments(?:\/([1-9]\d*)(?:\/(confirm|cancel|dropoff|complete))?)?$/)
  if (visit) {
    const [, id, action] = visit
    return (action ? method === 'POST' : id ? method === 'PUT' : method === 'POST') ? { resource: 'appointments', id } : null
  }
  const tire = url.pathname.match(/^\/api\/tire-sets(?:\/([1-9]\d*)(?:\/(events|readings)(?:\/([1-9]\d*))?)?)?$/)
  if (tire) {
    const [, id, child, childId] = tire
    const allowed = childId ? (child === 'events' ? ['PUT', 'DELETE'] : ['DELETE'])
      : child ? ['POST'] : id ? ['PUT', 'DELETE'] : ['POST']
    return allowed.includes(method) ? { resource: 'tire-sets', id } : null
  }
  const match = url.pathname.match(/^\/api\/(vehicles|fuel|services|repairs|taxes|parking|insurance|consumables|todos|reminders|attachments)(?:\/([1-9]\d*)(?:\/(complete|incomplete|snooze|cancel|archive|unarchive|mileage))?)?$/)
  if (!match) return null
  const [, resource, id, action] = match
  const actions = { vehicles: ['archive', 'unarchive', 'mileage'], reminders: ['complete', 'snooze'], todos: ['complete', 'incomplete'], taxes: ['cancel'], parking: ['cancel'], insurance: ['cancel'] }
  if (action ? method !== 'POST' || !actions[resource]?.includes(action)
    : id ? !['PUT', 'PATCH', 'DELETE'].includes(method) : method !== 'POST') return null
  return { resource, id }
}

export function protocolHeaders(headers) {
  return Object.fromEntries(['Idempotency-Key', 'X-GearCargo-Mutation-Version', 'If-Match']
    .map(name => [name, headers.get(name)]).filter(([, value]) => value !== null))
}

export function validMutation(request) {
  const headers = request.headers
  return headers.get('X-GearCargo-Mutation-Version') === '1'
    && /^[A-Za-z0-9_-]{16,128}$/.test(headers.get('Idempotency-Key') || '')
    && (!/\/\d+(?:\/[^/]+)?$/.test(new URL(request.url).pathname)
      || /^"[1-9][0-9]{0,15}"$/.test(headers.get('If-Match') || ''))
}
