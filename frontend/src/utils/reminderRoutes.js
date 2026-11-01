// Existing notification URLs are a public compatibility contract.
export const REMINDER_ROUTE = 'reminders/:reminderId'
export function reminderPath(id) {
  return /^[1-9]\d*$/.test(String(id)) ? `/reminders/${id}` : null
}
export function reminderIdFromPath(path) {
  return /^\/reminders\/([1-9]\d*)\/?$/.exec(path || '')?.[1] || null
}
export function reminderAuthPath(page, id) {
  return reminderPath(id) ? `${page}?reminder=${id}` : page
}
export function reminderReturnPath(search) {
  return reminderPath(new URLSearchParams(search).get('reminder')) || '/'
}
