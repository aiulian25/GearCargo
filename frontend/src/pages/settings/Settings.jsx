import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { BUILD } from '../../config/build'
import { useTheme } from '../../contexts/ThemeContext'
import { useAuth } from '../../contexts/AuthContext'
import { useLanguage, useTranslation } from '../../contexts/LanguageContext'
import { backupApi, vehicleApi, authApi, calendarApi, reportsApi, attachmentApi } from '../../services/api'
import { usePushNotifications } from '../../hooks/usePushNotifications'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import UserManagement from '../../components/admin/UserManagement'
import SystemLogs from '../../components/admin/SystemLogs'
import MaintenanceCleanup from '../../components/admin/MaintenanceCleanup'
import { formatDate, formatDateTime } from '../../utils/dateFormat'
import SecurityBlocking from '../../components/admin/SecurityBlocking'
import AiStatusPanel from '../../components/admin/AiStatusPanel'
import TwoFactorSetup from '../../components/settings/TwoFactorSetup'
import SecurityQuestionsSetup from '../../components/settings/SecurityQuestionsSetup'
import BackupSettings from '../../components/settings/BackupSettings'
import IntegrationSettings from '../../components/settings/IntegrationSettings'
import PrivacyPolicy from '../../components/settings/PrivacyPolicy'
import TermsOfService from '../../components/settings/TermsOfService'
import SyncIndicator from '../../components/PWA/SyncIndicator'
import PushPrimingModal from '../../components/PWA/PushPrimingModal'
import toast from 'react-hot-toast'

// SVG Icons for Settings
const SettingsIcons = {
  chevronRight: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
    </svg>
  ),
  darkMode: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
    </svg>
  ),
  lightMode: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
    </svg>
  ),
  language: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 21l5.25-11.25L21 21m-9-3h7.5M3 5.621a48.474 48.474 0 016-.371m0 0c1.12 0 2.233.038 3.334.114M9 5.25V3m3.334 2.364C11.176 10.658 7.69 15.08 3 17.502m9.334-12.138c.896.061 1.785.147 2.666.257m-4.589 8.495a18.023 18.023 0 01-3.827-5.802" />
    </svg>
  ),
  bell: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
    </svg>
  ),
  email: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
    </svg>
  ),
  download: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
    </svg>
  ),
  upload: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
    </svg>
  ),
  info: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
    </svg>
  ),
  document: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  ),
  gavel: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v17.25m0 0c-1.472 0-2.882.265-4.185.75M12 20.25c1.472 0 2.882.265 4.185.75M18.75 4.97A48.416 48.416 0 0012 4.5c-2.291 0-4.545.16-6.75.47m13.5 0c1.01.143 2.01.317 3 .52m-3-.52l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.988 5.988 0 01-2.031.352 5.988 5.988 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L18.75 4.971zm-16.5.52c.99-.203 1.99-.377 3-.52m0 0l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.989 5.989 0 01-2.031.352 5.989 5.989 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L5.25 4.971z" />
    </svg>
  ),
  externalLink: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
    </svg>
  ),
  logout: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
    </svg>
  ),
  users: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
    </svg>
  ),
  chevronDown: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
    </svg>
  ),
  chevronUp: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
    </svg>
  ),
  shield: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
    </svg>
  ),
  lock: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
    </svg>
  ),
  archive: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
    </svg>
  ),
  restore: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" />
    </svg>
  ),
  car: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 18.75a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 01-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h1.125c.621 0 1.125-.504 1.125-1.125v-5.25a2.25 2.25 0 00-.659-1.591l-3.591-3.591A2.25 2.25 0 0014.466 6H6a2.25 2.25 0 00-2.25 2.25v9.375c0 .621.504 1.125 1.125 1.125H5.25" />
    </svg>
  ),
  trash: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
    </svg>
  ),
  calendar: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
    </svg>
  ),
  link: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
    </svg>
  ),
  refresh: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
    </svg>
  ),
  report: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  ),
  chartBar: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
    </svg>
  ),
  warning: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
    </svg>
  ),
  clock: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
}

