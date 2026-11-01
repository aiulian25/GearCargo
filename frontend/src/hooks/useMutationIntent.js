import { useRef } from 'react'
import { mutationOptions } from '../utils/mutationProtocol'

export function useMutationIntent() {
  const intent = useRef(null)
  if (!intent.current) {
    let key = crypto.randomUUID()
    let revision
    intent.current = {
      capture(record) { revision = record.revision; key = crypto.randomUUID() },
      options() { return mutationOptions(revision, key) },
    }
  }
  return intent.current
}
