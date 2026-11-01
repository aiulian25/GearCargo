import { reminderAuthPath, reminderIdFromPath } from '../utils/reminderRoutes'
import axios from 'axios'
import toast from 'react-hot-toast'
import { getBoundIdentity, requireCurrentIdentity, beginIdentityTransition } from '../utils/offlineIdentity'
import { isOfflineWrite, identityHeaders } from '../utils/offlinePolicy'
import { mutationOptions, mutationTarget } from '../utils/mutationProtocol'
import { getQueueState } from '../db/mutationQueue'
import { getCsrfToken, needsCsrf } from '../utils/csrf'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  // S05 — tokens are now httpOnly cookies; withCredentials ensures the browser
  // includes cookies on every request (including cross-origin in dev mode where
  // Vite proxies /api to the backend on a different port).
  withCredentials: true,
})

// Capture the form's tab-local identity before transport. Retrying an old
// request must never relabel its contents with another tab's newer identity.
api.interceptors.request.use(async config => {
  const url = new URL(`${config.baseURL || '/api'}${config.url}`, window.location.origin)
  const target = mutationTarget(url, config.method.toUpperCase(), window.location.origin)
  if (target) {
    config.headers.set('Idempotency-Key', config.headers.get('Idempotency-Key') || crypto.randomUUID())
    config.headers.set('X-GearCargo-Mutation-Version', '1')
    if (target.id && !config.headers.get('If-Match')) {
      const error = new Error('Reload this record before saving. Its revision is unavailable.')
      error.response = { status: 428, data: { code: 'REVISION_REQUIRED', error: error.message } }
      throw error
    }
  }
  if (isOfflineWrite(url, config.method.toUpperCase(), window.location.origin) || config._receiptIdentity) {
    const identity = config._offlineIdentity || config._receiptIdentity || getBoundIdentity()
    await requireCurrentIdentity(identity)
    config._offlineIdentity = identity
    Object.assign(config.headers, identityHeaders(identity))
  }
  const revision = (await getQueueState()).revision
  if (config._privateRevision && config._privateRevision !== revision) throw new Error('Sign-in changed during this request.')
  config._privateRevision = revision
  if (needsCsrf(config.method)) {
    try {
      config.headers.set('X-CSRF-Token', await getCsrfToken())
    } catch (error) {
      // Let the worker durably save eligible writes during a network outage.
      // HTTP rejections and malformed token responses must still fail closed.
      if (!(error instanceof TypeError || error.name === 'TimeoutError') || !isOfflineWrite(url, config.method.toUpperCase(), window.location.origin)) throw error
      config.headers.delete('X-CSRF-Token')
    }
    if (revision !== (await getQueueState()).revision) throw new Error('Sign-in changed during this request.')
  }
  return config
})

// Single-flight token refresh (H4 companion). The server now ROTATES and
// REVOKES the previous session on every /auth/refresh, so the old refresh token
// is invalid the instant a new one is issued. When several requests 401 at once
// — e.g. a dashboard firing multiple API calls right as the 1-hour access token
// expires — each would otherwise call /auth/refresh independently; the first
// rotates, and the 2nd..Nth then present the just-revoked token and 401, forcing
// a spurious sign-out. Funnelling every refresh through ONE shared promise means
// exactly one rotation happens and all queued requests retry with the new token
// (also: one network round-trip instead of N).
let refreshPromise = null

function refreshSession(expectedRevision) {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      for (let attempt = 0; attempt < 2; attempt++) {
        const token = await getCsrfToken()
        if (expectedRevision && expectedRevision !== (await getQueueState()).revision) throw Object.assign(new Error('Sign-in changed during this request.'), { code: 'AUTH_CONTEXT_CHANGED' })
        try {
          return await axios.post('/api/auth/refresh', {}, { withCredentials: true, headers: { 'X-CSRF-Token': token } })
        } catch (error) {
          if (attempt || error.response?.status !== 403 || error.response?.data?.code !== 'CSRF_INVALID') throw error
        }
      }
    })().finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

// Pages where auth errors must NOT trigger a redirect/toast (you are already there).
const AUTH_PAGES = new Set(['/login', '/register', '/change-password'])
// Server codes meaning the session is definitively over — refreshing is futile.
const SESSION_ENDED_CODES = new Set(['SESSION_EXPIRED', 'SESSION_INVALID'])

