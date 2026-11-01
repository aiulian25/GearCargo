export function appointmentTime(instant, timeZone, language = 'en') {
  if (!instant) return ''
  return new Intl.DateTimeFormat(language, { timeZone, year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }).format(new Date(instant))
}
