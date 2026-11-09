export function serverMessage(requestError, t) {
  const body = requestError?.response?.data
  return (body?.message_key && t(body.message_key)) || body?.error || t('common.errorOccurred')
}
