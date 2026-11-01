import { getBoundIdentity, requireCurrentIdentity, workerMessage } from './offlineIdentity'
import { receiptUploadKey } from './receiptProtocol'

// The worker commits parent JSON and the receipt Blob in one local transaction
// before either request is sent. Navigation is safe only after this reply.
export async function saveExpenseWithReceipt({ resource, editId, payload, config, file, attachmentId }) {
  const identity = getBoundIdentity()
  await requireCurrentIdentity(identity)
  const saved = await workerMessage('SAVE_RECEIPT_EXPENSE', { identity,
    parent: { path: `/api/${resource}${editId ? `/${editId}` : ''}`, method: editId ? 'PUT' : 'POST', payload, headers: config.headers },
    receipt: { blob: file || null, name: file?.name, uploadKey: file ? receiptUploadKey(file) : null, attachmentId },
  })
  if (!saved?.success) throw new Error('Reload online to enable receipt storage before saving this expense.')
  if (navigator.onLine) {
    // Failure/timeout here must not undo or conceal the successful local save.
    await workerMessage('FORCE_SYNC', { identity }).catch(() => null)
  }
  const receiptId = `${identity.owner_key}:${config.headers['Idempotency-Key']}`
  const status = await workerMessage('REVIEW_RECEIPTS', { identity, action: { type: 'list' } }).catch(() => null)
  return { receiptPending: !status || status.entries.some(row => row.id === receiptId) }
}