export default function Settings() {
  const navigate = useNavigate()
  const { theme, setTheme } = useTheme()
  const { user, logout, refreshUser } = useAuth()
  const { language, setLanguage, currency, languageNames, supportedLanguages } = useLanguage()
  const { t } = useTranslation()
  const confirm = useConfirm()
  
  // Push notifications hook
  const {
    isSupported: pushSupported,
    isSubscribed: pushSubscribed,
    loading: pushLoading,
    toggle: togglePush,
    subscribe: subscribePush,
    resubscribe: resubscribePush,
    isDenied: pushDenied,
    isGranted: pushGranted,
    isDefault: pushDefault,
    sendTestNotification,
  } = usePushNotifications()

  // Permission-priming modal — shown before the browser prompt the first time.
  const [showPushPriming, setShowPushPriming] = useState(false)
  
  const [show2FASetup, setShow2FASetup] = useState(false)
  const [showSecurityQuestionsSetup, setShowSecurityQuestionsSetup] = useState(false)
  const [showBackupSettings, setShowBackupSettings] = useState(false)
  const [showIntegrations, setShowIntegrations] = useState(false)
  const [showEmailSettings, setShowEmailSettings] = useState(false)
  const [showCalendarSettings, setShowCalendarSettings] = useState(false)
  
  // Email notification settings
  const [emailSettings, setEmailSettings] = useState({
    notifications_enabled: true,
    notification_email: '',
    email_insurance_alerts: true,
    email_tax_alerts: true,
    email_service_alerts: true,
    email_reminder_alerts: true,
    email_smart_alerts: true,
    login_alerts_enabled: true,
    daily_alerts_enabled: true,
    weekly_report_enabled: false,
    monthly_report_enabled: true,
    alert_days_before: 14,
    email_enabled_on_server: false,
  })
  const [sendingTestEmail, setSendingTestEmail] = useState(false)
  const [notifEmail, setNotifEmail] = useState('')
  const [notifEmailVerified, setNotifEmailVerified] = useState(false)
  const [hasNotifEmail, setHasNotifEmail] = useState(false)
  const [notifEmailConsent, setNotifEmailConsent] = useState(false)
  const [notifEmailSaving, setNotifEmailSaving] = useState(false)
  const [notifEmailResending, setNotifEmailResending] = useState(false)
  const [consentHistory, setConsentHistory] = useState([])
  const [showConsentHistory, setShowConsentHistory] = useState(false)
  
  const [showAdminSection, setShowAdminSection] = useState(false)
  const [adminTab, setAdminTab] = useState('users')  // 'users', 'logs', 'maintenance', 'security', or 'ai'
  const [showArchiveSection, setShowArchiveSection] = useState(false)
  const [showPrivacyPolicy, setShowPrivacyPolicy] = useState(false)
  const [showTermsOfService, setShowTermsOfService] = useState(false)
  const [archivedVehicles, setArchivedVehicles] = useState([])
  const [loadingArchived, setLoadingArchived] = useState(false)
  
  // Calendar sync settings
  const [calendarSettings, setCalendarSettings] = useState({
    enabled: false,
    provider: '',
    url: '',
    server: '',
    username: '',
    password: '',
    calendar_id: '',
    configured: false,
    last_sync: null,
    sources: [],
  })
  const [selectedCalendarSourceId, setSelectedCalendarSourceId] = useState('')
  const [calendarProviders, setCalendarProviders] = useState([])
  const [calendarLoading, setCalendarLoading] = useState(false)
  const [calendarTesting, setCalendarTesting] = useState(false)
  const [calendarSyncing, setCalendarSyncing] = useState(false)
  const [availableCalendars, setAvailableCalendars] = useState([])
  const [showSetupGuide, setShowSetupGuide] = useState(false)
  
  // Reports settings
  const [showReportsSection, setShowReportsSection] = useState(false)
  const [reportVehicles, setReportVehicles] = useState([])
  const [reportPeriods, setReportPeriods] = useState([])
  const [reportYears, setReportYears] = useState([])
  const [reportMonths, setReportMonths] = useState([])
  const [reportSettings, setReportSettings] = useState({
    vehicleId: 'all',
    period: 'current_month',
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
  })
  const [reportPreview, setReportPreview] = useState(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportGenerating, setReportGenerating] = useState(false)
  // F05 — shareable report links
  const [shareLinks, setShareLinks] = useState([])
  const [shareCreating, setShareCreating] = useState(false)
  const [shareExpiryDays, setShareExpiryDays] = useState(7)
  const [createdShare, setCreatedShare] = useState(null)

  // Expiring attachments state
  const [expiringAttachments, setExpiringAttachments] = useState({
    expiring_soon: [],
    expired: [],
    expiring_count: 0,
    expired_count: 0,
    total_count: 0,
  })
  const [expiringLoading, setExpiringLoading] = useState(true)
  const [showExpiringSection, setShowExpiringSection] = useState(false)
  
  const isAdmin = user?.is_admin === true
  
  // Storage stats state (admin only)
  const [storageStats, setStorageStats] = useState(null)
  const [storageLoading, setStorageLoading] = useState(false)
  const [showStorageSection, setShowStorageSection] = useState(false)
  
  // Helper function for human-readable file sizes
  const _humanSize = (size) => {
    if (!size) return '0 B'
    for (const unit of ['B', 'KB', 'MB', 'GB']) {
      if (size < 1024) return `${size.toFixed(1)} ${unit}`
      size /= 1024
    }
    return `${size.toFixed(1)} TB`
  }
  
  // Clean up sync poll on unmount
  useEffect(() => () => stopSyncPoll(), []) // eslint-disable-line react-hooks/exhaustive-deps

  // Load expiring attachments
  useEffect(() => {
    const fetchExpiringAttachments = async () => {
      try {
        setExpiringLoading(true)
        const response = await attachmentApi.getExpiring(30, true)
        setExpiringAttachments(response.data)
        // Auto-expand if there are expiring/expired documents
        if (response.data.total_count > 0) {
          setShowExpiringSection(true)
        }
      } catch (error) {
        console.error('Failed to fetch expiring attachments:', error)
      } finally {
        setExpiringLoading(false)
      }
    }
    fetchExpiringAttachments()
  }, [])
  
  // Load storage stats (admin only)
  useEffect(() => {
    if (!isAdmin) return
    const fetchStorageStats = async () => {
      try {
        setStorageLoading(true)
        const response = await attachmentApi.getStats()
        setStorageStats(response.data)
      } catch (error) {
        console.error('Failed to fetch storage stats:', error)
      } finally {
        setStorageLoading(false)
      }
    }
    fetchStorageStats()
  }, [isAdmin])
  
  // Load email settings
  useEffect(() => {
    const fetchEmailSettings = async () => {
      try {
        const response = await authApi.getEmailSettings()
        setEmailSettings(response.data)
        // GDPR notification email fields
        if (response.data.notification_email) {
          setNotifEmail(response.data.notification_email)
        }
        setNotifEmailVerified(!!response.data.notification_email_verified)
        setHasNotifEmail(!!response.data.has_notification_email)
      } catch (error) {
        console.error('Failed to fetch email settings:', error)
      }
      
      // Auto-verify from URL param AFTER settings loaded (double opt-in step 2)
      const params = new URLSearchParams(window.location.search)
      const verifyToken = params.get('verify_notification')
      if (verifyToken) {
        try {
          const res = await authApi.verifyNotificationEmail(verifyToken)
          toast.success(t('settings.notifEmailVerified') || 'Notification email verified!')
          setNotifEmailVerified(true)
          setHasNotifEmail(true)
          if (res.data?.notification_email) {
            setNotifEmail(res.data.notification_email)
          }
        } catch (err) {
          toast.error(err.response?.data?.error || t('settings.notifEmailVerifyFailed') || 'Verification failed')
        } finally {
          // Clean URL regardless of success/failure
          const url = new URL(window.location)
          url.searchParams.delete('verify_notification')
          window.history.replaceState({}, '', url)
        }
      }
    }
    fetchEmailSettings()
  }, [])
  
  // Load calendar settings
  useEffect(() => {
    const fetchCalendarSettings = async () => {
      try {
        const [settingsRes, providersRes] = await Promise.all([
          calendarApi.getSettings(),
          calendarApi.getProviders()
        ])
        const incoming = settingsRes.data || {}
        const sources = Array.isArray(incoming.sources) ? incoming.sources : []
        const firstSource = sources[0] || null
        setCalendarSettings(prev => ({
          ...prev,
          ...incoming,
          provider: firstSource?.provider || incoming.provider || '',
          url: firstSource?.url || incoming.url || '',
          username: firstSource?.username || incoming.username || '',
          calendar_id: firstSource?.calendar_id || incoming.calendar_id || '',
          password: '',
          sources,
        }))
        setSelectedCalendarSourceId(firstSource?.id || '')
        setCalendarProviders(providersRes.data.providers || [])
      } catch (error) {
        console.error('Failed to fetch calendar settings:', error)
      }
    }
    fetchCalendarSettings()
  }, [])
  
  // Load reports data when section is expanded
  useEffect(() => {
    if (showReportsSection && reportVehicles.length === 0) {
      const fetchReportData = async () => {
        setReportLoading(true)
        try {
          const [vehiclesRes, periodsRes] = await Promise.all([
            vehicleApi.getAll(),
            reportsApi.getPeriods()
          ])
          setReportVehicles(vehiclesRes.data.vehicles || [])
          setReportPeriods(periodsRes.data.periods || [])
          setReportYears(periodsRes.data.years || [])
          setReportMonths(periodsRes.data.months || [])
          setReportSettings(prev => ({
            ...prev,
            year: periodsRes.data.current_year,
            month: periodsRes.data.current_month
          }))
        } catch (error) {
          console.error('Failed to fetch report data:', error)
        } finally {
          setReportLoading(false)
        }
      }
      fetchReportData()
    }
  }, [showReportsSection])
  
  // Load archived vehicles when section is expanded
  useEffect(() => {
    if (showArchiveSection && archivedVehicles.length === 0) {
      loadArchivedVehicles()
    }
  }, [showArchiveSection])
  
  const loadArchivedVehicles = async () => {
    setLoadingArchived(true)
    try {
      const response = await vehicleApi.getArchived()
      setArchivedVehicles(response.data.vehicles || [])
    } catch (error) {
      console.error('Failed to load archived vehicles:', error)
      toast.error(t('archive.loadFailed') || 'Failed to load archived vehicles')
    } finally {
      setLoadingArchived(false)
    }
  }
  
  const handleRestoreVehicle = async (vehicleId) => {
    if (!window.confirm(t('archive.restoreConfirm') || 'Restore this vehicle?')) return
    
    try {
      await vehicleApi.unarchive(vehicleId)
      setArchivedVehicles(prev => prev.filter(v => v.id !== vehicleId))
      toast.success(t('archive.restoreSuccess') || 'Vehicle restored successfully')
    } catch (error) {
      console.error('Failed to restore vehicle:', error)
      toast.error(t('archive.restoreFailed') || 'Failed to restore vehicle')
    }
  }
  
  const handleDeleteArchivedVehicle = async (vehicleId) => {
    const v = archivedVehicles.find((x) => x.id === vehicleId)
    const name = v?.name || `${v?.make || ''} ${v?.model || ''}`.trim()
    const ok = await confirm({
      title: t('confirm.deleteVehicleTitle') || 'Delete vehicle?',
      message: (t('confirm.deleteVehicleMessage') || 'Permanently delete “{name}” and all its data (fuel, services, repairs, taxes, insurance, attachments). This cannot be undone.').replace('{name}', name),
      confirmLabel: t('common.delete') || 'Delete',
      destructive: true,
    })
    if (!ok) return

    try {
      await vehicleApi.hardDelete(vehicleId)
      setArchivedVehicles(prev => prev.filter(v => v.id !== vehicleId))
      toast.success(t('archive.deleteSuccess') || 'Vehicle deleted permanently')
    } catch (error) {
      console.error('Failed to delete vehicle:', error)
      toast.error(t('archive.deleteFailed') || 'Failed to delete vehicle')
    }
  }
  
  const handlePushToggle = async () => {
    if (!pushSupported) {
      toast.error(t('settings.pushNotSupported') || 'Push notifications are not supported in this browser')
      return
    }

    if (pushDenied) {
      toast.error(t('settings.pushDenied') || 'Push notifications are blocked. Please enable them in your browser settings.')
      return
    }

    // Enabling for the first time (OS permission still "default"): prime the
    // user with the value proposition BEFORE triggering the one-shot prompt.
    if (!pushSubscribed && pushDefault) {
      setShowPushPriming(true)
      return
    }

    // Already granted, or turning off — act immediately.
    const success = await togglePush()
    if (success) {
      toast.success(
        pushSubscribed
          ? (t('settings.pushDisabled') || 'Push notifications disabled')
          : (t('settings.pushEnabled') || 'Push notifications enabled')
      )
    } else {
      toast.error(t('settings.pushFailed') || 'Failed to update push notification settings')
    }
  }

  // User confirmed the priming modal → now trigger the real browser prompt.
  const handlePushPrimingConfirm = async () => {
    setShowPushPriming(false)
    const success = await subscribePush()
    if (success) {
      toast.success(t('settings.pushEnabled') || 'Push notifications enabled')
    } else if (Notification.permission === 'denied') {
      toast.error(t('settings.pushDenied') || 'Push notifications are blocked. Please enable them in your browser settings.')
    } else {
      toast.error(t('settings.pushFailed') || 'Failed to update push notification settings')
    }
  }

  // Recover a stale/expired subscription without toggling off first.
  const handleResubscribe = async () => {
    const success = await resubscribePush()
    if (success) {
      toast.success(t('settings.pushResubscribed') || 'Notifications re-subscribed')
    } else {
      toast.error(t('settings.pushResubscribeFailed') || 'Failed to re-subscribe')
    }
  }
  
  const handleTestNotification = async () => {
    const success = await sendTestNotification()
    if (success) {
      toast.success(t('settings.testNotificationSent') || 'Test notification sent!')
    } else {
      toast.error(t('settings.testNotificationFailed') || 'Failed to send test notification')
    }
  }
  
  // Email notification handlers
  const handleEmailSettingChange = async (field, value) => {
    const newSettings = { ...emailSettings, [field]: value }
    setEmailSettings(newSettings)
    
    try {
      await authApi.updateProfile({ [field]: value })
      // Don't show toast for every toggle, only for main switches
      if (field === 'notifications_enabled') {
        toast.success(value 
          ? (t('settings.emailAlertsEnabled') || 'Email alerts enabled')
          : (t('settings.emailAlertsDisabled') || 'Email alerts disabled')
        )
      }
    } catch (error) {
      console.error('Failed to update email settings:', error)
      // Revert on error
      setEmailSettings(emailSettings)
      toast.error(t('settings.emailSettingsFailed') || 'Failed to update email settings')
    }
  }
  
  const handleSendTestEmail = async () => {
    if (sendingTestEmail) return
    
    setSendingTestEmail(true)
    try {
      await authApi.sendTestEmail()
      toast.success(t('settings.testEmailSent') || 'Test email sent! Check your inbox.')
    } catch (error) {
      console.error('Failed to send test email:', error)
      toast.error(error.response?.data?.error || t('settings.testEmailFailed') || 'Failed to send test email')
    } finally {
      setSendingTestEmail(false)
    }
  }
  
  // GDPR Notification Email handlers
  const handleSetNotificationEmail = async () => {
    if (!notifEmail || !notifEmailConsent) return
    setNotifEmailSaving(true)
    try {
      await authApi.setNotificationEmail({
        email: notifEmail,
        consent: true,
        consent_text: 'I consent to receiving email notifications at this address. My email will be encrypted and I can withdraw consent at any time.',
      })
      toast.success(t('settings.notifEmailSet') || 'Verification email sent! Check your inbox.')
      setHasNotifEmail(true)
      setNotifEmailVerified(false)
    } catch (error) {
      toast.error(error.response?.data?.error || t('settings.notifEmailSetFailed') || 'Failed to set notification email')
    } finally {
      setNotifEmailSaving(false)
    }
  }
  
  const handleRemoveNotificationEmail = async () => {
    try {
      await authApi.removeNotificationEmail()
      toast.success(t('settings.notifEmailRemoved') || 'Notification email removed')
      setNotifEmail('')
      setHasNotifEmail(false)
      setNotifEmailVerified(false)
      setNotifEmailConsent(false)
    } catch (error) {
      toast.error(error.response?.data?.error || t('settings.notifEmailRemoveFailed') || 'Failed to remove notification email')
    }
  }
  
  const handleResendVerification = async () => {
    setNotifEmailResending(true)
    try {
      await authApi.resendNotificationVerification()
      toast.success(t('settings.notifEmailResent') || 'Verification email resent!')
    } catch (error) {
      toast.error(error.response?.data?.error || t('settings.notifEmailResendFailed') || 'Failed to resend verification')
    } finally {
      setNotifEmailResending(false)
    }
  }
  
  const handleLoadConsentHistory = async () => {
    if (!showConsentHistory) {
      try {
        const res = await authApi.getConsentHistory()
        setConsentHistory(res.data.history || [])
      } catch (error) {
        console.error('Failed to load consent history:', error)
      }
    }
    setShowConsentHistory(!showConsentHistory)
  }
  
  // Calendar sync handlers
  const createEmptyCalendarSource = (index = 1) => ({
    id: `calendar_source_${Date.now()}_${index}`,
    name: `${t('settings.calendarSource') || 'Calendar Source'} ${index}`,
    provider: 'caldav',
    url: '',
    username: '',
    password: '',
    has_password: false,
    calendar_id: '',
    enabled: true,
  })

  const selectedCalendarSource = (calendarSettings.sources || []).find(source => source.id === selectedCalendarSourceId) || null

  const updateCalendarSources = (updater) => {
    setCalendarSettings(prev => {
      const current = Array.isArray(prev.sources) ? prev.sources : []
      const next = updater(current)
      return { ...prev, sources: next }
    })
  }

  const handleCalendarProviderChange = (provider) => {
    const providerInfo = calendarProviders.find(p => p.id === provider)
    updateCalendarSources((sources) => sources.map((source) => {
      if (source.id !== selectedCalendarSourceId) return source
      return {
        ...source,
        provider,
        url: source.url || providerInfo?.default_url || '',
      }
    }))
    if (provider) setShowSetupGuide(true)
  }

  const handleCalendarSettingChange = (field, value) => {
    updateCalendarSources((sources) => sources.map((source) => {
      if (source.id !== selectedCalendarSourceId) return source
      return { ...source, [field]: value }
    }))
  }

  const addCalendarSource = () => {
    updateCalendarSources((sources) => {
      const next = [...sources, createEmptyCalendarSource(sources.length + 1)]
      const added = next[next.length - 1]
      setSelectedCalendarSourceId(added.id)
      return next
    })
  }

  const removeCalendarSource = (sourceId) => {
    updateCalendarSources((sources) => {
      if (sources.length <= 1) {
        const fallback = createEmptyCalendarSource(1)
        setSelectedCalendarSourceId(fallback.id)
        return [fallback]
      }
      const next = sources.filter(source => source.id !== sourceId)
      if (!next.find(source => source.id === selectedCalendarSourceId)) {
        setSelectedCalendarSourceId(next[0]?.id || '')
      }
      return next
    })
  }
  
  const handleSaveCalendarSettings = async () => {
    setCalendarLoading(true)
    try {
      const sources = (calendarSettings.sources || []).map((source, index) => ({
        id: source.id || `calendar_source_${index + 1}`,
        name: source.name || `${t('settings.calendarSource') || 'Calendar Source'} ${index + 1}`,
        provider: source.provider || 'caldav',
        url: (source.url || '').trim(),
        username: (source.username || '').trim(),
        password: (source.password || '').trim(),
        calendar_id: source.calendar_id || '',
        enabled: source.enabled !== false,
      }))

      const response = await calendarApi.updateSettings({
        enabled: calendarSettings.enabled,
        sources,
      })

      const savedSources = response.data?.sources || []
      setCalendarSettings(prev => ({ ...prev, ...response.data, sources: savedSources, password: '' }))
      if (savedSources.length && !savedSources.find(source => source.id === selectedCalendarSourceId)) {
        setSelectedCalendarSourceId(savedSources[0].id)
      }

      toast.success(t(response.data?.message_key) || t('settings.calendarSettingsSaved') || 'Calendar settings saved')
    } catch (error) {
      console.error('Failed to save calendar settings:', error)
      const messageKey = error.response?.data?.message_key
      toast.error((messageKey ? t(messageKey) : null) || error.response?.data?.error || t('settings.calendarSettingsFailed') || 'Failed to save calendar settings')
    } finally {
      setCalendarLoading(false)
    }
  }
  
  const handleTestCalendarConnection = async () => {
    if (calendarTesting) return
    if (!selectedCalendarSource) {
      toast.error(t('settings.selectSourceFirst') || 'Select a calendar source first')
      return
    }
    
    setCalendarTesting(true)
    try {
      const response = await calendarApi.testConnection({ source: selectedCalendarSource })
      toast.success((response.data?.message_key ? t(response.data.message_key) : null) || response.data.message || t('settings.calendarConnectionSuccess') || 'Calendar connection successful!')
      
      // Use calendars returned by the test response directly (avoids a second round-trip
      // and works even when the source hasn't been saved yet, preventing a 404)
      const calendars = response.data?.calendars || []
      setAvailableCalendars(calendars)
      
      if (calendars.length > 0 && !selectedCalendarSource.calendar_id) {
        // Auto-select first calendar if none selected
        handleCalendarSettingChange('calendar_id', calendars[0].id)
      }
    } catch (error) {
      console.error('Failed to connect to calendar:', error)
      const messageKey = error.response?.data?.message_key
      toast.error((messageKey ? t(messageKey) : null) || error.response?.data?.error || t('settings.calendarConnectionFailed') || 'Failed to connect to calendar')
    } finally {
      setCalendarTesting(false)
    }
  }
  
  const syncPollRef = useRef(null)

  const stopSyncPoll = () => {
    if (syncPollRef.current) {
      clearInterval(syncPollRef.current)
      syncPollRef.current = null
    }
    setCalendarSyncing(false)
  }

  const startSyncPoll = () => {
    let attempts = 0
    const maxAttempts = 150 // 5 minutes at 2s intervals
    syncPollRef.current = setInterval(async () => {
      attempts++
      try {
        const status = await calendarApi.getSyncJobStatus()
        const { status: state, synced, failed, error } = status.data
        if (state === 'done') {
          stopSyncPoll()
          if (failed > 0) {
            toast.success(
              t('settings.calendarSyncSuccess', { count: synced }) ||
              `Synced ${synced} entries (${failed} failed)`
            )
          } else {
            toast.success(
              t('settings.calendarSyncSuccess', { count: synced }) ||
              `Successfully synced ${synced} entries to calendar`
            )
          }
        } else if (state === 'failed') {
          stopSyncPoll()
          toast.error(error || t('settings.calendarSyncFailed') || 'Sync failed')
        }
      } catch (_) {
        // poll error — keep trying
      }
      if (attempts >= maxAttempts) {
        stopSyncPoll()
        toast.error(t('settings.calendarSyncFailed') || 'Sync timed out')
      }
    }, 2000)
  }

  const handleSyncAllToCalendar = async () => {
    if (calendarSyncing) return

    setCalendarSyncing(true)
    try {
      const response = await calendarApi.syncAllEntries()
      if (response.status === 202 || response.data.queued) {
        toast(t('settings.calendarSyncStarted') || 'Sync started — checking progress…', { icon: '⏳' })
        startSyncPoll()
        return // keep calendarSyncing=true while polling
      } else {
        toast.success(
          t('settings.calendarSyncSuccess', { count: response.data.synced }) ||
          `Successfully synced ${response.data.synced} entries to calendar`
        )
        setCalendarSyncing(false)
      }
    } catch (error) {
      console.error('Failed to sync to calendar:', error)
      toast.error(error.response?.data?.error || t('settings.calendarSyncFailed') || 'Failed to sync to calendar')
      setCalendarSyncing(false)
    }
  }
  
  // Report handlers
  const handleReportSettingChange = (field, value) => {
    setReportSettings(prev => ({ ...prev, [field]: value }))
    setReportPreview(null) // Clear preview when settings change
  }
  
  const handlePreviewReport = async () => {
    setReportLoading(true)
    try {
      const data = {
        vehicle_ids: reportSettings.vehicleId === 'all' ? 'all' : [parseInt(reportSettings.vehicleId)],
        period: reportSettings.period,
        year: reportSettings.year,
        month: reportSettings.month,
      }
      const response = await reportsApi.preview(data)
      setReportPreview(response.data)
    } catch (error) {
      console.error('Failed to preview report:', error)
      toast.error(t('settings.reportPreviewFailed') || 'Failed to load report preview')
    } finally {
      setReportLoading(false)
    }
  }
  
  const handleGenerateReport = async () => {
    if (reportGenerating) return
    
    setReportGenerating(true)
    try {
      const data = {
        vehicle_ids: reportSettings.vehicleId === 'all' ? 'all' : [parseInt(reportSettings.vehicleId)],
        period: reportSettings.period,
        year: reportSettings.year,
        month: reportSettings.month,
      }
      
      const response = await reportsApi.generate(data)
      
      // Create download link
      const blob = new Blob([response.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      
      // Get filename from Content-Disposition header or generate one
      const contentDisposition = response.headers?.['content-disposition']
      let filename = 'GearCargo_Report.pdf'
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?([^";\n]+)"?/)
        if (match) filename = match[1]
      }
      
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
      
      toast.success(t('settings.reportGenerated') || 'Report downloaded successfully!')
    } catch (error) {
      console.error('Failed to generate report:', error)
      toast.error(error.response?.data?.error || t('settings.reportFailed') || 'Failed to generate report')
    } finally {
      setReportGenerating(false)
    }
  }
  
  // F05 — shareable report link handlers
  const loadShares = async () => {
    try {
      const r = await reportsApi.listShares()
      setShareLinks(r.data?.shares || [])
    } catch (error) {
      console.error('Failed to load share links:', error)
    }
  }

  const handleCreateShare = async () => {
    if (shareCreating) return
    setShareCreating(true)
    setCreatedShare(null)
    try {
      const res = await reportsApi.createShare({
        vehicle_ids: reportSettings.vehicleId === 'all' ? 'all' : [parseInt(reportSettings.vehicleId)],
        period: reportSettings.period,
        year: reportSettings.year,
        month: reportSettings.month,
        expires_in_days: shareExpiryDays,
      })
      setCreatedShare(res.data)
      await loadShares()
      toast.success(t('reportShare.created') || 'Share link created')
    } catch (error) {
      toast.error(error.response?.data?.error || t('reportShare.createFailed') || 'Failed to create share link')
    } finally {
      setShareCreating(false)
    }
  }

  const handleRevokeShare = async (id) => {
    if (!window.confirm(t('reportShare.revokeConfirm') || 'Revoke this link? Anyone using it will immediately lose access.')) return
    try {
      await reportsApi.revokeShare(id)
      if (createdShare?.id === id) setCreatedShare(null)
      await loadShares()
      toast.success(t('reportShare.revoked') || 'Link revoked')
    } catch (error) {
      toast.error(t('common.error') || 'Error')
    }
  }

  const copyShareLink = async (url) => {
    try {
      await navigator.clipboard.writeText(url)
      toast.success(t('reportShare.copied') || 'Link copied')
    } catch {
      toast.error(t('reportShare.copyFailed') || 'Could not copy link')
    }
  }

  // Load existing share links when the Reports section is opened.
  useEffect(() => {
    if (showReportsSection) loadShares()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showReportsSection])

  const handleLogout = () => {
    if (window.confirm('Are you sure you want to logout?')) {
      logout()
      navigate('/login')
    }
  }
  
  return (
    <div className="p-4 pb-24">
      {/* Header */}
      <h1 className="text-lg font-semibold mb-4">{t('nav.settings')}</h1>
      
      {/* User Card */}
      <div 
        className="card flex items-center gap-4 mb-4 cursor-pointer"
        onClick={() => navigate('/settings/profile')}
      >
        <div className="w-14 h-14 rounded-full bg-[var(--color-accent)] flex items-center justify-center flex-shrink-0">
          <span className="text-xl font-bold text-white">
            {user?.name?.charAt(0).toUpperCase() || 'U'}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-medium truncate">{user?.name || 'User'}</h2>
          <p className="text-xs text-[var(--color-text-secondary)] truncate">{user?.email}</p>
        </div>
        <span className="text-[var(--color-text-muted)]">
          {SettingsIcons.chevronRight}
        </span>
      </div>
      
      {/* Expiring Attachments Section */}
      {!expiringLoading && (
        <div className={`card mb-4 ${expiringAttachments.total_count > 0 ? `border-2 ${expiringAttachments.expired_count > 0 ? 'border-red-500 bg-red-50 dark:bg-red-900/20' : 'border-yellow-500 bg-yellow-50 dark:bg-yellow-900/20'}` : ''}`}>
          <button
            onClick={() => setShowExpiringSection(!showExpiringSection)}
            className="w-full flex items-center justify-between"
          >
            <div className="flex items-center gap-3">
              <span className={`${expiringAttachments.expired_count > 0 ? 'text-red-500 animate-pulse' : expiringAttachments.expiring_count > 0 ? 'text-yellow-500' : 'text-green-500'}`}>
                {expiringAttachments.total_count > 0 ? SettingsIcons.warning : SettingsIcons.document}
              </span>
              <div className="text-left">
                <h3 className={`text-sm font-medium ${expiringAttachments.expired_count > 0 ? 'text-red-600 dark:text-red-400' : expiringAttachments.expiring_count > 0 ? 'text-yellow-600 dark:text-yellow-400' : ''}`}>
                  {expiringAttachments.expired_count > 0 ? (
                    <span className="animate-pulse">{t('settings.documentsExpired') || 'Documents Expired!'}</span>
                  ) : expiringAttachments.expiring_count > 0 ? (
                    t('settings.documentsExpiringSoon') || 'Documents Expiring Soon'
                  ) : (
                    t('settings.documentExpiry') || 'Document Expiry'
                  )}
                </h3>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {expiringAttachments.total_count === 0 ? (
                    <span className="text-green-600 dark:text-green-400">{t('settings.noExpiringDocuments') || 'No expiring documents'}</span>
                  ) : (
                    <>
                      {expiringAttachments.expired_count > 0 && (
                        <span className="text-red-500 font-medium">{expiringAttachments.expired_count} {t('settings.expired') || 'expired'}</span>
                      )}
                      {expiringAttachments.expired_count > 0 && expiringAttachments.expiring_count > 0 && ' · '}
                      {expiringAttachments.expiring_count > 0 && (
                        <span className="text-yellow-600 dark:text-yellow-400">{expiringAttachments.expiring_count} {t('settings.expiringSoon') || 'expiring soon'}</span>
                      )}
                    </>
                  )}
                </p>
              </div>
            </div>
            <span className="text-[var(--color-text-muted)]">
              {showExpiringSection ? SettingsIcons.chevronUp : SettingsIcons.chevronDown}
            </span>
          </button>
          
          {showExpiringSection && expiringAttachments.total_count > 0 && (
            <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
              {/* Expired Documents */}
              {expiringAttachments.expired.length > 0 && (
                <div className="mb-4">
                  <p className="text-xs font-medium text-red-600 dark:text-red-400 uppercase tracking-wide mb-2 flex items-center gap-1">
                    <span className="animate-pulse">●</span>
                    {t('settings.expiredDocuments') || 'Expired Documents'}
                  </p>
                  <div className="space-y-2">
                    {expiringAttachments.expired.map(attachment => (
                      <div 
                        key={attachment.id}
                        className="flex items-center gap-3 p-2 rounded-lg bg-red-100 dark:bg-red-900/30 cursor-pointer hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
                        onClick={() => navigate(`/vehicles/${attachment.vehicle_id}/documents`)}
                      >
                        <span className="text-red-500">
                          {SettingsIcons.document}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{attachment.filename}</p>
                          <p className="text-2xs text-red-600 dark:text-red-400">
                            {t('settings.expiredOn') || 'Expired on'} {formatDate(attachment.expires_at)}
                          </p>
                        </div>
                        <span className="text-[var(--color-text-muted)]">
                          {SettingsIcons.chevronRight}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Expiring Soon Documents */}
              {expiringAttachments.expiring_soon.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-yellow-600 dark:text-yellow-400 uppercase tracking-wide mb-2 flex items-center gap-1">
                    <span className="text-yellow-500">{SettingsIcons.clock}</span>
                    {t('settings.expiringSoonDocuments') || 'Expiring Soon'}
                  </p>
                  <div className="space-y-2">
                    {expiringAttachments.expiring_soon.map(attachment => {
                      const daysLeft = Math.ceil((new Date(attachment.expires_at) - new Date()) / (1000 * 60 * 60 * 24))
                      return (
                        <div 
                          key={attachment.id}
                          className="flex items-center gap-3 p-2 rounded-lg bg-yellow-100 dark:bg-yellow-900/30 cursor-pointer hover:bg-yellow-200 dark:hover:bg-yellow-900/50 transition-colors"
                          onClick={() => navigate(`/vehicles/${attachment.vehicle_id}/documents`)}
                        >
                          <span className="text-yellow-500">
                            {SettingsIcons.document}
                          </span>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{attachment.filename}</p>
                            <p className="text-2xs text-yellow-600 dark:text-yellow-400">
                              {daysLeft <= 0 
                                ? (t('settings.expiresToday') || 'Expires today')
                                : daysLeft === 1 
                                  ? (t('settings.expiresTomorrow') || 'Expires tomorrow')
                                  : `${t('settings.expiresIn') || 'Expires in'} ${daysLeft} ${t('settings.days') || 'days'}`
                              }
                            </p>
                          </div>
                          <span className="text-[var(--color-text-muted)]">
                            {SettingsIcons.chevronRight}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      
      {/* Language & Region */}
      <div className="card mb-4">
        <h3 className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide mb-3">
          {t('settings.languageRegion')}
        </h3>
        
        <div className="space-y-3">
          {/* Language Selector */}
          <div className="flex items-center justify-between py-2">
            <div className="flex items-center gap-3">
              <span className="text-[var(--color-text-muted)]">
                {SettingsIcons.language}
              </span>
              <div>
                <span className="text-sm">{t('settings.language')}</span>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {t('settings.languageDesc')}
                </p>
              </div>
            </div>
          </div>
          
          {/* Language Options */}
          <div className="flex gap-2 flex-wrap">
            {supportedLanguages.map(lang => (
              <button
                key={lang}
                onClick={() => setLanguage(lang)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                  language === lang
                    ? 'bg-[var(--color-accent)] text-white shadow-md'
                    : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]/80'
                }`}
              >
                <span>{languageNames[lang]?.flag}</span>
                <span>{languageNames[lang]?.native}</span>
              </button>
            ))}
          </div>
          
          {/* Currency Display */}
          <div className="flex items-center justify-between py-2 border-t border-[var(--color-border)] mt-2 pt-3">
            <div className="flex items-center gap-3">
              <span className="text-lg w-5 h-5 flex items-center justify-center text-[var(--color-text-muted)]">
                {currency.symbol === 'lei' ? '₽' : currency.symbol}
              </span>
              <div>
                <span className="text-sm">{t('settings.currency')}</span>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {t('settings.currencyDesc')}
                </p>
              </div>
            </div>
            <span className="text-sm font-medium text-[var(--color-accent)]">
              {currency.code} ({currency.symbol})
            </span>
          </div>
        </div>
      </div>
      
      {/* Appearance */}
      <div className="card mb-4">
        <h3 className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide mb-3">
          {t('settings.appearance')}
        </h3>
        
        <div className="flex items-center justify-between py-2">
          <div className="flex items-center gap-3">
            <span className="text-[var(--color-text-muted)]">
              {theme === 'dark' ? SettingsIcons.darkMode : SettingsIcons.lightMode}
            </span>
            <span className="text-sm">{t('settings.theme')}</span>
          </div>
          
          <div className="flex bg-[var(--color-bg-tertiary)] rounded-lg p-1">
            {['light', 'dark'].map(themeOption => (
              <button
                key={themeOption}
                onClick={() => setTheme(themeOption)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors capitalize ${
                  theme === themeOption 
                    ? 'bg-[var(--color-bg-card)] shadow-sm' 
                    : 'text-[var(--color-text-secondary)]'
                }`}
              >
                {t(`settings.${themeOption}`)}
              </button>
            ))}
          </div>
        </div>
      </div>
      
      {/* Notifications */}
      <div className="card mb-4">
        <h3 className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide mb-3">
          {t('settings.notifications')}
        </h3>
        
        <div className="space-y-1">
          <div className="flex items-center justify-between py-2">
            <div className="flex items-center gap-3">
              <span className={pushDenied ? 'text-red-400' : 'text-[var(--color-text-muted)]'}>
                {SettingsIcons.bell}
              </span>
              <div>
                <span className="text-sm">{t('settings.pushNotifications')}</span>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {pushDenied 
                    ? (t('settings.pushBlockedDesc') || 'Blocked in browser settings')
                    : !pushSupported 
                      ? (t('settings.pushNotSupportedDesc') || 'Not supported in this browser')
                      : t('settings.pushNotificationsDesc')
                  }
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {pushSubscribed && pushGranted && (
                <button
                  onClick={handleResubscribe}
                  disabled={pushLoading}
                  className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-accent)] hover:underline disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] rounded"
                  title={t('settings.pushResubscribeHint') || 'Refresh your subscription if notifications stop arriving'}
                >
                  {t('settings.pushResubscribe') || 'Re-subscribe'}
                </button>
              )}
              {pushSubscribed && (
                <button
                  onClick={handleTestNotification}
                  className="text-xs text-[var(--color-accent)] hover:underline focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] rounded"
                >
                  {t('settings.test') || 'Test'}
                </button>
              )}
              <label className={`relative inline-flex items-center ${pushSupported && !pushDenied ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'}`}>
                <input
                  type="checkbox"
                  checked={pushSubscribed}
                  onChange={handlePushToggle}
                  disabled={!pushSupported || pushDenied || pushLoading}
                  className="sr-only peer"
                />
                <div className={`w-10 h-6 bg-[var(--color-bg-tertiary)] peer-focus:ring-2 peer-focus:ring-[var(--color-accent)] rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--color-accent)] ${pushLoading ? 'animate-pulse' : ''}`}></div>
              </label>
            </div>
          </div>
        </div>
      </div>
      
      {/* Email Notifications - Collapsible */}
      <div className="card mb-4">
        <button
          onClick={() => setShowEmailSettings(!showEmailSettings)}
          className="w-full flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <span className={emailSettings.notifications_enabled && emailSettings.email_enabled_on_server ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-muted)]'}>
              {SettingsIcons.email}
            </span>
            <div className="text-left">
              <h3 className="text-sm font-medium">{t('settings.emailNotifications')}</h3>
              <p className="text-2xs text-[var(--color-text-muted)]">
                {emailSettings.email_enabled_on_server 
                  ? t('settings.emailNotificationsDesc')
                  : (t('settings.emailNotConfigured') || 'Email not configured on server')
                }
              </p>
            </div>
          </div>
          <span className="text-[var(--color-text-muted)]">
            {showEmailSettings ? SettingsIcons.chevronUp : SettingsIcons.chevronDown}
          </span>
        </button>
        
        {showEmailSettings && (
          <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
            {/* Master Toggle */}
            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-sm">{t('settings.enableEmailAlerts') || 'Enable Email Alerts'}</span>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {emailSettings.notifications_enabled 
                    ? (t('settings.emailAlertsEnabled') || 'You will receive email notifications')
                    : (t('settings.emailAlertsDisabled') || 'Email notifications are disabled')
                  }
                </p>
              </div>
              <div className="flex items-center gap-2">
                {emailSettings.notifications_enabled && emailSettings.email_enabled_on_server && (
                  <button
                    onClick={handleSendTestEmail}
                    disabled={sendingTestEmail}
                    className="text-xs text-[var(--color-accent)] hover:underline disabled:opacity-50"
                  >
                    {sendingTestEmail ? '...' : (t('settings.test') || 'Test')}
                  </button>
                )}
                <label className={`relative inline-flex items-center ${emailSettings.email_enabled_on_server ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'}`}>
                  <input
                    type="checkbox"
                    checked={emailSettings.notifications_enabled}
                    onChange={(e) => handleEmailSettingChange('notifications_enabled', e.target.checked)}
                    disabled={!emailSettings.email_enabled_on_server}
                    className="sr-only peer"
                  />
                  <div className="w-10 h-6 bg-[var(--color-bg-tertiary)] peer-focus:ring-2 peer-focus:ring-[var(--color-accent)] rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--color-accent)]"></div>
                </label>
              </div>
            </div>
            
            {/* Expanded settings when enabled */}
            {emailSettings.notifications_enabled && emailSettings.email_enabled_on_server && (
              <div className="mt-4 space-y-2">
                {/* Custom Notification Email - GDPR */}
                <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3 mb-4">
                  <p className="text-2xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mb-2">
                    {t('settings.notifEmailTitle') || 'Custom Notification Email'}
                  </p>
                  <p className="text-2xs text-[var(--color-text-muted)] mb-3">
                    {t('settings.notifEmailDesc') || 'Set a separate email address to receive notifications. Your email is encrypted and stored securely.'}
                  </p>
                  
                  {hasNotifEmail && notifEmailVerified ? (
                    /* Verified state */
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-medium bg-green-500/10 text-green-600">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd"/></svg>
                          {t('settings.notifEmailStatusVerified') || 'Verified'}
                        </span>
                        <span className="text-sm text-[var(--color-text)]">{notifEmail}</span>
                      </div>
                      <button
                        onClick={handleRemoveNotificationEmail}
                        className="text-xs text-red-500 hover:underline"
                      >
                        {t('settings.notifEmailRemove') || 'Remove & Revoke Consent'}
                      </button>
                    </div>
                  ) : hasNotifEmail && !notifEmailVerified ? (
                    /* Pending verification state */
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-medium bg-yellow-500/10 text-yellow-600">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd"/></svg>
                          {t('settings.notifEmailStatusPending') || 'Pending Verification'}
                        </span>
                      </div>
                      <p className="text-2xs text-[var(--color-text-muted)]">
                        {t('settings.notifEmailCheckInbox') || 'Check your inbox and click the verification link.'}
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={handleResendVerification}
                          disabled={notifEmailResending}
                          className="text-xs text-[var(--color-accent)] hover:underline disabled:opacity-50"
                        >
                          {notifEmailResending ? '...' : (t('settings.notifEmailResend') || 'Resend Verification')}
                        </button>
                        <button
                          onClick={handleRemoveNotificationEmail}
                          className="text-xs text-red-500 hover:underline"
                        >
                          {t('settings.notifEmailRemove') || 'Remove & Revoke Consent'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* Not set state - input form */
                    <div className="space-y-2">
                      <input
                        type="email"
                        value={notifEmail}
                        onChange={(e) => setNotifEmail(e.target.value)}
                        placeholder={t('settings.notifEmailPlaceholder') || 'your-alerts@example.com'}
                        className="w-full bg-[var(--color-bg-input)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                      />
                      <label className="flex items-start gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={notifEmailConsent}
                          onChange={(e) => setNotifEmailConsent(e.target.checked)}
                          className="w-4 h-4 mt-0.5 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                        />
                        <span className="text-2xs text-[var(--color-text-muted)]">
                          {t('settings.notifEmailConsent') || 'I consent to receiving email notifications at this address. My email will be encrypted and I can withdraw consent at any time.'}
                        </span>
                      </label>
                      <button
                        onClick={handleSetNotificationEmail}
                        disabled={!notifEmail || !notifEmailConsent || notifEmailSaving}
                        className="px-3 py-1.5 rounded-lg bg-[var(--color-accent)] text-white text-xs font-medium disabled:opacity-50"
                      >
                        {notifEmailSaving ? '...' : (t('settings.notifEmailSave') || 'Set & Verify Email')}
                      </button>
                    </div>
                  )}
                  
                  {/* Consent History */}
                  <button
                    onClick={handleLoadConsentHistory}
                    className="mt-2 text-2xs text-[var(--color-text-muted)] hover:underline"
                  >
                    {showConsentHistory
                      ? (t('settings.notifEmailHideHistory') || 'Hide consent history')
                      : (t('settings.notifEmailShowHistory') || 'View consent history')
                    }
                  </button>
                  {showConsentHistory && consentHistory.length > 0 && (
                    <div className="mt-2 space-y-1 max-h-32 overflow-y-auto">
                      {consentHistory.map((entry, i) => (
                        <div key={i} className="text-2xs text-[var(--color-text-muted)] flex justify-between">
                          <span className="capitalize">{entry.action}</span>
                          <span>{formatDateTime(entry.created_at)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {showConsentHistory && consentHistory.length === 0 && (
                    <p className="mt-2 text-2xs text-[var(--color-text-muted)]">
                      {t('settings.notifEmailNoHistory') || 'No consent history yet.'}
                    </p>
                  )}
                </div>
                
                {/* Alert Types */}
                <p className="text-2xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mb-1">
                  {t('settings.alertTypes') || 'Alert Types'}
                </p>
                <p className="text-2xs text-[var(--color-text-muted)] mb-2">
                  {t('settings.alertTypesDesc') || 'Sent as a daily digest when items are due within your alert window. Toggle types below to control what appears in the digest.'}
                </p>
                
                <label className="flex items-center justify-between py-1 cursor-pointer">
                  <span className="text-sm">{t('settings.insuranceAlerts') || 'Insurance Expiry'}</span>
                  <input
                    type="checkbox"
                    checked={emailSettings.email_insurance_alerts}
                    onChange={(e) => handleEmailSettingChange('email_insurance_alerts', e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                  />
                </label>
                
                <label className="flex items-center justify-between py-1 cursor-pointer">
                  <span className="text-sm">{t('settings.taxAlerts') || 'Road Tax Due'}</span>
                  <input
                    type="checkbox"
                    checked={emailSettings.email_tax_alerts}
                    onChange={(e) => handleEmailSettingChange('email_tax_alerts', e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                  />
                </label>
                
                <label className="flex items-center justify-between py-1 cursor-pointer">
                  <span className="text-sm">{t('settings.serviceAlerts') || 'Service & Maintenance'}</span>
                  <input
                    type="checkbox"
                    checked={emailSettings.email_service_alerts}
                    onChange={(e) => handleEmailSettingChange('email_service_alerts', e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                  />
                </label>
                
                <label className="flex items-center justify-between py-1 cursor-pointer">
                  <span className="text-sm">{t('settings.reminderAlerts') || 'Reminders'}</span>
                  <input
                    type="checkbox"
                    checked={emailSettings.email_reminder_alerts}
                    onChange={(e) => handleEmailSettingChange('email_reminder_alerts', e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                  />
                </label>
                
                <label className="flex items-center justify-between py-1 cursor-pointer">
                  <span className="text-sm">{t('settings.smartAlerts') || 'Smart Recommendations'}</span>
                  <input
                    type="checkbox"
                    checked={emailSettings.email_smart_alerts}
                    onChange={(e) => handleEmailSettingChange('email_smart_alerts', e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                  />
                </label>

                {/* Security Alerts */}
                <p className="text-2xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mt-4 mb-1">
                  {t('settings.securityAlerts') || 'Security Alerts'}
                </p>

                <div className="flex items-start justify-between py-1 gap-4">
                  <div>
                    <span className="text-sm">{t('settings.loginAlerts') || 'Suspicious Login Alerts'}</span>
                    <p className="text-2xs text-[var(--color-text-muted)] mt-0.5">
                      {t('settings.loginAlertsDesc') || 'Get notified when a login occurs from an unrecognised location or device. Your IP address is used locally for geolocation — never shared with third parties.'}
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={emailSettings.login_alerts_enabled}
                    onChange={(e) => handleEmailSettingChange('login_alerts_enabled', e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)] mt-0.5 shrink-0"
                  />
                </div>
                
                {/* Reports */}
                <p className="text-2xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mt-4 mb-2">
                  {t('settings.scheduledReports') || 'Scheduled Reports'}
                </p>

                <label className="flex items-center justify-between py-1 cursor-pointer">
                  <span className="text-sm">{t('settings.dailyDigest') || 'Daily Digest'}</span>
                  <input
                    type="checkbox"
                    checked={emailSettings.daily_alerts_enabled}
                    onChange={(e) => handleEmailSettingChange('daily_alerts_enabled', e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                  />
                </label>

                <label className="flex items-center justify-between py-1 cursor-pointer">
                  <span className="text-sm">{t('settings.weeklyReport') || 'Weekly Summary'}</span>
                  <input
                    type="checkbox"
                    checked={emailSettings.weekly_report_enabled}
                    onChange={(e) => handleEmailSettingChange('weekly_report_enabled', e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                  />
                </label>
                
                <label className="flex items-center justify-between py-1 cursor-pointer">
                  <span className="text-sm">{t('settings.monthlyReport') || 'Monthly Report'}</span>
                  <input
                    type="checkbox"
                    checked={emailSettings.monthly_report_enabled}
                    onChange={(e) => handleEmailSettingChange('monthly_report_enabled', e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                  />
                </label>
                
                {/* Alert timing */}
                <p className="text-2xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mt-4 mb-2">
                  {t('settings.alertTiming') || 'Alert Timing'}
                </p>
                
                <div className="flex items-center justify-between py-1">
                  <span className="text-sm">{t('settings.alertDaysBefore') || 'Days before due date'}</span>
                  <select
                    value={emailSettings.alert_days_before}
                    onChange={(e) => handleEmailSettingChange('alert_days_before', parseInt(e.target.value))}
                    className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-2 py-1 text-sm"
                  >
                    <option value={7}>7 {t('common.days') || 'days'}</option>
                    <option value={14}>14 {t('common.days') || 'days'}</option>
                    <option value={30}>30 {t('common.days') || 'days'}</option>
                  </select>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Calendar Sync - Collapsible */}
      <div className="card mb-4">
        <button
          onClick={() => setShowCalendarSettings(!showCalendarSettings)}
          className="w-full flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <span className={calendarSettings.enabled ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-muted)]'}>
              {SettingsIcons.calendar}
            </span>
            <div className="text-left">
              <h3 className="text-sm font-medium">{t('settings.calendarSync') || 'Calendar Sync'}</h3>
              <p className="text-2xs text-[var(--color-text-muted)]">
                {t('settings.calendarSyncDesc') || 'Sync entries to Google Calendar, Nextcloud, etc.'}
              </p>
            </div>
          </div>
          <span className="text-[var(--color-text-muted)]">
            {showCalendarSettings ? SettingsIcons.chevronUp : SettingsIcons.chevronDown}
          </span>
        </button>
        
        {showCalendarSettings && (
          <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
            {/* Master Toggle */}
            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-sm">{t('settings.enableCalendarSync') || 'Enable Calendar Sync'}</span>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {calendarSettings.enabled 
                    ? (t('settings.calendarSyncEnabled') || 'New entries will be synced automatically')
                    : (t('settings.calendarSyncDisabled') || 'Calendar sync is disabled')
                  }
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={calendarSettings.enabled}
                  onChange={(e) => setCalendarSettings(prev => ({ ...prev, enabled: e.target.checked }))}
                  className="sr-only peer"
                />
                <div className="w-10 h-6 bg-[var(--color-bg-tertiary)] peer-focus:ring-2 peer-focus:ring-[var(--color-accent)] rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--color-accent)]"></div>
              </label>
            </div>
            
            {/* Calendar Configuration */}
            <div className="mt-4 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-[var(--color-text-muted)]">
                  {t('settings.calendarSourcesConfigured') || 'Configured sources'}: {(calendarSettings.sources || []).length}
                </span>
                <button
                  onClick={addCalendarSource}
                  className="px-3 py-1.5 rounded-lg bg-[var(--color-accent)]/10 text-[var(--color-accent)] text-xs font-medium hover:bg-[var(--color-accent)]/20"
                >
                  + {t('settings.addCalendarSource') || 'Add Source'}
                </button>
              </div>

              {(calendarSettings.sources || []).length > 0 && (
                <div className="space-y-2">
                  {(calendarSettings.sources || []).map((source) => (
                    <div key={source.id} className={`rounded-lg border p-2 ${selectedCalendarSourceId === source.id ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/5' : 'border-[var(--color-border)]'}`}>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setSelectedCalendarSourceId(source.id)}
                          className="flex-1 min-w-0 text-left"
                        >
                          <div className="text-sm font-medium truncate">{source.name || source.provider || 'Source'}</div>
                          <div className="text-2xs text-[var(--color-text-muted)] truncate">{source.url || t('settings.calendarUrlNotSet') || 'URL not set'}</div>
                        </button>
                        <label className="flex items-center gap-1 text-xs text-[var(--color-text-muted)] shrink-0">
                          <input
                            type="checkbox"
                            checked={source.enabled !== false}
                            onChange={(e) => updateCalendarSources((sources) => sources.map(item => item.id === source.id ? { ...item, enabled: e.target.checked } : item))}
                          />
                          {t('settings.enabled') || 'Enabled'}
                        </label>
                        <button
                          onClick={() => removeCalendarSource(source.id)}
                          className="px-2 py-1 text-xs text-red-500 hover:bg-red-500/10 rounded shrink-0"
                          disabled={(calendarSettings.sources || []).length <= 1}
                        >
                          {t('settings.removeSource') || 'Remove'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {selectedCalendarSource && (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      {t('settings.sourceName') || 'Source Name'}
                    </label>
                    <input
                      type="text"
                      value={selectedCalendarSource.name || ''}
                      onChange={(e) => handleCalendarSettingChange('name', e.target.value)}
                      className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                    />
                  </div>

              {/* Provider Selection */}
              <div>
                <label className="block text-sm font-medium mb-2">
                  {t('settings.calendarProvider') || 'Calendar Provider'}
                </label>
                <select
                  value={selectedCalendarSource.provider || ''}
                  onChange={(e) => handleCalendarProviderChange(e.target.value)}
                  className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">{t('settings.selectProvider') || 'Select a provider...'}</option>
                  {calendarProviders.map(provider => (
                    <option key={provider.id} value={provider.id}>{provider.name}</option>
                  ))}
                </select>
              </div>
              
              {/* Setup Guide */}
              {selectedCalendarSource.provider && (
                <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
                  <button
                    onClick={() => setShowSetupGuide(!showSetupGuide)}
                    className="w-full flex items-center justify-between text-sm font-medium"
                  >
                    <span className="flex items-center gap-2">
                      {SettingsIcons.info}
                      {t('settings.setupGuide') || 'Setup Guide'}
                    </span>
                    <span className="text-[var(--color-text-muted)]">
                      {showSetupGuide ? SettingsIcons.chevronUp : SettingsIcons.chevronDown}
                    </span>
                  </button>
                  {showSetupGuide && (
                    <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                      {t(calendarProviders.find(p => p.id === selectedCalendarSource.provider)?.setup_guide_key) || t('settings.calendarSetupGuideFallback') || 'Use your provider app-password and CalDAV URL.'}
                    </p>
                  )}
                </div>
              )}
              
              {/* CalDAV URL */}
              {selectedCalendarSource.provider && (
                <div>
                  <label className="block text-sm font-medium mb-2">
                    {t('settings.calendarUrl') || 'CalDAV URL'}
                  </label>
                  <input
                    type="url"
                    value={selectedCalendarSource.url || ''}
                    onChange={(e) => handleCalendarSettingChange('url', e.target.value)}
                    placeholder={calendarProviders.find(p => p.id === selectedCalendarSource.provider)?.default_url || 'https://...'}
                    className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                  />
                </div>
              )}
              
              {/* Username */}
              {selectedCalendarSource.provider && (
                <div>
                  <label className="block text-sm font-medium mb-2">
                    {t('settings.calendarUsername') || 'Username / Email'}
                  </label>
                  <input
                    type="text"
                    value={selectedCalendarSource.username || ''}
                    onChange={(e) => handleCalendarSettingChange('username', e.target.value)}
                    placeholder={selectedCalendarSource.provider === 'google' ? 'your.email@gmail.com' : 'username'}
                    className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                  />
                </div>
              )}
              
              {/* Password / App Password */}
              {selectedCalendarSource.provider && (
                <div>
                  <label className="block text-sm font-medium mb-2">
                    {selectedCalendarSource.provider === 'google' 
                      ? (t('settings.googleAppPassword') || 'App Password (16 characters)')
                      : (t('settings.calendarPassword') || 'Password / App Password')
                    }
                  </label>
                  <input
                    type="password"
                    value={selectedCalendarSource.password || ''}
                    onChange={(e) => handleCalendarSettingChange('password', e.target.value)}
                    placeholder="••••••••••••••••"
                    className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                  />
                </div>
              )}
              
              {/* Test Connection & Get Calendars */}
              {selectedCalendarSource.provider && selectedCalendarSource.url && selectedCalendarSource.username && (
                <button
                  onClick={handleTestCalendarConnection}
                  disabled={calendarTesting}
                  className="w-full bg-[var(--color-accent)] text-white rounded-lg px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {calendarTesting ? (
                    <>
                      <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      {t('settings.testing') || 'Testing...'}
                    </>
                  ) : (
                    <>
                      {SettingsIcons.link}
                      {t('settings.testConnection') || 'Test Connection & Get Calendars'}
                    </>
                  )}
                </button>
              )}
              
              {/* Calendar Selection */}
              {availableCalendars.length > 0 && (
                <div>
                  <label className="block text-sm font-medium mb-2">
                    {t('settings.selectCalendar') || 'Select Calendar'}
                  </label>
                  <select
                    value={selectedCalendarSource.calendar_id || ''}
                    onChange={(e) => handleCalendarSettingChange('calendar_id', e.target.value)}
                    className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                  >
                    {availableCalendars.map(cal => (
                      <option key={cal.id} value={cal.id}>{cal.name}</option>
                    ))}
                  </select>
                </div>
              )}
              
              {/* Save Button */}
              {selectedCalendarSource.provider && (
                <button
                  onClick={handleSaveCalendarSettings}
                  disabled={calendarLoading}
                  className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-4 py-2 text-sm font-medium hover:bg-[var(--color-bg-secondary)] disabled:opacity-50"
                >
                  {calendarLoading ? (t('common.saving') || 'Saving...') : (t('settings.saveCalendarSettings') || 'Save Calendar Settings')}
                </button>
              )}
              
              {/* Sync All Button */}
              {calendarSettings.enabled && selectedCalendarSource?.calendar_id && (
                <div className="pt-4 border-t border-[var(--color-border)]">
                  <p className="text-2xs text-[var(--color-text-muted)] mb-2">
                    {t('settings.syncAllDesc') || 'Sync all existing services, reminders, insurance, and tax entries to your calendar'}
                  </p>
                  <button
                    onClick={handleSyncAllToCalendar}
                    disabled={calendarSyncing}
                    className="w-full bg-green-500 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-green-600 disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {calendarSyncing ? (
                      <>
                        <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        {t('settings.syncing') || 'Syncing...'}
                      </>
                    ) : (
                      <>
                        {SettingsIcons.refresh}
                        {t('settings.syncAllToCalendar') || 'Sync All Entries to Calendar'}
                      </>
                    )}
                  </button>
                </div>
              )}
                </>
              )}
            </div>
          </div>
        )}
      </div>
      
      {/* PDF Reports - Collapsible */}
      <div className="card mb-4">
        <button
          onClick={() => setShowReportsSection(!showReportsSection)}
          className="w-full flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <span className="text-[var(--color-accent)]">
              {SettingsIcons.chartBar}
            </span>
            <div className="text-left">
              <h3 className="text-sm font-medium">{t('settings.reports') || 'PDF Reports'}</h3>
              <p className="text-2xs text-[var(--color-text-muted)]">
                {t('settings.reportsDesc') || 'Export vehicle expense reports as PDF'}
              </p>
            </div>
          </div>
          <span className="text-[var(--color-text-muted)]">
            {showReportsSection ? SettingsIcons.chevronUp : SettingsIcons.chevronDown}
          </span>
        </button>
        
        {showReportsSection && (
          <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
            {reportLoading && reportVehicles.length === 0 ? (
              <div className="flex items-center justify-center py-4">
                <svg className="animate-spin h-5 w-5 text-[var(--color-accent)]" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Vehicle Selection */}
                <div>
                  <label className="block text-sm font-medium mb-2">
                    {t('settings.selectVehicle') || 'Select Vehicle'}
                  </label>
                  <select
                    value={reportSettings.vehicleId}
                    onChange={(e) => handleReportSettingChange('vehicleId', e.target.value)}
                    className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                  >
                    <option value="all">{t('settings.allVehicles') || 'All Vehicles'}</option>
                    {reportVehicles.map(vehicle => (
                      <option key={vehicle.id} value={vehicle.id}>
                        {vehicle.make} {vehicle.model} {vehicle.license_plate ? `(${vehicle.license_plate})` : ''}
                      </option>
                    ))}
                  </select>
                </div>
                
                {/* Period Selection */}
                <div>
                  <label className="block text-sm font-medium mb-2">
                    {t('settings.reportPeriod') || 'Report Period'}
                  </label>
                  <select
                    value={reportSettings.period}
                    onChange={(e) => handleReportSettingChange('period', e.target.value)}
                    className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                  >
                    {reportPeriods.map(period => (
                      <option key={period.id} value={period.id}>
                        {t(`settings.period_${period.id}`) || period.name}
                      </option>
                    ))}
                  </select>
                </div>
                
                {/* Year Selection (for year and custom periods) */}
                {(reportSettings.period === 'year' || reportSettings.period === 'custom') && (
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      {t('settings.selectYear') || 'Select Year'}
                    </label>
                    <select
                      value={reportSettings.year}
                      onChange={(e) => handleReportSettingChange('year', parseInt(e.target.value))}
                      className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                    >
                      {reportYears.map(year => (
                        <option key={year} value={year}>{year}</option>
                      ))}
                    </select>
                  </div>
                )}
                
                {/* Month Selection (for custom period) */}
                {reportSettings.period === 'custom' && (
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      {t('settings.selectMonth') || 'Select Month'}
                    </label>
                    <select
                      value={reportSettings.month}
                      onChange={(e) => handleReportSettingChange('month', parseInt(e.target.value))}
                      className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                    >
                      {reportMonths.map(month => (
                        <option key={month.id} value={month.id}>
                          {t(`calendar.months.${month.name.toLowerCase()}`) || month.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                
                {/* Preview Button */}
                <button
                  onClick={handlePreviewReport}
                  disabled={reportLoading || reportVehicles.length === 0}
                  className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-4 py-2 text-sm font-medium hover:bg-[var(--color-bg-secondary)] disabled:opacity-50"
                >
                  {reportLoading ? (t('common.loading') || 'Loading...') : (t('settings.previewReport') || 'Preview Report Info')}
                </button>
                
                {/* Preview Info */}
                {reportPreview && (
                  <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-[var(--color-text-muted)]">{t('settings.periodLabel') || 'Period'}:</span>
                      <span className="text-sm font-medium">{reportPreview.period_label}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-[var(--color-text-muted)]">{t('settings.vehiclesIncluded') || 'Vehicles'}:</span>
                      <span className="text-sm font-medium">{reportPreview.vehicle_count} {t('settings.vehiclesCount') || 'vehicle(s)'}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-[var(--color-text-muted)]">{t('settings.totalEntries') || 'Total Entries'}:</span>
                      <span className="text-sm font-medium">{reportPreview.entry_counts?.total || 0}</span>
                    </div>
                    
                    {/* Entry breakdown */}
                    <div className="pt-2 border-t border-[var(--color-border)]">
                      <p className="text-2xs text-[var(--color-text-muted)] uppercase tracking-wide mb-2">
                        {t('settings.breakdown') || 'Breakdown'}
                      </p>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-[var(--color-text-muted)]">⛽ {t('nav.fuel') || 'Fuel'}:</span>
                          <span>{reportPreview.entry_counts?.fuel || 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[var(--color-text-muted)]">🔧 {t('settings.service') || 'Service'}:</span>
                          <span>{reportPreview.entry_counts?.service || 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[var(--color-text-muted)]">🛠️ {t('settings.repairs') || 'Repairs'}:</span>
                          <span>{reportPreview.entry_counts?.repair || 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[var(--color-text-muted)]">📋 {t('settings.tax') || 'Tax'}:</span>
                          <span>{reportPreview.entry_counts?.tax || 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[var(--color-text-muted)]">🅿️ {t('settings.parking') || 'Parking'}:</span>
                          <span>{reportPreview.entry_counts?.parking || 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[var(--color-text-muted)]">🛡️ {t('settings.insurance') || 'Insurance'}:</span>
                          <span>{reportPreview.entry_counts?.insurance || 0}</span>
                        </div>
                      </div>
                    </div>
                    
                    {/* Total cost */}
                    <div className="pt-2 border-t border-[var(--color-border)]">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{t('settings.totalCost') || 'Total Cost'}:</span>
                        <span className="text-lg font-bold text-[var(--color-accent)]">
                          {(reportPreview.totals?.grand_total || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {reportPreview.currency}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
                
                {/* Generate PDF Button */}
                <button
                  onClick={handleGenerateReport}
                  disabled={reportGenerating || reportVehicles.length === 0}
                  className="w-full bg-[var(--color-accent)] text-white rounded-lg px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {reportGenerating ? (
                    <>
                      <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      {t('settings.generating') || 'Generating PDF...'}
                    </>
                  ) : (
                    <>
                      {SettingsIcons.download}
                      {t('settings.downloadReport') || 'Download PDF Report'}
                    </>
                  )}
                </button>
                
                {reportVehicles.length === 0 && !reportLoading && (
                  <p className="text-sm text-[var(--color-text-muted)] text-center">
                    {t('settings.noVehiclesForReport') || 'Add vehicles to generate reports'}
                  </p>
                )}

                {/* F05 — Shareable read-only link */}
                {reportVehicles.length > 0 && (
                  <div className="pt-4 mt-2 border-t border-[var(--color-border)] space-y-3">
                    <div>
                      <p className="text-sm font-medium">{t('reportShare.title') || 'Share a read-only link'}</p>
                      <p className="text-2xs text-[var(--color-text-muted)] mt-0.5">
                        {t('reportShare.desc') || 'Anyone with the link can view this report (no login). The link expires and can be revoked.'}
                      </p>
                    </div>

                    <div className="flex items-end gap-2">
                      <div className="flex-1">
                        <label className="block text-2xs text-[var(--color-text-muted)] mb-1" htmlFor="shareExpiry">
                          {t('reportShare.expiresIn') || 'Expires in'}
                        </label>
                        <select
                          id="shareExpiry"
                          value={shareExpiryDays}
                          onChange={(e) => setShareExpiryDays(parseInt(e.target.value))}
                          className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-sm"
                        >
                          <option value={1}>{t('reportShare.days1') || '1 day'}</option>
                          <option value={7}>{t('reportShare.days7') || '7 days'}</option>
                          <option value={30}>{t('reportShare.days30') || '30 days'}</option>
                          <option value={90}>{t('reportShare.days90') || '90 days'}</option>
                        </select>
                      </div>
                      <button
                        onClick={handleCreateShare}
                        disabled={shareCreating}
                        className="px-4 py-2 rounded-lg bg-[var(--color-bg-tertiary)] text-sm font-medium hover:opacity-90 disabled:opacity-50 whitespace-nowrap"
                      >
                        {shareCreating ? (t('reportShare.creating') || 'Creating…') : (t('reportShare.createButton') || 'Create link')}
                      </button>
                    </div>

                    {/* Freshly-created link — shown ONCE */}
                    {createdShare?.url && (
                      <div className="p-3 rounded-lg bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20 space-y-2">
                        <p className="text-2xs text-[var(--color-text-secondary)]">
                          {t('reportShare.copyNow') || 'Copy this link now — it will not be shown again.'}
                        </p>
                        <div className="flex items-center gap-2">
                          <input
                            readOnly
                            value={createdShare.url}
                            onFocus={(e) => e.target.select()}
                            className="flex-1 min-w-0 px-2 py-1.5 rounded bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-2xs"
                          />
                          <button
                            onClick={() => copyShareLink(createdShare.url)}
                            className="px-3 py-1.5 rounded bg-[var(--color-accent)] text-white text-xs font-medium whitespace-nowrap"
                          >
                            {t('reportShare.copy') || 'Copy'}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Existing links */}
                    {shareLinks.length > 0 && (
                      <ul className="space-y-2">
                        {shareLinks.map((s) => (
                          <li key={s.id} className="flex items-center justify-between gap-2 p-2.5 rounded-lg bg-[var(--color-bg-secondary)]">
                            <div className="min-w-0">
                              <p className="text-xs font-medium truncate">
                                {s.label || `${s.token_prefix}…`}
                                <span className={`ml-2 text-2xs px-1.5 py-0.5 rounded-full ${
                                  s.status === 'active' ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                                  : s.status === 'expired' ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                                  : 'bg-red-500/10 text-red-600 dark:text-red-400'
                                }`}>
                                  {t(`reportShare.status_${s.status}`) || s.status}
                                </span>
                              </p>
                              <p className="text-2xs text-[var(--color-text-muted)] truncate">
                                {(t('reportShare.views') || '{n} views').replace('{n}', String(s.access_count || 0))}
                              </p>
                            </div>
                            {s.status !== 'revoked' && (
                              <button
                                onClick={() => handleRevokeShare(s.id)}
                                className="px-2.5 py-1 rounded text-xs text-red-500 hover:bg-red-500/10 whitespace-nowrap shrink-0"
                              >
                                {t('reportShare.revoke') || 'Revoke'}
                              </button>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Security */}
      <div className="card mb-4">
        <h3 className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide mb-3">
          {t('profile.security') || 'Security'}
        </h3>
        
        <button 
          onClick={() => setShow2FASetup(true)}
          className="flex items-center gap-3 w-full py-2 text-left"
        >
          <span className={user?.two_factor_enabled ? 'text-green-500' : 'text-[var(--color-text-muted)]'}>
            {SettingsIcons.shield}
          </span>
          <div className="flex-1">
            <span className="text-sm">{t('auth.twoFactorAuth') || 'Two-Factor Authentication'}</span>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('profile.addExtraSecurity') || 'Add an extra layer of security'}
            </p>
          </div>
          <span className={`px-2 py-0.5 rounded-full text-2xs font-medium ${
            user?.two_factor_enabled 
              ? 'bg-green-500/10 text-green-500' 
              : 'bg-amber-500/10 text-amber-500'
          }`}>
            {user?.two_factor_enabled ? (t('common.enabled') || 'Enabled') : (t('common.disabled') || 'Disabled')}
          </span>
        </button>
        
        <button 
          onClick={() => setShowSecurityQuestionsSetup(true)}
          className="flex items-center gap-3 w-full py-2 text-left"
        >
          <span className={user?.security_questions_status?.configured ? 'text-green-500' : 'text-[var(--color-text-muted)]'}>
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />
            </svg>
          </span>
          <div className="flex-1">
            <span className="text-sm">{t('securityQuestions.title') || 'Security Questions'}</span>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('securityQuestions.accountRecovery') || 'Account recovery backup option'}
            </p>
          </div>
          <span className={`px-2 py-0.5 rounded-full text-2xs font-medium ${
            user?.security_questions_status?.configured 
              ? 'bg-green-500/10 text-green-500' 
              : 'bg-amber-500/10 text-amber-500'
          }`}>
            {user?.security_questions_status?.configured 
              ? `${user?.security_questions_status?.count || 0} ${t('securityQuestions.configured') || 'Configured'}` 
              : (t('common.notSet') || 'Not Set')}
          </span>
        </button>
        
        <button 
          onClick={() => navigate('/settings/profile')}
          className="flex items-center gap-3 w-full py-2 text-left"
        >
          <span className="text-[var(--color-text-muted)]">
            {SettingsIcons.lock}
          </span>
          <div className="flex-1">
            <span className="text-sm">{t('profile.updateProfile') || 'Update Profile'}</span>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('profile.updateProfileDesc') || 'Avatar, password & account settings'}
            </p>
          </div>
          <span className="text-[var(--color-text-muted)]">
            {SettingsIcons.chevronRight}
          </span>
        </button>
      </div>
      
      {/* Data & Backup */}
      <div className="card mb-4">
        <button
          onClick={() => setShowBackupSettings(!showBackupSettings)}
          className="w-full flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <span className="text-[var(--color-accent)]">
              {SettingsIcons.download}
            </span>
            <div className="text-left">
              <h3 className="text-sm font-medium">{t('settings.dataBackup')}</h3>
              <p className="text-2xs text-[var(--color-text-muted)]">
                {t('backup.description') || 'Auto backups, restore & external sync'}
              </p>
            </div>
          </div>
          <span className="text-[var(--color-text-muted)]">
            {showBackupSettings ? SettingsIcons.chevronUp : SettingsIcons.chevronDown}
          </span>
        </button>
        
        {showBackupSettings && (
          <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
            <BackupSettings />
          </div>
        )}
      </div>

      {/* Sync & Offline status — pending writes, last sync, failures + retry */}
      <div className="mb-4">
        <SyncIndicator variant="card" />
      </div>

      {/* Integrations */}
      <div className="card mb-4">
        <button
          onClick={() => setShowIntegrations(!showIntegrations)}
          className="w-full flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <span className="text-purple-500">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 11a9 9 0 0 1 9 9" /><path d="M4 4a16 16 0 0 1 16 16" /><circle cx="5" cy="19" r="1" />
              </svg>
            </span>
            <div className="text-left">
              <h3 className="text-sm font-medium">{t('integrations.title') || 'Integrations'}</h3>
              <p className="text-2xs text-[var(--color-text-muted)]">
                {t('integrations.description') || 'Gethomepage widget & API access'}
              </p>
            </div>
          </div>
          <span className="text-[var(--color-text-muted)]">
            {showIntegrations ? SettingsIcons.chevronUp : SettingsIcons.chevronDown}
          </span>
        </button>
        
        {showIntegrations && (
          <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
            <IntegrationSettings />
          </div>
        )}
      </div>
      
      {/* Archived Vehicles */}
      <div className="card mb-4">
        <button
          onClick={() => setShowArchiveSection(!showArchiveSection)}
          className="w-full flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <span className="text-[var(--color-text-muted)]">
              {SettingsIcons.archive}
            </span>
            <div className="text-left">
              <h3 className="text-sm font-medium">{t('archive.title') || 'Archived Vehicles'}</h3>
              <p className="text-2xs text-[var(--color-text-muted)]">
                {t('archive.description') || 'View and manage archived vehicles'}
              </p>
            </div>
          </div>
          <span className="text-[var(--color-text-muted)]">
            {showArchiveSection ? SettingsIcons.chevronUp : SettingsIcons.chevronDown}
          </span>
        </button>
        
        {showArchiveSection && (
          <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
            {loadingArchived ? (
              <div className="flex justify-center py-4">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-[var(--color-accent)] border-t-transparent"></div>
              </div>
            ) : archivedVehicles.length === 0 ? (
              <div className="text-center py-6 text-[var(--color-text-muted)]">
                <div className="mb-2">{SettingsIcons.archive}</div>
                <p className="text-sm">{t('archive.empty') || 'No archived vehicles'}</p>
                <p className="text-2xs mt-1">{t('archive.emptyHint') || 'Archived vehicles will appear here'}</p>
              </div>
            ) : (
              <div className="space-y-3">
                {archivedVehicles.map(vehicle => (
                  <div 
                    key={vehicle.id} 
                    className="flex items-center gap-3 p-3 rounded-lg bg-[var(--color-bg-tertiary)] cursor-pointer hover:bg-[var(--color-bg-tertiary)]/80 transition-colors"
                    onClick={() => navigate(`/vehicles/${vehicle.id}`)}
                  >
                    {/* Vehicle photo or icon */}
                    <div className="w-12 h-12 rounded-lg bg-[var(--color-bg-primary)] flex items-center justify-center overflow-hidden flex-shrink-0">
                      {vehicle.photo ? (
                        <img 
                          src={vehicle.photo} 
                          alt={vehicle.name} 
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <span className="text-[var(--color-text-muted)]">{SettingsIcons.car}</span>
                      )}
                    </div>
                    
                    {/* Vehicle info */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{vehicle.name}</p>
                      <p className="text-2xs text-[var(--color-text-muted)]">
                        {vehicle.make} {vehicle.model} {vehicle.year ? `(${vehicle.year})` : ''}
                      </p>
                      {vehicle.archived_at && (
                        <p className="text-2xs text-[var(--color-text-muted)]">
                          {t('archive.archivedOn') || 'Archived'}: {formatDate(vehicle.archived_at)}
                        </p>
                      )}
                    </div>
                    
                    {/* Actions */}
                    <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => handleRestoreVehicle(vehicle.id)}
                        className="p-2 rounded-lg bg-green-500/10 text-green-500 hover:bg-green-500/20 transition-colors"
                        title={t('archive.restore') || 'Restore'}
                      >
                        {SettingsIcons.restore}
                      </button>
                      <button
                        onClick={() => handleDeleteArchivedVehicle(vehicle.id)}
                        className="p-2 rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors"
                        title={t('common.delete') || 'Delete'}
                      >
                        {SettingsIcons.trash}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Storage Stats - Admin Only */}
      {isAdmin && (
        <div className="card mb-4">
          <button
            onClick={() => setShowStorageSection(!showStorageSection)}
            className="w-full flex items-center justify-between"
          >
            <div className="flex items-center gap-3">
              <span className="text-blue-500">
                {SettingsIcons.archive}
              </span>
              <div className="text-left">
                <h3 className="text-sm font-medium">{t('settings.storageStats') || 'Storage Statistics'}</h3>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {storageLoading ? (
                    t('common.loading') || 'Loading...'
                  ) : storageStats ? (
                    `${storageStats.total_count} ${t('settings.files') || 'files'} · ${storageStats.total_size_human}`
                  ) : (
                    t('settings.storageDesc') || 'View attachment storage usage'
                  )}
                </p>
              </div>
            </div>
            <span className="text-[var(--color-text-muted)]">
              {showStorageSection ? SettingsIcons.chevronUp : SettingsIcons.chevronDown}
            </span>
          </button>
          
          {showStorageSection && storageStats && (
            <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
              {/* Total Storage */}
              <div className="mb-4 p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[var(--color-text-secondary)]">{t('settings.totalStorage') || 'Total Storage Used'}</span>
                  <span className="text-lg font-semibold text-blue-600 dark:text-blue-400">{storageStats.total_size_human}</span>
                </div>
                <div className="text-2xs text-[var(--color-text-muted)] mt-1">
                  {storageStats.total_count} {t('settings.totalFiles') || 'total files'}
                </div>
              </div>
              
              {/* By Category */}
              <div className="mb-4">
                <p className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide mb-2">
                  {t('settings.byCategory') || 'By Category'}
                </p>
                <div className="space-y-2">
                  {Object.entries(storageStats.by_category || {}).map(([category, data]) => (
                    <div key={category} className="flex items-center justify-between p-2 rounded-lg bg-[var(--color-bg-tertiary)]">
                      <div className="flex items-center gap-2">
                        <span className="text-sm capitalize">{t(`attachmentCategories.${category}`) || category}</span>
                        <span className="text-2xs text-[var(--color-text-muted)]">({data.count})</span>
                      </div>
                      <span className="text-sm font-medium">{_humanSize(data.size)}</span>
                    </div>
                  ))}
                  {Object.keys(storageStats.by_category || {}).length === 0 && (
                    <p className="text-sm text-[var(--color-text-muted)] text-center py-2">
                      {t('settings.noAttachments') || 'No attachments yet'}
                    </p>
                  )}
                </div>
              </div>
              
              {/* By Type */}
              <div>
                <p className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide mb-2">
                  {t('settings.byType') || 'By File Type'}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex items-center justify-between p-2 rounded-lg bg-[var(--color-bg-tertiary)]">
                    <span className="text-sm">📷 {t('settings.images') || 'Images'}</span>
                    <span className="text-sm font-medium">{storageStats.by_type?.images || 0}</span>
                  </div>
                  <div className="flex items-center justify-between p-2 rounded-lg bg-[var(--color-bg-tertiary)]">
                    <span className="text-sm">📄 {t('settings.pdfs') || 'PDFs'}</span>
                    <span className="text-sm font-medium">{storageStats.by_type?.pdfs || 0}</span>
                  </div>
                  <div className="flex items-center justify-between p-2 rounded-lg bg-[var(--color-bg-tertiary)]">
                    <span className="text-sm">📝 {t('settings.documents') || 'Documents'}</span>
                    <span className="text-sm font-medium">{storageStats.by_type?.documents || 0}</span>
                  </div>
                  <div className="flex items-center justify-between p-2 rounded-lg bg-[var(--color-bg-tertiary)]">
                    <span className="text-sm">📎 {t('settings.otherFiles') || 'Other'}</span>
                    <span className="text-sm font-medium">{storageStats.by_type?.other || 0}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      
      {/* Admin Section - Only visible to admins */}
      {isAdmin && (
        <div className="card mb-4">
          <button
            onClick={() => setShowAdminSection(!showAdminSection)}
            className="w-full flex items-center justify-between"
          >
            <div className="flex items-center gap-3">
              <span className="text-amber-500">
                {SettingsIcons.users}
              </span>
              <div className="text-left">
                <h3 className="text-sm font-medium">{t('admin.title') || 'Admin Panel'}</h3>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {t('admin.description') || 'Manage users and system settings'}
                </p>
              </div>
            </div>
            <span className="text-[var(--color-text-muted)]">
              {showAdminSection ? SettingsIcons.chevronUp : SettingsIcons.chevronDown}
            </span>
          </button>
          
          {showAdminSection && (
            <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
              {/* Admin Tabs */}
              <div className="flex bg-[var(--color-bg-tertiary)] rounded-lg p-1 mb-4">
                <button
                  onClick={() => setAdminTab('users')}
                  className={`flex-1 py-2 rounded-md text-xs font-medium transition-colors ${
                    adminTab === 'users'
                      ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm'
                      : 'text-[var(--color-text-secondary)]'
                  }`}
                >
                  {t('admin.users') || 'Users'}
                </button>
                <button
                  onClick={() => setAdminTab('security')}
                  className={`flex-1 py-2 rounded-md text-xs font-medium transition-colors ${
                    adminTab === 'security'
                      ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm'
                      : 'text-[var(--color-text-secondary)]'
                  }`}
                >
                  {t('admin.security.title') || 'Security'}
                </button>
                <button
                  onClick={() => setAdminTab('logs')}
                  className={`flex-1 py-2 rounded-md text-xs font-medium transition-colors ${
                    adminTab === 'logs'
                      ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm'
                      : 'text-[var(--color-text-secondary)]'
                  }`}
                >
                  {t('admin.systemLogs') || 'Logs'}
                </button>
                <button
                  onClick={() => setAdminTab('maintenance')}
                  className={`flex-1 py-2 rounded-md text-xs font-medium transition-colors ${
                    adminTab === 'maintenance'
                      ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm'
                      : 'text-[var(--color-text-secondary)]'
                  }`}
                >
                  {t('admin.maintenance') || 'Cleanup'}
                </button>
                <button
                  onClick={() => setAdminTab('ai')}
                  className={`flex-1 py-2 rounded-md text-xs font-medium transition-colors ${
                    adminTab === 'ai'
                      ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm'
                      : 'text-[var(--color-text-secondary)]'
                  }`}
                >
                  {t('admin.ai') || 'AI'}
                </button>
              </div>
              
              {/* Tab Content */}
              {adminTab === 'users' && <UserManagement />}
              {adminTab === 'security' && <SecurityBlocking />}
              {adminTab === 'logs' && <SystemLogs />}
              {adminTab === 'maintenance' && <MaintenanceCleanup />}
              {adminTab === 'ai' && <AiStatusPanel />}
            </div>
          )}
        </div>
      )}
      
      {/* About */}
      <div className="card mb-4">
        <h3 className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide mb-3">
          {t('settings.about')}
        </h3>
        
        <div className="space-y-1">
          <div className="flex items-center gap-3 py-2">
            <span className="text-[var(--color-text-muted)]">
              {SettingsIcons.info}
            </span>
            <div className="flex-1">
              <span className="text-sm">{t('settings.version')}</span>
            </div>
            <span className="text-sm text-[var(--color-text-muted)] tabular-nums">{BUILD.version}</span>
          </div>
          
          <button 
            onClick={() => setShowPrivacyPolicy(true)}
            className="flex items-center gap-3 w-full py-2 text-left"
          >
            <span className="text-[var(--color-text-muted)]">
              {SettingsIcons.document}
            </span>
            <span className="text-sm flex-1">{t('settings.privacyPolicy')}</span>
            <span className="text-[var(--color-text-muted)]">
              {SettingsIcons.externalLink}
            </span>
          </button>
          
          <button 
            onClick={() => setShowTermsOfService(true)}
            className="flex items-center gap-3 w-full py-2 text-left"
          >
            <span className="text-[var(--color-text-muted)]">
              {SettingsIcons.gavel}
            </span>
            <span className="text-sm flex-1">{t('settings.termsOfService')}</span>
            <span className="text-[var(--color-text-muted)]">
              {SettingsIcons.externalLink}
            </span>
          </button>
        </div>
      </div>
      
      {/* Logout */}
      <button
        onClick={handleLogout}
        className="w-full flex items-center justify-center gap-2 py-3 text-red-500 font-medium"
      >
        {SettingsIcons.logout}
        {t('settings.logout')}
      </button>
      
      {/* 2FA Setup Modal */}
      <TwoFactorSetup
        isOpen={show2FASetup}
        onClose={() => setShow2FASetup(false)}
        onSuccess={() => refreshUser()}
        isEnabled={user?.two_factor_enabled}
      />
      
      {/* Security Questions Setup Modal */}
      <SecurityQuestionsSetup
        isOpen={showSecurityQuestionsSetup}
        onClose={() => setShowSecurityQuestionsSetup(false)}
        onSuccess={() => refreshUser()}
      />
      
      {/* Privacy Policy Modal */}
      <PrivacyPolicy
        isOpen={showPrivacyPolicy}
        onClose={() => setShowPrivacyPolicy(false)}
      />
      
      {/* Terms of Service Modal */}
      <TermsOfService
        isOpen={showTermsOfService}
        onClose={() => setShowTermsOfService(false)}
      />

      {/* Push permission priming — shown before the browser prompt */}
      <PushPrimingModal
        isOpen={showPushPriming}
        onConfirm={handlePushPrimingConfirm}
        onClose={() => setShowPushPriming(false)}
      />
    </div>
  )
}
