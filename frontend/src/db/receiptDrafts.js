import { mutationDb } from './mutationQueue'

async function current(row, version = row.version) {
  const stored = await mutationDb.receipts.get(row.id)
  if (stored?.version !== version) throw new Error('This receipt changed. Refresh the list.')
}
export const receiptStore = {
  list: () => mutationDb.receipts.orderBy('createdAt').toArray(),
  version: async ownerKey => (await mutationDb.receipts.where('ownerKey').equals(ownerKey).toArray()).map(row => row.version).join(','),
  count: ownerKey => mutationDb.receipts.where('ownerKey').equals(ownerKey).count(),
  parentExists: async id => !!(await mutationDb.pending.get(id) || await mutationDb.quarantine.get(id)),
  save: (row, version) => mutationDb.transaction('rw', mutationDb.receipts, async () => { await current(row, version); await mutationDb.receipts.put(row) }),
  complete: row => mutationDb.transaction('rw', mutationDb.receipts, mutationDb.state, async () => {
    await current(row)
    await mutationDb.receipts.delete(row.id)
    await mutationDb.state.put({ key: `committed:${row.ownerKey}`, at: Date.now() })
  }),
  remove: row => mutationDb.transaction('rw', mutationDb.receipts, async () => { await current(row); await mutationDb.receipts.delete(row.id) }),
}
