import axios from 'axios'

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

// No request interceptor needed — the browser attaches the httpOnly
// access_token cookie automatically on every request.  Manual Authorization
// header injection from localStorage is removed (S05).

// Response interceptor — transparent token refresh via cookie
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Skip auth handling on login / register / change-password pages.
    const currentPath = window.location.pathname
    const isAuthPage =
      currentPath === '/login' ||
      currentPath === '/register' ||
      currentPath === '/change-password'

    // Session definitively expired / invalid — no point refreshing.
    const errorCode = error.response?.data?.code
    if (errorCode === 'SESSION_EXPIRED' || errorCode === 'SESSION_INVALID') {
      // Clear the local auth flag so ThemeContext / LanguageContext stop
      // attempting background sync (they check this flag, not the cookie).
      localStorage.removeItem('auth_session')
      if (!isAuthPage) {
        alert(error.response?.data?.error || 'Your session has expired. Please login again.')
        window.location.href = '/login'
      }
      return Promise.reject(error)
    }

    // 401 — try a silent token refresh; the browser sends the refresh_token
    // cookie automatically because withCredentials: true is set.
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isAuthPage) {
        return Promise.reject(error)
      }

      originalRequest._retry = true

      try {
        // POST with empty body — the httpOnly refresh_token cookie is sent
        // automatically.  No localStorage read needed (S05).
        await axios.post('/api/auth/refresh', {}, { withCredentials: true })

        // New access_token cookie is now set by the server.  Retry original request.
        return api(originalRequest)
      } catch (refreshError) {
        const refreshErrorCode = refreshError.response?.data?.code
        if (refreshErrorCode === 'SESSION_EXPIRED' || refreshErrorCode === 'SESSION_INVALID') {
          localStorage.removeItem('auth_session')
          if (!isAuthPage) {
            alert(refreshError.response?.data?.error || 'Your session has expired. Please login again.')
            window.location.href = '/login'
          }
          return Promise.reject(refreshError)
        }

        // Refresh failed for any other reason — send user to login.
        localStorage.removeItem('auth_session')
        if (!isAuthPage) {
          window.location.href = '/login'
        }
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default api

// API helper functions
export const vehicleApi = {
  getAll: () => api.get('/vehicles'),
  getArchived: () => api.get('/vehicles/archived'),
  get: (id) => api.get(`/vehicles/${id}`),
  getById: (id) => api.get(`/vehicles/${id}`),
  create: (data) => api.post('/vehicles', data),
  update: (id, data) => api.put(`/vehicles/${id}`, data),
  delete: (id) => api.delete(`/vehicles/${id}`),
  hardDelete: (id) => api.delete(`/vehicles/${id}?hard=true`),
  archive: (id) => api.post(`/vehicles/${id}/archive`),
  unarchive: (id) => api.post(`/vehicles/${id}/unarchive`),
  getStats: (id) => api.get(`/vehicles/${id}/stats`),
  getHealth: (id) => api.get(`/vehicles/${id}/health`),
  completeHealthAction: (id, data) => api.post(`/vehicles/${id}/health/actions/complete`, data),
  getManual: (id) => api.get(`/vehicles/${id}/manual`),
  getTimeline: (id, page = 1, type = 'all', perPage = 50) =>
    api.get(`/vehicles/${id}/timeline?page=${page}&type=${type}&per_page=${perPage}`),
  reorder: (order) => api.post('/vehicles/reorder', { order }),
  updateMileage: (id, mileage) => api.post(`/vehicles/${id}/mileage`, { mileage }),
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
  get: (id) => api.get(`/fuel/${id}`),
  create: (data) => api.post('/fuel', data),
  update: (id, data) => api.put(`/fuel/${id}`, data),
  delete: (id) => api.delete(`/fuel/${id}`),
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
  create: (data) => api.post('/services', data),
  update: (id, data) => api.put(`/services/${id}`, data),
  delete: (id) => api.delete(`/services/${id}`),
  getUpcoming: () => api.get('/services/upcoming'),
}

export const repairApi = {
  getAll: (vehicleId = null, page = 1) => {
    const params = new URLSearchParams({ page })
    if (vehicleId) params.append('vehicle_id', vehicleId)
    return api.get(`/repairs?${params}`)
  },
  getByVehicle: (vehicleId, page = 1) => api.get(`/repairs?vehicle_id=${vehicleId}&page=${page}`),
  get: (id) => api.get(`/repairs/${id}`),
  create: (data) => api.post('/repairs', data),
  update: (id, data) => api.put(`/repairs/${id}`, data),
  delete: (id) => api.delete(`/repairs/${id}`),
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
  create: (data) => api.post('/reminders', data),
  update: (id, data) => api.put(`/reminders/${id}`, data),
  delete: (id) => api.delete(`/reminders/${id}`),
  complete: (id, mileage = null) => api.post(`/reminders/${id}/complete`, { mileage }),
  snooze: (id, days) => api.post(`/reminders/${id}/snooze`, { days }),
  getUpcoming: (days = 7) => api.get(`/reminders/upcoming?days=${days}`),
  getOverdue: () => api.get('/reminders/overdue'),
  getStats: () => api.get('/reminders/stats'),
}

export const pushApi = {
  getVapidKey: () => api.get('/push/vapid-key'),
  subscribe: (subscription, deviceInfo = {}) => api.post('/push/subscribe', { subscription, ...deviceInfo }),
  unsubscribe: (endpoint) => api.post('/push/unsubscribe', { endpoint }),
  test: () => api.post('/push/test', {}),
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
  
  // 2FA
  setupTotp: () => api.post('/auth/totp/setup'),
  enableTotp: (code) => api.post('/auth/totp/enable', { code }),
  disableTotp: (code) => api.post('/auth/totp/disable', { code }),
  verifyTotp: (email, code) => api.post('/auth/totp/verify', { email, code }),
  
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
  // Get backup status and available backups
  getStatus: () => api.get('/backup/status'),
  
  // Get backup statistics
  getStats: () => api.get('/backup/stats'),
  
  // Get backup history
  getHistory: (page = 1, perPage = 20) => api.get(`/backup/history?page=${page}&per_page=${perPage}`),
  
  // Export data (download)
  export: (format = 'zip', includeAttachments = true, saveToStorage = false) => 
    api.post('/backup/export', { format, include_attachments: includeAttachments, save_to_storage: saveToStorage }, {
      responseType: format === 'zip' ? 'blob' : 'json'
    }),
  
  // Import data from file
  import: (formData) => api.post('/backup/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  
  // Restore from stored backup
  restoreFromStorage: (filename, mergeMode = 'merge') => 
    api.post(`/backup/restore/${filename}`, { merge_mode: mergeMode }),
  
  // Download stored backup
  downloadStored: (filename) => api.get(`/backup/download/${filename}`, { responseType: 'blob' }),

  // Delete stored backup
  deleteBackup: (filename) => api.delete(`/backup/delete/${filename}`),
  
  // Get schedule settings
  getSchedule: () => api.get('/backup/schedule'),
  
  // Update schedule settings
  updateSchedule: (data) => api.put('/backup/schedule', data),
  
  // Run backup now
  runNow: (includeAttachments = true, sendExternal = false) => 
    api.post('/backup/run-now', { include_attachments: includeAttachments, send_external: sendExternal }),

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
  restoreFromExternal: (filename, url = null, apiKey = null, path = null, mergeMode = 'merge') =>
    api.post('/backup/external/restore', { filename, url, api_key: apiKey, path, merge_mode: mergeMode }),

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
  create: (data) => api.post('/taxes', data),
  update: (id, data) => api.put(`/taxes/${id}`, data),
  delete: (id) => api.delete(`/taxes/${id}`),
  cancel: (id) => api.post(`/taxes/${id}/cancel`),
}

export const insuranceApi = {
  getAll: (vehicleId = null, page = 1) => {
    const params = new URLSearchParams({ page })
    if (vehicleId) params.append('vehicle_id', vehicleId)
    return api.get(`/insurance?${params}`)
  },
  get: (id) => api.get(`/insurance/${id}`),
  create: (data) => api.post('/insurance', data),
  update: (id, data) => api.put(`/insurance/${id}`, data),
  delete: (id) => api.delete(`/insurance/${id}`),
  cancel: (id) => api.post(`/insurance/${id}/cancel`),
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
  refresh: (vehicleId = null, locale = 'en-US') => {
    const params = new URLSearchParams()
    if (vehicleId) params.set('vehicle_id', vehicleId)
    if (locale && locale !== 'en-US') params.set('locale', locale)
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
}

export const dashboardApi = {
  getSummary: () => api.get('/dashboard/summary'),
  getOverdueReminders: () => api.get('/dashboard/overdue'),
  getUpcomingReminders: (days = 30) => api.get(`/dashboard/upcoming?days=${days}`),
  getRecentActivity: (limit = 10) => api.get(`/dashboard/activity?limit=${limit}`),
  getCostsByMonth: (year = null) => {
    const params = year ? `?year=${year}` : ''
    return api.get(`/dashboard/costs-by-month${params}`)
  },
}

export const externalApi = {
  getWeather: (lat, lon, location) => {
    const params = new URLSearchParams()
    if (lat) params.append('lat', lat)
    if (lon) params.append('lon', lon)
    if (location) params.append('location', location)
    return api.get(`/external/weather?${params}`)
  },
  getFuelPrices: (country = 'UK', location = '', lat = null, lon = null, forceRefresh = false) => {
    const params = new URLSearchParams({ country })
    if (location) params.append('location', location)
    if (lat) params.append('lat', lat)
    if (lon) params.append('lon', lon)
    if (forceRefresh) params.append('force_refresh', 'true')
    return api.get(`/external/fuel-prices?${params}`)
  },
  getAirQuality: (lat, lon) => {
    const params = new URLSearchParams()
    if (lat) params.append('lat', lat)
    if (lon) params.append('lon', lon)
    return api.get(`/external/air-quality?${params}`)
  },
  getWeatherAlerts: (lat, lon, location) => {
    const params = new URLSearchParams()
    if (lat) params.append('lat', lat)
    if (lon) params.append('lon', lon)
    if (location) params.append('location', location)
    return api.get(`/external/weather-alerts?${params}`)
  },
  getCurrencyRates: () => api.get('/external/currency-rates'),
}

// Attachment/Receipt API
export const attachmentApi = {
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
    return api.post('/attachments', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  update: (id, data) => api.put(`/attachments/${id}`, data),
  delete: (id) => api.delete(`/attachments/${id}`),
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
