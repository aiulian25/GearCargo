import { useState, useEffect } from 'react'
import { adminApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import toast from 'react-hot-toast'

// Icons
const Icons = {
  shield: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  globe: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
    </svg>
  ),
  monitor: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
    </svg>
  ),
  x: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  check: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  ban: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>
    </svg>
  ),
  unlock: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>
    </svg>
  ),
  refresh: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </svg>
  ),
  plus: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  ),
  alertTriangle: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  chevronDown: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  ),
  chevronUp: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="18 15 12 9 6 15"/>
    </svg>
  ),
}

export default function SecurityBlocking() {
  const { t } = useTranslation()
  
  // State
  const [activeTab, setActiveTab] = useState('overview') // overview, ips, devices, failed-logins
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState(null)
  const [blockedIPs, setBlockedIPs] = useState([])
  const [blockedDevices, setBlockedDevices] = useState([])
  const [failedLogins, setFailedLogins] = useState([])
  const [failedLoginsSummary, setFailedLoginsSummary] = useState(null)
  
  // Modal states
  const [showBlockIPModal, setShowBlockIPModal] = useState(false)
  const [showUnblockModal, setShowUnblockModal] = useState(null) // { type: 'ip' | 'device', item: object }
  const [expandedRow, setExpandedRow] = useState(null)
  
  // Form states
  const [newBlockIP, setNewBlockIP] = useState('')
  const [newBlockReason, setNewBlockReason] = useState('')
  const [unblockReason, setUnblockReason] = useState('')
  
  // Load data
  useEffect(() => {
    loadSummary()
  }, [])
  
  useEffect(() => {
    if (activeTab === 'ips') loadBlockedIPs()
    if (activeTab === 'devices') loadBlockedDevices()
    if (activeTab === 'failed-logins') loadFailedLogins()
  }, [activeTab])
  
  const loadSummary = async () => {
    setLoading(true)
    try {
      const response = await adminApi.getBlockedSummary()
      setSummary(response)
    } catch (error) {
      console.error('Failed to load summary:', error)
      toast.error('Failed to load security summary')
    } finally {
      setLoading(false)
    }
  }
  
  const loadBlockedIPs = async () => {
    try {
      const response = await adminApi.getBlockedIPs()
      setBlockedIPs(response.blocked_ips || [])
    } catch (error) {
      console.error('Failed to load blocked IPs:', error)
    }
  }
  
  const loadBlockedDevices = async () => {
    try {
      const response = await adminApi.getBlockedDevices()
      setBlockedDevices(response.blocked_devices || [])
    } catch (error) {
      console.error('Failed to load blocked devices:', error)
    }
  }
  
  const loadFailedLogins = async () => {
    try {
      const response = await adminApi.getFailedLogins()
      setFailedLogins(response.failed_logins || [])
      setFailedLoginsSummary(response.summary || null)
    } catch (error) {
      console.error('Failed to load failed logins:', error)
    }
  }
  
  const handleUnblockIP = async (id) => {
    try {
      await adminApi.unblockIP(id, unblockReason || 'Unblocked by admin')
      toast.success('IP unblocked successfully')
      setShowUnblockModal(null)
      setUnblockReason('')
      loadBlockedIPs()
      loadSummary()
    } catch (error) {
      toast.error('Failed to unblock IP')
    }
  }
  
  const handleUnblockDevice = async (id) => {
    try {
      await adminApi.unblockDevice(id, unblockReason || 'Unblocked by admin')
      toast.success('Device unblocked successfully')
      setShowUnblockModal(null)
      setUnblockReason('')
      loadBlockedDevices()
      loadSummary()
    } catch (error) {
      toast.error('Failed to unblock device')
    }
  }
  
  const handleBlockIP = async (e) => {
    e.preventDefault()
    if (!newBlockIP.trim()) {
      toast.error('IP address is required')
      return
    }
    
    try {
      await adminApi.blockIP(newBlockIP.trim(), newBlockReason || 'Manually blocked by admin')
      toast.success('IP blocked successfully')
      setShowBlockIPModal(false)
      setNewBlockIP('')
      setNewBlockReason('')
      loadBlockedIPs()
      loadSummary()
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to block IP')
    }
  }
  
  const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    return date.toLocaleString()
  }
  
  if (loading && !summary) {
    return (
      <div className="flex justify-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    )
  }
  
  return (
    <div className="space-y-4">
      {/* Tabs */}
      <div className="flex bg-[var(--color-bg-tertiary)] rounded-lg p-1">
        {[
          { key: 'overview', label: t('admin.security.overview') || 'Overview' },
          { key: 'ips', label: t('admin.security.blockedIPs') || 'Blocked IPs' },
          { key: 'devices', label: t('admin.security.blockedDevices') || 'Blocked Devices' },
          { key: 'failed-logins', label: t('admin.security.failedLogins') || 'Failed Logins' },
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 py-1.5 rounded-md text-2xs font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm'
                : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      
      {/* Overview Tab */}
      {activeTab === 'overview' && summary && (
        <div className="space-y-4">
          {/* Stats Cards */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-red-500">{Icons.ban}</span>
                <span className="text-2xs text-[var(--color-text-muted)]">{t('admin.security.blockedIPs') || 'Blocked IPs'}</span>
              </div>
              <div className="text-xl font-bold text-red-500">{summary.blocked_ips?.total || 0}</div>
              <div className="text-2xs text-[var(--color-text-muted)] mt-1">
                {summary.blocked_ips?.auto || 0} {t('admin.security.auto') || 'auto'} / {summary.blocked_ips?.manual || 0} {t('admin.security.manual') || 'manual'}
              </div>
            </div>
            
            <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-orange-500">{Icons.monitor}</span>
                <span className="text-2xs text-[var(--color-text-muted)]">{t('admin.security.blockedDevices') || 'Blocked Devices'}</span>
              </div>
              <div className="text-xl font-bold text-orange-500">{summary.blocked_devices?.total || 0}</div>
              <div className="text-2xs text-[var(--color-text-muted)] mt-1">
                {summary.blocked_devices?.auto || 0} {t('admin.security.auto') || 'auto'} / {summary.blocked_devices?.manual || 0} {t('admin.security.manual') || 'manual'}
              </div>
            </div>
            
            <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-amber-500">{Icons.alertTriangle}</span>
                <span className="text-2xs text-[var(--color-text-muted)]">{t('admin.security.failed24h') || 'Failed (24h)'}</span>
              </div>
              <div className="text-xl font-bold text-amber-500">{summary.failed_logins?.last_24h || 0}</div>
            </div>
            
            <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-yellow-500">{Icons.alertTriangle}</span>
                <span className="text-2xs text-[var(--color-text-muted)]">{t('admin.security.failed7d') || 'Failed (7d)'}</span>
              </div>
              <div className="text-xl font-bold text-yellow-500">{summary.failed_logins?.last_7d || 0}</div>
            </div>
          </div>
          
          {/* Recent Blocked IPs */}
          {summary.blocked_ips?.recent?.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-[var(--color-text-muted)] mb-2">{t('admin.security.recentBlockedIPs') || 'Recent Blocked IPs'}</h4>
              <div className="space-y-2">
                {summary.blocked_ips.recent.slice(0, 3).map(ip => (
                  <div key={ip.id} className="bg-[var(--color-bg-tertiary)] rounded-lg p-2 flex items-center justify-between">
                    <div>
                      <span className="text-sm font-mono">{ip.ip_address}</span>
                      <span className={`ml-2 px-1.5 py-0.5 rounded text-2xs ${
                        ip.block_type === 'auto' ? 'bg-red-500/10 text-red-500' : 'bg-blue-500/10 text-blue-500'
                      }`}>
                        {ip.block_type}
                      </span>
                      {ip.country && (
                        <span className="ml-2 text-2xs text-[var(--color-text-muted)]">
                          {ip.country}
                        </span>
                      )}
                    </div>
                    <span className="text-2xs text-[var(--color-text-muted)]">
                      {ip.failed_attempts} {t('admin.security.attempts') || 'attempts'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* Recent Blocked Devices */}
          {summary.blocked_devices?.recent?.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-[var(--color-text-muted)] mb-2">{t('admin.security.blockedDevices') || 'Recent Blocked Devices'}</h4>
              <div className="space-y-2">
                {summary.blocked_devices.recent.slice(0, 3).map(device => (
                  <div key={device.id} className="bg-[var(--color-bg-tertiary)] rounded-lg p-2 flex items-center justify-between">
                    <div>
                      <span className="text-sm">{device.browser || 'Unknown'} / {device.os || 'Unknown'}</span>
                      <span className={`ml-2 px-1.5 py-0.5 rounded text-2xs ${
                        device.block_type === 'auto' ? 'bg-red-500/10 text-red-500' : 'bg-blue-500/10 text-blue-500'
                      }`}>
                        {device.block_type}
                      </span>
                    </div>
                    <span className="text-2xs text-[var(--color-text-muted)]">
                      {device.failed_attempts} {t('admin.security.attempts') || 'attempts'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          <button 
            onClick={loadSummary}
            className="w-full py-2 rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] text-sm flex items-center justify-center gap-2 hover:bg-[var(--color-bg-tertiary)]/80"
          >
            {Icons.refresh}
            {t('admin.security.refresh') || 'Refresh'}
          </button>
        </div>
      )}
      
      {/* Blocked IPs Tab */}
      {activeTab === 'ips' && (
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-[var(--color-text-muted)]">
              {blockedIPs.length} blocked IP{blockedIPs.length !== 1 ? 's' : ''}
            </span>
            <button
              onClick={() => setShowBlockIPModal(true)}
              className="px-3 py-1.5 rounded-lg bg-red-500/10 text-red-500 text-xs flex items-center gap-1 hover:bg-red-500/20"
            >
              {Icons.plus} Block IP
            </button>
          </div>
          
          {blockedIPs.length === 0 ? (
            <div className="text-center py-8 text-[var(--color-text-muted)]">
              <div className="mb-2">{Icons.shield}</div>
              <p className="text-sm">No blocked IPs</p>
              <p className="text-2xs">IPs are auto-blocked after 3 failed login attempts</p>
            </div>
          ) : (
            <div className="space-y-2">
              {blockedIPs.map(ip => (
                <div key={ip.id} className="bg-[var(--color-bg-tertiary)] rounded-lg overflow-hidden">
                  <div 
                    className="p-3 flex items-center justify-between cursor-pointer"
                    onClick={() => setExpandedRow(expandedRow === `ip-${ip.id}` ? null : `ip-${ip.id}`)}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-red-500">{Icons.ban}</span>
                      <div>
                        <div className="font-mono text-sm">{ip.ip_address}</div>
                        <div className="text-2xs text-[var(--color-text-muted)]">
                          {ip.country && `${ip.country} • `}{ip.failed_attempts} attempts
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`px-1.5 py-0.5 rounded text-2xs ${
                        ip.block_type === 'auto' ? 'bg-red-500/10 text-red-500' : 'bg-blue-500/10 text-blue-500'
                      }`}>
                        {ip.block_type}
                      </span>
                      {expandedRow === `ip-${ip.id}` ? Icons.chevronUp : Icons.chevronDown}
                    </div>
                  </div>
                  
                  {expandedRow === `ip-${ip.id}` && (
                    <div className="px-3 pb-3 pt-0 border-t border-[var(--color-border)] space-y-2">
                      <div className="grid grid-cols-2 gap-2 text-2xs">
                        <div>
                          <span className="text-[var(--color-text-muted)]">Target Email:</span>
                          <span className="ml-1">{ip.target_email || '-'}</span>
                        </div>
                        <div>
                          <span className="text-[var(--color-text-muted)]">ISP:</span>
                          <span className="ml-1">{ip.isp || '-'}</span>
                        </div>
                        <div>
                          <span className="text-[var(--color-text-muted)]">Blocked:</span>
                          <span className="ml-1">{formatDate(ip.created_at)}</span>
                        </div>
                        <div>
                          <span className="text-[var(--color-text-muted)]">Last Attempt:</span>
                          <span className="ml-1">{formatDate(ip.last_failed_attempt)}</span>
                        </div>
                      </div>
                      {ip.reason && (
                        <div className="text-2xs">
                          <span className="text-[var(--color-text-muted)]">Reason:</span>
                          <span className="ml-1">{ip.reason}</span>
                        </div>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setShowUnblockModal({ type: 'ip', item: ip })
                        }}
                        className="w-full py-1.5 rounded bg-green-500/10 text-green-500 text-xs flex items-center justify-center gap-1 hover:bg-green-500/20"
                      >
                        {Icons.unlock} Unblock IP
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* Blocked Devices Tab */}
      {activeTab === 'devices' && (
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-[var(--color-text-muted)]">
              {blockedDevices.length} blocked device{blockedDevices.length !== 1 ? 's' : ''}
            </span>
          </div>
          
          {blockedDevices.length === 0 ? (
            <div className="text-center py-8 text-[var(--color-text-muted)]">
              <div className="mb-2">{Icons.monitor}</div>
              <p className="text-sm">No blocked devices</p>
              <p className="text-2xs">Devices are auto-blocked after 3 failed login attempts</p>
            </div>
          ) : (
            <div className="space-y-2">
              {blockedDevices.map(device => (
                <div key={device.id} className="bg-[var(--color-bg-tertiary)] rounded-lg overflow-hidden">
                  <div 
                    className="p-3 flex items-center justify-between cursor-pointer"
                    onClick={() => setExpandedRow(expandedRow === `device-${device.id}` ? null : `device-${device.id}`)}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-orange-500">{Icons.monitor}</span>
                      <div>
                        <div className="text-sm">{device.browser || 'Unknown Browser'} / {device.os || 'Unknown OS'}</div>
                        <div className="text-2xs text-[var(--color-text-muted)]">
                          {device.device_type} • {device.failed_attempts} attempts
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`px-1.5 py-0.5 rounded text-2xs ${
                        device.block_type === 'auto' ? 'bg-red-500/10 text-red-500' : 'bg-blue-500/10 text-blue-500'
                      }`}>
                        {device.block_type}
                      </span>
                      {expandedRow === `device-${device.id}` ? Icons.chevronUp : Icons.chevronDown}
                    </div>
                  </div>
                  
                  {expandedRow === `device-${device.id}` && (
                    <div className="px-3 pb-3 pt-0 border-t border-[var(--color-border)] space-y-2">
                      <div className="grid grid-cols-2 gap-2 text-2xs">
                        <div>
                          <span className="text-[var(--color-text-muted)]">Target Email:</span>
                          <span className="ml-1">{device.target_email || '-'}</span>
                        </div>
                        <div>
                          <span className="text-[var(--color-text-muted)]">Browser Version:</span>
                          <span className="ml-1">{device.browser_version || '-'}</span>
                        </div>
                        <div>
                          <span className="text-[var(--color-text-muted)]">OS Version:</span>
                          <span className="ml-1">{device.os_version || '-'}</span>
                        </div>
                        <div>
                          <span className="text-[var(--color-text-muted)]">Fingerprint:</span>
                          <span className="ml-1 font-mono">{device.device_fingerprint?.substring(0, 12)}...</span>
                        </div>
                      </div>
                      {device.associated_ips?.length > 0 && (
                        <div className="text-2xs">
                          <span className="text-[var(--color-text-muted)]">Associated IPs:</span>
                          <span className="ml-1 font-mono">{device.associated_ips.join(', ')}</span>
                        </div>
                      )}
                      {device.reason && (
                        <div className="text-2xs">
                          <span className="text-[var(--color-text-muted)]">Reason:</span>
                          <span className="ml-1">{device.reason}</span>
                        </div>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setShowUnblockModal({ type: 'device', item: device })
                        }}
                        className="w-full py-1.5 rounded bg-green-500/10 text-green-500 text-xs flex items-center justify-center gap-1 hover:bg-green-500/20"
                      >
                        {Icons.unlock} Unblock Device
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* Failed Logins Tab */}
      {activeTab === 'failed-logins' && (
        <div className="space-y-3">
          {failedLoginsSummary && (
            <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Last {failedLoginsSummary.days_included} days</span>
                <span className="text-lg font-bold text-red-500">{failedLoginsSummary.total_failed} failed</span>
              </div>
              {failedLoginsSummary.top_ips?.length > 0 && (
                <div className="text-2xs text-[var(--color-text-muted)]">
                  Top IPs: {failedLoginsSummary.top_ips.slice(0, 3).map(ip => `${ip.ip} (${ip.count})`).join(', ')}
                </div>
              )}
            </div>
          )}
          
          {failedLogins.length === 0 ? (
            <div className="text-center py-8 text-[var(--color-text-muted)]">
              <div className="mb-2">{Icons.check}</div>
              <p className="text-sm">No recent failed logins</p>
            </div>
          ) : (
            <div className="space-y-2">
              {failedLogins.map(log => (
                <div key={log.id} className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-sm font-medium">
                        {log.extra_data?.email || log.description?.match(/email: ([^\s(]+)/)?.[1] || 'Unknown'}
                      </div>
                      <div className="text-2xs text-[var(--color-text-muted)] mt-1">
                        {log.ip_address && <span className="font-mono">{log.ip_address}</span>}
                        {log.country && <span className="ml-2">{log.country}</span>}
                      </div>
                      <div className="text-2xs text-[var(--color-text-muted)] mt-1">
                        {log.browser && `${log.browser} / `}{log.os || 'Unknown OS'}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`text-2xs px-1.5 py-0.5 rounded ${
                        log.event_type === 'login_failed' ? 'bg-red-500/10 text-red-500' :
                        log.event_type === 'login_blocked_ip' ? 'bg-orange-500/10 text-orange-500' :
                        log.event_type === 'login_blocked_device' ? 'bg-yellow-500/10 text-yellow-500' :
                        'bg-gray-500/10 text-gray-500'
                      }`}>
                        {log.event_type?.replace(/_/g, ' ')}
                      </div>
                      <div className="text-2xs text-[var(--color-text-muted)] mt-1">
                        {formatDate(log.created_at)}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          <button 
            onClick={loadFailedLogins}
            className="w-full py-2 rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] text-sm flex items-center justify-center gap-2 hover:bg-[var(--color-bg-tertiary)]/80"
          >
            {Icons.refresh}
            Refresh
          </button>
        </div>
      )}
      
      {/* Block IP Modal */}
      {showBlockIPModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[var(--color-bg-card)] rounded-xl p-4 w-full max-w-sm">
            <h3 className="text-lg font-semibold mb-4">Block IP Address</h3>
            <form onSubmit={handleBlockIP} className="space-y-3">
              <div>
                <label className="text-xs text-[var(--color-text-muted)] mb-1 block">IP Address</label>
                <input
                  type="text"
                  value={newBlockIP}
                  onChange={(e) => setNewBlockIP(e.target.value)}
                  placeholder="e.g., 192.168.1.100"
                  className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-sm"
                  autoFocus
                />
              </div>
              <div>
                <label className="text-xs text-[var(--color-text-muted)] mb-1 block">Reason (optional)</label>
                <input
                  type="text"
                  value={newBlockReason}
                  onChange={(e) => setNewBlockReason(e.target.value)}
                  placeholder="e.g., Suspicious activity"
                  className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-sm"
                />
              </div>
              <div className="flex gap-2 mt-4">
                <button
                  type="button"
                  onClick={() => setShowBlockIPModal(false)}
                  className="flex-1 py-2 rounded-lg bg-[var(--color-bg-tertiary)] text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2 rounded-lg bg-red-500 text-white text-sm"
                >
                  Block IP
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      
      {/* Unblock Modal */}
      {showUnblockModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[var(--color-bg-card)] rounded-xl p-4 w-full max-w-sm">
            <h3 className="text-lg font-semibold mb-2">
              Unblock {showUnblockModal.type === 'ip' ? 'IP Address' : 'Device'}
            </h3>
            <p className="text-sm text-[var(--color-text-muted)] mb-4">
              {showUnblockModal.type === 'ip' 
                ? `Are you sure you want to unblock ${showUnblockModal.item.ip_address}?`
                : `Are you sure you want to unblock this ${showUnblockModal.item.browser || 'unknown'} / ${showUnblockModal.item.os || 'unknown'} device?`
              }
            </p>
            <div className="mb-4">
              <label className="text-xs text-[var(--color-text-muted)] mb-1 block">Reason (optional)</label>
              <input
                type="text"
                value={unblockReason}
                onChange={(e) => setUnblockReason(e.target.value)}
                placeholder="e.g., User verified identity"
                className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-sm"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setShowUnblockModal(null)
                  setUnblockReason('')
                }}
                className="flex-1 py-2 rounded-lg bg-[var(--color-bg-tertiary)] text-sm"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (showUnblockModal.type === 'ip') {
                    handleUnblockIP(showUnblockModal.item.id)
                  } else {
                    handleUnblockDevice(showUnblockModal.item.id)
                  }
                }}
                className="flex-1 py-2 rounded-lg bg-green-500 text-white text-sm"
              >
                Unblock
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