// T2 (Step 25): the response-error logic is extracted here so the
// 401 → refresh → retry and session-expired → redirect paths can be unit-tested
// with injected deps. Behaviour is IDENTICAL to the previous inline interceptor;
// the interceptor below just wires the real window/localStorage/toast/axios
// implementations. Note: this service layer lives outside React, so it cannot
// call the i18n t(); it surfaces the backend's own (localized) `error` message
// and falls back to an English string only when the backend sends none.
export async function handleAuthError(error, deps) {
  const { getPath, clearAuth, notifyExpired, redirectSoon, redirectNow, refresh, retry } = deps
  const originalRequest = error.config
  const path = getPath()
  const isAuthPage = AUTH_PAGES.has(path)
  const loginPath = reminderAuthPath('/login', reminderIdFromPath(path))

  // Session definitively expired / invalid — no point refreshing.
  const errorCode = error.response?.data?.code
  if (SESSION_ENDED_CODES.has(errorCode)) {
    // Clear the local auth flag so ThemeContext / LanguageContext stop
    // attempting background sync (they check this flag, not the cookie).
    await clearAuth()
    if (!isAuthPage) {
      notifyExpired(error.response?.data?.error || 'Your session has expired. Please login again.')
      redirectSoon(loginPath)
    }
    return Promise.reject(error)
  }

  // 401 — try a silent token refresh; the browser sends the refresh_token
  // cookie automatically because withCredentials: true is set.
  if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
    if (isAuthPage) {
      if (originalRequest.url === '/auth/me') await clearAuth()
      return Promise.reject(error)
    }

    originalRequest._retry = true

    try {
      // Single-flight: concurrent 401s share ONE refresh so only one session
      // rotation happens server-side (H4). The httpOnly refresh_token cookie is
      // sent automatically; no localStorage read needed (S05).
      await refresh()

      // New access_token cookie is now set by the server.  Retry original request.
      return retry(originalRequest)
    } catch (refreshError) {
      const refreshErrorCode = refreshError.response?.data?.code
      if (refreshError.code === 'AUTH_CONTEXT_CHANGED' || refreshErrorCode?.startsWith('CSRF_')) return Promise.reject(refreshError)
      if (SESSION_ENDED_CODES.has(refreshErrorCode)) {
        await clearAuth()
        if (!isAuthPage) {
          notifyExpired(refreshError.response?.data?.error || 'Your session has expired. Please login again.')
          redirectSoon(loginPath)
        }
        return Promise.reject(refreshError)
      }

      // Refresh failed for any other reason — send user to login.
      await clearAuth()
      if (!isAuthPage) {
        redirectNow(loginPath)
      }
      return Promise.reject(refreshError)
    }
  }

  if (error.response?.status === 401 && originalRequest?._retry) await clearAuth()
  return Promise.reject(error)
}

// Response interceptor — transparent token refresh via cookie. Wires the real
// browser/axios dependencies into the testable handleAuthError above.
api.interceptors.response.use(
  async (response) => {
    if (response.config?._privateRevision && response.config._privateRevision !== (await getQueueState()).revision) throw new Error('Sign-in changed before the response arrived.')
    if (response.status === 202 && response.headers?.['x-gearcargo-queued'] === '1' && response.data?.code === 'OFFLINE_QUEUED') {
      return Promise.reject(Object.assign(new Error('Saved on this device; waiting to sync.'), { code: 'OFFLINE_QUEUED', response, config: response.config }))
    }
    return response
  },
  async (error) => {
    if (error.config?._privateRevision && error.config._privateRevision !== (await getQueueState()).revision) throw new Error('Sign-in changed before the response arrived.')
    if (error.response?.status === 403 && error.response?.data?.code === 'CSRF_INVALID' && error.config && !error.config._csrfRetry) {
      error.config._csrfRetry = true
      return api(error.config)
    }
    if (['REVISION_CONFLICT', 'OPERATION_KEY_REUSED'].includes(error.response?.data?.code)) {
      toast.error(error.response.data.error, { duration: 8000, id: 'mutation-conflict' })
    }
    return handleAuthError(error, {
      getPath: () => window.location.pathname,
      clearAuth: async () => {
        await beginIdentityTransition({ logout: true, expectedRevision: error.config?._privateRevision })
      },
      notifyExpired: (message) => toast.error(message, { duration: 4000, id: 'session-expired' }),
      redirectSoon: (url) => { setTimeout(() => { window.location.href = url }, 2000) },
      redirectNow: (url) => { window.location.href = url },
      refresh: () => refreshSession(error.config?._privateRevision),
      retry: (config) => api(config),
    })
  }
)

export default api

