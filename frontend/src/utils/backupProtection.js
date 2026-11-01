export function protectionOptions(enabled, passphrase, confirmation, t, stored = false) {
  if (!enabled) return { encrypt: false }
  if (stored && !passphrase && !confirmation) return { encrypt: true }
  if (passphrase.length < 12 || passphrase.length > 1024) throw new Error(t('backup.protection.keyLength'))
  if (passphrase !== confirmation) throw new Error(t('backup.protection.keyMismatch'))
  return { encrypt: true, passphrase }
}