// API helper functions
export const vehicleApi = {
  getAll: () => api.get('/vehicles'),
  getArchived: () => api.get('/vehicles/archived'),
  get: (id) => api.get(`/vehicles/${id}`),
  getById: (id) => api.get(`/vehicles/${id}`),
  create: (data, config) => api.post('/vehicles', data, config),
  update: (id, data, config) => api.put(`/vehicles/${id}`, data, config),
  delete: (id, config) => api.delete(`/vehicles/${id}`, config),
  hardDelete: (id) => api.delete(`/vehicles/${id}?hard=true`),
  archive: (id, config) => api.post(`/vehicles/${id}/archive`, {}, config),
  unarchive: (id, config) => api.post(`/vehicles/${id}/unarchive`, {}, config),
  getStats: (id) => api.get(`/vehicles/${id}/stats`),
  getCostAnalytics: (id) => api.get(`/vehicles/${id}/cost-analytics`),
  getExpenseSummary: (id, filters) => api.get(`/vehicles/${id}/expenses-summary`, { params: filters }),
  getExpenseRecords: (id, filters) => api.get(`/vehicles/${id}/expense-records`, { params: filters }),
  // F11 — 12-month forward cost forecast (recurring + predictions vs budget)
  getForecast: (id, months = 12) => api.get(`/vehicles/${id}/forecast?months=${months}`),
  // F06 — natural-language vehicle chat (single-turn, AI/Ollama)
  chat: (id, question, locale) => api.post(`/vehicles/${id}/chat`, { question, locale }),
  // F10 — fleet-wide chat across all vehicles (no id)
  chatFleet: (question, locale) => api.post('/vehicles/chat', { question, locale }),
  getHealth: (id) => api.get(`/vehicles/${id}/health`),
  getWarranties: (id) => api.get(`/vehicles/${id}/warranties`),
  completeHealthAction: (id, data) => api.post(`/vehicles/${id}/health/actions/complete`, data),
  getManual: (id) => api.get(`/vehicles/${id}/manual`),
  getTimeline: (id, page = 1, type = 'all', perPage = 50) =>
    api.get(`/vehicles/${id}/timeline?page=${page}&type=${type}&per_page=${perPage}`),
  // Fleet-wide feed of the most recent cost-bearing transactions across all vehicles.
  getRecentTransactions: (limit = 5) => api.get(`/vehicles/recent-transactions?limit=${limit}`),
  reorder: (order) => api.post('/vehicles/reorder', { order }),
  updateMileage: (id, mileage, config) => api.post(`/vehicles/${id}/mileage`, { mileage }, config),
  uploadPhoto: (id, file) => {
    const formData = new FormData()
    formData.append('photo', file)
    return api.post(`/vehicles/${id}/photo`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  deletePhoto: (id) => api.delete(`/vehicles/${id}/photo`),
  suggestReminder: (id, locale = 'en-US') =>
    api.post(`/vehicles/${id}/suggest-reminder`, { locale }),
}

export const fuelApi = {
  getAll: (vehicleId = null, page = 1) => {
    const params = new URLSearchParams({ page })
    if (vehicleId) params.append('vehicle_id', vehicleId)
    return api.get(`/fuel?${params}`)
  },
  getByVehicle: (vehicleId, page = 1) => api.get(`/fuel?vehicle_id=${vehicleId}&page=${page}`),
  // F26 — per-station price insights from the user's own fills.
  getStations: (vehicleId) => api.get(vehicleId ? `/fuel/stations?vehicle_id=${vehicleId}` : '/fuel/stations'),
  get: (id) => api.get(`/fuel/${id}`),
  create: (data, config) => api.post('/fuel', data, config),
  update: (id, data, config) => api.put(`/fuel/${id}`, data, config),
  delete: (id, config) => api.delete(`/fuel/${id}`, config),
  getStats: (vehicleId = null) => {
    const params = vehicleId ? `?vehicle_id=${vehicleId}` : ''
    return api.get(`/fuel/stats${params}`)
  },
}

export const serviceApi = {
  getAll: (vehicleId = null, page = 1) => {
    const params = new URLSearchParams({ page })
    if (vehicleId) params.append('vehicle_id', vehicleId)
    return api.get(`/services?${params}`)
  },
  getByVehicle: (vehicleId, page = 1) => api.get(`/services?vehicle_id=${vehicleId}&page=${page}`),
  get: (id) => api.get(`/services/${id}`),
  create: (data, config) => api.post('/services', data, config),
  update: (id, data, config) => api.put(`/services/${id}`, data, config),
  delete: (id, config) => api.delete(`/services/${id}`, config),
}

export const repairApi = {
  getAll: (vehicleId = null, page = 1) => {
    const params = new URLSearchParams({ page })
    if (vehicleId) params.append('vehicle_id', vehicleId)
    return api.get(`/repairs?${params}`)
  },
  getByVehicle: (vehicleId, page = 1) => api.get(`/repairs?vehicle_id=${vehicleId}&page=${page}`),
  get: (id) => api.get(`/repairs/${id}`),
  create: (data, config) => api.post('/repairs', data, config),
  update: (id, data, config) => api.put(`/repairs/${id}`, data, config),
  delete: (id, config) => api.delete(`/repairs/${id}`, config),
}

export const reconciliationApi = {
  list: (page = 1) => api.get(`/reconciliation?page=${page}`),
  preview: data => api.post('/reconciliation/preview', data),
  create: (data, options) => api.post('/reconciliation', data, options),
  get: id => api.get(`/reconciliation/${id}`),
  candidates: (id, row, page, search) => api.get(`/reconciliation/${id}/rows/${row}/candidates`, { params: { page, search } }),
  match: (id, row, data, options) => api.put(`/reconciliation/${id}/rows/${row}`, data, options),
  complete: (id, options) => api.post(`/reconciliation/${id}/complete`, {}, options),
  delete: (id, options) => api.delete(`/reconciliation/${id}`, options),
  summary: id => api.get(`/reconciliation/${id}/summary.csv`, { responseType: 'blob' }),
}

export const appointmentApi = {
  list: vehicleId => api.get(`/appointments?vehicle_id=${vehicleId}`),
  work: vehicleId => api.get(`/appointments/work?vehicle_id=${vehicleId}`),
  create: (data, options) => api.post('/appointments', data, options),
  update: (id, data, options) => api.put(`/appointments/${id}`, data, options),
  action: (id, action, data, options) => api.post(`/appointments/${id}/${action}`, data, options),
}

export const tireApi = {
  list: (vehicleId) => api.get(`/tire-sets?vehicle_id=${vehicleId}`),
  get: (id) => api.get(`/tire-sets/${id}`),
  create: (data, config) => api.post('/tire-sets', data, config),
  update: (id, data, config) => api.put(`/tire-sets/${id}`, data, config),
  delete: (id, config) => api.delete(`/tire-sets/${id}`, config),
  event: (id, data, config) => api.post(`/tire-sets/${id}/events`, data, config),
  correctEvent: (id, eventId, data, config) => api.put(`/tire-sets/${id}/events/${eventId}`, data, config),
  undoEvent: (id, eventId, config) => api.delete(`/tire-sets/${id}/events/${eventId}`, config),
  reading: (id, data, config) => api.post(`/tire-sets/${id}/readings`, data, config),
  deleteReading: (id, readingId, config) => api.delete(`/tire-sets/${id}/readings/${readingId}`, config),
}

export const consumableApi = {
  getByVehicle: (vehicleId, page = 1) => api.get(`/consumables?vehicle_id=${vehicleId}&page=${page}`),
  getDue: () => api.get('/consumables/due'),
  get: (id) => api.get(`/consumables/${id}`),
  create: (data, config) => api.post('/consumables', data, config),
  update: (id, data, config) => api.put(`/consumables/${id}`, data, config),
  delete: (id, config) => api.delete(`/consumables/${id}`, config),
}

export const reminderApi = {
  getAll: (options = {}) => {
    const { vehicleId, status, page = 1 } = options
    const params = new URLSearchParams({ page })
    if (vehicleId) params.append('vehicle_id', vehicleId)
    if (status) params.append('status', status)
    return api.get(`/reminders?${params}`)
  },
  get: (id) => api.get(`/reminders/${id}`),
  create: (data, config) => api.post('/reminders', data, config),
  update: (id, data, config) => api.put(`/reminders/${id}`, data, config),
  delete: (id, config) => api.delete(`/reminders/${id}`, config),
  complete: (id, mileage = null, config) => api.post(`/reminders/${id}/complete`,
    mileage !== null && typeof mileage === 'object' ? mileage : { mileage }, config),
  snooze: (id, days, config) => api.post(`/reminders/${id}/snooze`, { days }, config),
  getOverdue: () => api.get('/reminders/overdue'),
  getStats: () => api.get('/reminders/stats'),
}

// F4 — unified "Due & Expiring" surface: one ranked feed across every source.
export const dueApi = {
  // F53 — omit days to follow the user's alert_days_before horizon server-side;
  // pass an explicit number to override.
  get: (days) => api.get(days != null ? `/due?days=${days}` : '/due'),
  // F40 — dismiss one occurrence of an item (reminders flip their native
  // dismissed flag; other kinds store an occurrence-scoped dismissal).
  dismiss: (kind, refId) => api.post('/due/dismiss', { kind, ref_id: refId }),
  undismiss: (kind, refId) => api.post('/due/undismiss', { kind, ref_id: refId }),
}

// F11 — fleet-wide 12-month cost forecast.
export const forecastApi = {
  getFleet: (months = 12) => api.get(`/forecast?months=${months}`),
}

export const parkingApi = {
  getByVehicle: (vehicleId, page = 1) => api.get(`/parking?vehicle_id=${vehicleId}&page=${page}`),
  update: (id, data, config) => api.put(`/parking/${id}`, data, config),
  // F34 — stop a recurring permit/subscription series (mirrors taxApi.cancel).
  cancel: (id, config) => api.post(`/parking/${id}/cancel`, {}, config),
  // F14 — outstanding parking fines (+ total_owed). status: pending|contested|paid, or omit for all outstanding.
  getFines: (status) => api.get(status ? `/parking/fines?status=${status}` : '/parking/fines'),
}

// Public, non-sensitive branding config (app + assistant name).
export const configApi = {
  get: () => api.get('/config'),
}

export const pushApi = {
  getVapidKey: () => api.get('/push/vapid-key'),
  subscribe: (subscription, deviceInfo = {}) => api.post('/push/subscribe', { subscription, ...deviceInfo }),
  unsubscribe: (endpoint) => api.post('/push/unsubscribe', { endpoint }),
  test: () => api.post('/push/test', {}),
  // F58 — read-only delivery history (push + email) for the current user.
  getHistory: (page = 1) => api.get('/push/history?page=' + page),
}

export const authApi = {
  login: (data) => api.post('/auth/login', data),
  register: (data) => api.post('/auth/register', data),
  logout: () => api.post('/auth/logout'),
  refresh: (refreshToken) => api.post('/auth/refresh', { refresh_token: refreshToken }),
  me: () => api.get('/auth/me'),
  updateProfile: (data) => api.put('/auth/me', data),
  changePassword: (data) => api.put('/auth/password', data),
  validatePassword: (password) => api.post('/auth/password/validate', { password }),
  
  // Password Reset
  requestPasswordReset: (email) => api.post('/auth/password-reset/request', { email }),
  verifyPasswordReset: (token, new_password) => api.post('/auth/password-reset/verify', { token, new_password }),
  
  // Email Verification
  sendVerificationEmail: () => api.post('/auth/email/send-verification', {}),
  verifyEmail: (token) => api.post('/auth/email/verify', { token }),
  resendVerificationEmail: (email) => api.post('/auth/email/resend-verification', { email }),

  // 2FA: TwoFactorSetup.jsx calls the real /auth/2fa/* endpoints directly.

  // Avatar
  getAvatars: () => api.get('/auth/avatars'),
  uploadAvatar: (file) => {
    const formData = new FormData()
    formData.append('avatar', file)
    return api.post('/auth/avatar', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  selectAvatar: (avatarUrl) => api.put('/auth/avatar/select', { avatar_url: avatarUrl }),
  deleteAvatar: (filename) => api.delete(`/auth/avatar/${filename}`),
  removeAvatar: () => api.delete('/auth/avatar'),
  
  // Email notifications
  getEmailSettings: () => api.get('/auth/email/settings'),
  sendTestEmail: () => api.post('/auth/email/test', {}),
  
  // GDPR Notification Email
  setNotificationEmail: (data) => api.post('/auth/notification-email', data),
  verifyNotificationEmail: (token) => api.post('/auth/notification-email/verify', { token }),
  removeNotificationEmail: () => api.delete('/auth/notification-email'),
  resendNotificationVerification: () => api.post('/auth/notification-email/resend', {}),
  getConsentHistory: () => api.get('/auth/consent-history'),
  
  // Security Questions
  getAvailableSecurityQuestions: () => api.get('/auth/security-questions/available'),
  getSecurityQuestions: () => api.get('/auth/security-questions'),
  setSecurityQuestions: (data) => api.post('/auth/security-questions', data),
  setSecurityQuestionsFirstTime: (data) => api.post('/auth/security-questions/first-time', data),
  getRecoveryQuestions: (email) => api.post('/auth/password/recover/questions', { email }),
  verifyRecoveryAnswers: (email, answers) => api.post('/auth/password/recover/verify-answers', { email, answers }),
  resetPasswordWithToken: (resetToken, newPassword, confirmPassword) => 
    api.post('/auth/password/recover/reset', { reset_token: resetToken, new_password: newPassword, confirm_password: confirmPassword }),
}

export const widgetApi = {
  getApiKey: () => api.get('/widget/api-key'),
  generateApiKey: () => api.post('/widget/api-key'),
  revokeApiKey: () => api.delete('/widget/api-key'),
}

export const backupApi = {
  getRecoveryStatus: () => api.get('/backup/recovery-status'),
  // Get backup status and available backups
  getStatus: () => api.get('/backup/status'),
  
  // Get backup statistics
  getStats: () => api.get('/backup/stats'),
  
  // Get backup history
  getHistory: (page = 1, perPage = 20) => api.get(`/backup/history?page=${page}&per_page=${perPage}`),
  
  // Export data (download)
  export: (format = 'zip', includeAttachments = true, saveToStorage = false, protection = {}) =>
    api.post('/backup/export', { format, include_attachments: includeAttachments, save_to_storage: saveToStorage, ...protection }, {
      responseType: format === 'zip' || protection.encrypt ? 'blob' : 'json'
    }),
  
  // Import data from file
  import: (formData) => api.post('/backup/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),

  // F01 — Export one entry type as CSV (blob download)
  exportCsv: (type, vehicleId = null) =>
    api.get('/backup/export/csv', {
      params: vehicleId ? { type, vehicle_id: vehicleId } : { type },
      responseType: 'blob',
    }),

  // F01 — Import entries from a CSV file (multipart: file, type, merge_mode)
  importCsv: (formData) => api.post('/backup/import/csv', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  
  // Restore from stored backup
  restoreFromStorage: (filename, mergeMode = 'merge', options = {}) =>
    api.post(`/backup/restore/${filename}`, { merge_mode: mergeMode, ...options }),
  
  // Download stored backup
  downloadStored: (filename) => api.get(`/backup/download/${filename}`, { responseType: 'blob' }),

  // Delete stored backup
  deleteBackup: (filename) => api.delete(`/backup/delete/${filename}`),
  
  // Get schedule settings
  getSchedule: () => api.get('/backup/schedule'),
  
  // Update schedule settings
  updateSchedule: (data) => api.put('/backup/schedule', data),
  
  // Run backup now
  runNow: (includeAttachments = true, sendExternal = false, protection = {}) =>
    api.post('/backup/run-now', { include_attachments: includeAttachments, send_external: sendExternal, ...protection }),

  // Send latest (or specific) backup to external server
  sendToExternal: (filename = null) =>
    api.post('/backup/send-external', { filename }),

  // Test external server connection
  testExternalConnection: (url, apiKey = '', path = '/GearCargo') => 
    api.post('/backup/external/test', { url, api_key: apiKey, path }),

  // Browse external server folders (WebDAV)
  browseExternalFolders: (url, apiKey, path = '/') =>
    api.post('/backup/external/browse', { url, api_key: apiKey, path }),

  // Browse external server files (WebDAV) - for restore
  browseExternalFiles: (url, apiKey, path = '/GearCargo') =>
    api.post('/backup/external/files', { url, api_key: apiKey, path }),

  // Restore from external server file
  restoreFromExternal: (filename, url = null, apiKey = null, path = null, mergeMode = 'merge', options = {}) =>
    api.post('/backup/external/restore', { filename, url, api_key: apiKey, path, merge_mode: mergeMode, ...options }),

  // Upload a backup .zip file to stored backups
  uploadBackup: (formData) => api.post('/backup/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  
  // Import from LubeLogger backup
  importLubelog: (formData) => api.post('/backup/import/lubelog', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
}

export const taxApi = {
  getAll: (vehicleId = null, page = 1) => {
    const params = new URLSearchParams({ page })
    if (vehicleId) params.append('vehicle_id', vehicleId)
    return api.get(`/taxes?${params}`)
  },
  get: (id) => api.get(`/taxes/${id}`),
  create: (data, config) => api.post('/taxes', data, config),
  update: (id, data, config) => api.put(`/taxes/${id}`, data, config),
  delete: (id, config) => api.delete(`/taxes/${id}`, config),
  cancel: (id, config) => api.post(`/taxes/${id}/cancel`, {}, config),
}

export const insuranceApi = {
  getAll: (vehicleId = null, page = 1) => {
    const params = new URLSearchParams({ page })
    if (vehicleId) params.append('vehicle_id', vehicleId)
    return api.get(`/insurance?${params}`)
  },
  get: (id) => api.get(`/insurance/${id}`),
  create: (data, config) => api.post('/insurance', data, config),
  update: (id, data, config) => api.put(`/insurance/${id}`, data, config),
  delete: (id, config) => api.delete(`/insurance/${id}`, config),
  cancel: (id, config) => api.post(`/insurance/${id}/cancel`, {}, config),
  getActive: () => api.get('/insurance/active'),
  getExpiring: (days = 30) => api.get(`/insurance/expiring?days=${days}`),
}

export const predictionApi = {
  getAll: (vehicleId = null, status = null, locale = 'en-US') => {
    const params = new URLSearchParams()
    if (vehicleId) params.set('vehicle_id', vehicleId)
    if (status) params.set('status', status)
    if (locale) params.set('locale', locale)
    const qs = params.toString()
    return api.get(`/predictions${qs ? `?${qs}` : ''}`)
  },
  get: (id) => api.get(`/predictions/${id}`),
  dismiss: (id) => api.post(`/predictions/${id}/dismiss`),
  refresh: (vehicleId = null, locale = 'en-US', force = false) => {
    const params = new URLSearchParams()
    if (vehicleId) params.set('vehicle_id', vehicleId)
    if (locale && locale !== 'en-US') params.set('locale', locale)
    if (force) params.set('force', 'true')
    const qs = params.toString()
    return api.post(`/predictions/refresh${qs ? `?${qs}` : ''}`)
  },
  getStatus: () => api.get('/predictions/status'),
  // Seasonal Checklists
  getChecklists: () => api.get('/predictions/checklists'),
  toggleChecklistItem: (checklistId, itemId, completed) => {
    const method = completed ? 'post' : 'delete'
    return api[method](`/predictions/checklists/${checklistId}/items/${itemId}`)
  },
  dismissChecklist: (checklistId, dismissed = true) => {
    const method = dismissed ? 'post' : 'delete'
    return api[method](`/predictions/checklists/${checklistId}/dismiss`)
  },
  resetChecklist: (checklistId) => api.post(`/predictions/checklists/${checklistId}/reset`),
  // F54 — user-configurable checklists
  updateChecklistSettings: (settings) => api.put('/predictions/checklists/settings', settings),
  addChecklistItem: (checklistId, label) => api.post(`/predictions/checklists/${checklistId}/custom-items`, { label }),
  removeChecklistItem: (checklistId, itemId) => api.delete(`/predictions/checklists/${checklistId}/custom-items`, { data: { id: itemId } }),
}

export const externalApi = {
  getFuelPrices: (country = 'UK', location = '', lat = null, lon = null, forceRefresh = false) => {
    const params = new URLSearchParams({ country })
    if (location) params.append('location', location)
    if (lat) params.append('lat', lat)
    if (lon) params.append('lon', lon)
    if (forceRefresh) params.append('force_refresh', 'true')
    return api.get(`/external/fuel-prices?${params}`)
  },
  // F25 — stored weekly national price points (accrued by the Monday refresh).
  history: (country = 'UK', weeks = 12) =>
    api.get(`/external/fuel-prices/history?country=${encodeURIComponent(country)}&weeks=${weeks}`),
  getCurrencyRates: () => api.get('/external/currency-rates'),
}

// Attachment/Receipt API
const uploadIntents = new WeakMap()
export const attachmentApi = {
  // Linking a newly created entry is a separate system operation; metadata
  // editors must instead pass the revision they displayed to update().
  link: async (id, data) => {
    const current = await api.get(`/attachments/${id}`)
    return api.put(`/attachments/${id}`, data, mutationOptions(current.data))
  },
  getAll: (params = {}) => {
    const searchParams = new URLSearchParams()
    if (params.vehicleId) searchParams.append('vehicle_id', params.vehicleId)
    if (params.entryId) searchParams.append('entry_id', params.entryId)
    if (params.category) searchParams.append('category', params.category)
    if (params.page) searchParams.append('page', params.page)
    if (params.perPage) searchParams.append('per_page', params.perPage)
    if (params.q) searchParams.append('q', params.q)
    return api.get(`/attachments?${searchParams}`)
  },
  get: (id) => api.get(`/attachments/${id}`),
  upload: (file, data = {}) => {
    const formData = new FormData()
    formData.append('file', file)
    if (data.vehicleId) formData.append('vehicle_id', data.vehicleId)
    if (data.entryId) formData.append('entry_id', data.entryId)
    if (data.category) formData.append('category', data.category)
    if (data.description) formData.append('description', data.description)
    if (!uploadIntents.has(file)) uploadIntents.set(file, crypto.randomUUID())
    return api.post('/attachments', formData, {
      _receiptIdentity: data.identity,
      headers: { 'Content-Type': 'multipart/form-data', ...mutationOptions(null, data.operationKey || uploadIntents.get(file)).headers }
    }).then(response => { uploadIntents.delete(file); return response })
  },
  update: (id, data, config) => api.put(`/attachments/${id}`, data, config),
  delete: (id, config) => api.delete(`/attachments/${id}`, config),
  download: (id) => api.get(`/attachments/${id}/download`, { responseType: 'blob' }),
  // S20: returns the plain view URL — the browser sends the httpOnly session
  // cookie automatically for same-origin <img>/<iframe> requests.
  getViewUrl: (id) => `/api/attachments/${id}/view`,
  // S20: for non-cookie contexts (e.g. programmatic download / external use),
  // call this to obtain a short-lived HMAC-signed URL (valid 5 min).
  getSignedViewUrl: (id) => api.get(`/attachments/${id}/token`).then(r => r.data.url),
  getExpiring: (days = 30, includeExpired = true) => {
    const params = new URLSearchParams()
    params.append('days', days)
    params.append('include_expired', includeExpired)
    return api.get(`/attachments/expiring?${params}`)
  },
  getStats: () => api.get('/attachments/stats'),
  getOcr: (id) => api.get(`/attachments/${id}/ocr`),
  parseOcr: (id) => api.post(`/attachments/${id}/ocr/parse`),
  retryOcr: (id) => api.post(`/attachments/${id}/ocr/retry`),
}

// Calendar API
export const calendarApi = {
  // Get all entries for calendar view
  getEntries: (startDate, endDate, vehicleId = null) => {
    const params = new URLSearchParams()
    if (startDate) params.append('start_date', startDate)
    if (endDate) params.append('end_date', endDate)
    if (vehicleId) params.append('vehicle_id', vehicleId)
    return api.get(`/calendar/entries?${params}`)
  },
  // Export calendar
  exportCalendar: (vehicleId = null) => {
    const params = vehicleId ? `?vehicle_id=${vehicleId}` : ''
    return api.get(`/calendar/export${params}`, { responseType: 'blob' })
  },
  // Get calendar feed token
  getFeedToken: () => api.post('/calendar/feed-token'),
  // R8 — rotates the feed secret, invalidating every ICS link already issued.
  revokeFeedToken: () => api.delete('/calendar/feed-token'),
  // Get sync status
  getSyncStatus: () => api.get('/calendar/sync-status'),
  // Sync all reminders to calendar
  syncAll: () => api.post('/calendar/sync-all'),
  
  // Calendar Sync Configuration
  getProviders: () => api.get('/calendar/providers'),
  getSettings: () => api.get('/calendar/settings'),
  updateSettings: (data) => api.post('/calendar/settings', data),
  testConnection: (data = {}) => api.post('/calendar/test', data),
  getCalendars: (sourceId = null) => {
    const params = sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : ''
    return api.get(`/calendar/calendars${params}`)
  },
  syncAllEntries: () => api.post('/calendar/sync'),
  getSyncJobStatus: () => api.get('/calendar/sync/job-status'),
  retrySync: (sourceId) => api.post('/calendar/sync/retry', { source_id: sourceId }),
  syncEntry: (type, id, action = 'create') => api.post('/calendar/sync/entry', { type, id, action }),
}

// Reports API - PDF Generation
export const reportsApi = {
  // Get available periods and options
  getPeriods: () => api.get('/reports/periods'),
  
  // Preview report info before generating
  preview: (data) => api.post('/reports/preview', data),
  
  // Generate and download PDF report
  generate: (data) => api.post('/reports/generate', data, { responseType: 'blob' }),

  // F05 — shareable read-only report links (signed, expiring, revocable)
  createShare: (data) => api.post('/reports/shares', data),
  listShares: () => api.get('/reports/shares'),
  revokeShare: (id) => api.delete(`/reports/shares/${id}`),
  // Public (no auth) — fetch a shared report by its token
  getSharedReport: (token) => api.get(`/reports/shared/${encodeURIComponent(token)}`),
  // Public PDF download URL for a shared report token
  sharedPdfUrl: (token) => `/api/reports/shared/${encodeURIComponent(token)}/pdf`,
}

// Admin API (requires admin role)
export const adminApi = {
  // Stats
  getStats: () => api.get('/admin/stats'),
  
  // User management
  getUsers: (page = 1, perPage = 20, search = '') => {
    const params = new URLSearchParams({ page, per_page: perPage })
    if (search) params.append('search', search)
    return api.get(`/admin/users?${params}`)
  },
  getUser: (id) => api.get(`/admin/users/${id}`),
  createUser: (data) => api.post('/admin/users', data),
  updateUser: (id, data) => api.put(`/admin/users/${id}`, data),
  deleteUser: (id) => api.delete(`/admin/users/${id}`),
  
  // Settings
  getSettings: () => api.get('/admin/settings'),
  updateSettings: (data) => api.put('/admin/settings', data),
  flushAiCache: () => api.delete('/admin/ai-cache'),
  
  // Activity Logs
  getLogs: (options = {}) => {
    const params = new URLSearchParams()
    if (options.page) params.append('page', options.page)
    if (options.perPage) params.append('per_page', options.perPage)
    if (options.eventType) params.append('event_type', options.eventType)
    if (options.category) params.append('category', options.category)
    if (options.userId) params.append('user_id', options.userId)
    if (options.success !== undefined) params.append('success', options.success)
    if (options.startDate) params.append('start_date', options.startDate)
    if (options.endDate) params.append('end_date', options.endDate)
    if (options.search) params.append('search', options.search)
    if (options.country) params.append('country', options.country)
    return api.get(`/admin/logs?${params}`)
  },
  
  // Maintenance
  previewCleanup: () => api.post('/admin/maintenance/cleanup', { preview: true }),
  runCleanup: () => api.post('/admin/maintenance/cleanup', { preview: false }),
  
  // Blocked IPs and Devices Management
  getBlockedSummary: () => api.get('/admin/blocked/summary'),
  
  getBlockedIPs: (options = {}) => {
    const params = new URLSearchParams()
    if (options.activeOnly !== undefined) params.append('active_only', options.activeOnly)
    if (options.type) params.append('type', options.type)
    if (options.page) params.append('page', options.page)
    if (options.perPage) params.append('per_page', options.perPage)
    return api.get(`/admin/blocked/ips?${params}`)
  },
  
  getBlockedDevices: (options = {}) => {
    const params = new URLSearchParams()
    if (options.activeOnly !== undefined) params.append('active_only', options.activeOnly)
    if (options.type) params.append('type', options.type)
    if (options.page) params.append('page', options.page)
    if (options.perPage) params.append('per_page', options.perPage)
    return api.get(`/admin/blocked/devices?${params}`)
  },
  
  unblockIP: (id, reason = '') => api.post(`/admin/blocked/ip/${id}/unblock`, { reason }),
  unblockDevice: (id, reason = '') => api.post(`/admin/blocked/device/${id}/unblock`, { reason }),
  
  blockIP: (ipAddress, reason = '', expiresHours = null) => 
    api.post('/admin/blocked/ip', { ip_address: ipAddress, reason, expires_hours: expiresHours }),
  
  blockDevice: (userAgent, reason = '', expiresHours = null) => 
    api.post('/admin/blocked/device', { user_agent: userAgent, reason, expires_hours: expiresHours }),
  
  getFailedLogins: (options = {}) => {
    const params = new URLSearchParams()
    if (options.page) params.append('page', options.page)
    if (options.perPage) params.append('per_page', options.perPage)
    if (options.days) params.append('days', options.days)
    if (options.email) params.append('email', options.email)
    if (options.ip) params.append('ip', options.ip)
    return api.get(`/admin/blocked/failed-logins?${params}`)
  },
}

// Global Search API
export const searchApi = {
  /**
   * Search across vehicles, entries, and attachment OCR text.
   * @param {string} q - search query (2–100 chars)
   * @returns Promise<AxiosResponse<{query, results, total}>>
   */
  search: (q) => api.get(`/search?q=${encodeURIComponent(q)}`),
}
