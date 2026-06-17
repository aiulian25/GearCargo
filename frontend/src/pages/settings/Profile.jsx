import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useAuth } from '../../contexts/AuthContext'
import { useTranslation } from '../../contexts/LanguageContext'
import api, { authApi } from '../../services/api'
import TwoFactorSetup from '../../components/settings/TwoFactorSetup'

// Password strength indicator component with optional server-side validation
function PasswordStrength({ password, useServerValidation = false }) {
  const { t } = useTranslation()
  const [strength, setStrength] = useState({ score: 0, level: 'weak', errors: [] })
  const [isValidating, setIsValidating] = useState(false)
  const debounceTimerRef = useRef(null)
  
  // Client-side validation (instant feedback)
  const validateClientSide = useCallback((pwd) => {
    if (!pwd) {
      return { score: 0, level: 'weak', errors: [] }
    }
    
    let score = 0
    const errors = []
    
    // Length checks (S03: minimum raised to 12)
    if (pwd.length >= 12) score += 20
    if (pwd.length >= 16) score += 10
    if (pwd.length < 12) errors.push(t('profile.passwordMinLength') || 'At least 12 characters')
    
    // Character type checks
    if (/[A-Z]/.test(pwd)) score += 15
    else errors.push(t('profile.passwordUppercase') || 'Add uppercase letter')
    
    if (/[a-z]/.test(pwd)) score += 15
    else errors.push(t('profile.passwordLowercase') || 'Add lowercase letter')
    
    if (/\d/.test(pwd)) score += 15
    else errors.push(t('profile.passwordNumber') || 'Add a number')
    
    if (/[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;'`~]/.test(pwd)) score += 15
    
    // Common password check (simplified client-side)
    const commonPasswords = ['password', 'password123', '123456', 'qwerty', 'letmein', 'admin', 'welcome']
    if (commonPasswords.includes(pwd.toLowerCase())) {
      errors.push(t('profile.passwordCommon') || 'Too common')
      score = Math.min(score, 20)
    }
    
    // Sequential check
    if (/123|234|345|456|567|678|789|abc|bcd|cde|qwe|wer|asd/.test(pwd.toLowerCase())) {
      score = Math.max(0, score - 10)
    }
    
    let level = 'weak'
    if (score >= 70) level = 'strong'
    else if (score >= 50) level = 'medium'
    
    return { score, level, errors }
  }, [t])
  
  // Server-side validation (debounced for more thorough checks)
  const validateServerSide = useCallback(async (pwd) => {
    if (!pwd || pwd.length < 4) return
    
    try {
      setIsValidating(true)
      const response = await authApi.validatePassword(pwd)
      const data = response.data
      
      // Map server response to our format
      let level = 'weak'
      if (data.strength === 'strong' || data.strength_score >= 70) level = 'strong'
      else if (data.strength === 'medium' || data.strength_score >= 50) level = 'medium'
      
      setStrength({
        score: data.strength_score || 0,
        level,
        errors: data.errors || [],
        isServerValidated: true
      })
    } catch (err) {
      // If server validation fails, keep client-side validation
      console.warn('Server password validation failed:', err)
    } finally {
      setIsValidating(false)
    }
  }, [])
  
  useEffect(() => {
    // Clear any pending debounce timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }
    
    // Immediate client-side validation
    const clientResult = validateClientSide(password)
    setStrength(clientResult)
    
    // Debounced server-side validation (if enabled and password is long enough)
    if (useServerValidation && password && password.length >= 4) {
      debounceTimerRef.current = setTimeout(() => {
        validateServerSide(password)
      }, 500) // 500ms debounce
    }
    
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
    }
  }, [password, useServerValidation, validateClientSide, validateServerSide])
  
  const getColor = () => {
    if (strength.level === 'strong') return 'bg-green-500'
    if (strength.level === 'medium') return 'bg-amber-500'
    return 'bg-red-500'
  }
  
  const getLabel = () => {
    if (strength.level === 'strong') return t('profile.passwordStrong') || 'Strong'
    if (strength.level === 'medium') return t('profile.passwordMedium') || 'Medium'
    return t('profile.passwordWeak') || 'Weak'
  }
  
  if (!password) return null
  
  return (
    <div className="mt-2">
      <div className="flex items-center gap-2 mb-1">
        <div className="flex-1 h-1 bg-[var(--color-bg-tertiary)] rounded-full overflow-hidden">
          <div 
            className={`h-full transition-all duration-300 ${getColor()}`}
            style={{ width: `${strength.score}%` }}
          />
        </div>
        <span className={`text-2xs font-medium flex items-center gap-1 ${
          strength.level === 'strong' ? 'text-green-500' :
          strength.level === 'medium' ? 'text-amber-500' : 'text-red-500'
        }`}>
          {isValidating && (
            <span className="w-2 h-2 border border-current border-t-transparent rounded-full animate-spin" />
          )}
          {getLabel()}
          {strength.isServerValidated && !isValidating && (
            <svg className="w-3 h-3 text-green-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
          )}
        </span>
      </div>
      {strength.errors.length > 0 && (
        <ul className="text-2xs text-[var(--color-text-muted)] space-y-0.5">
          {strength.errors.slice(0, 3).map((err, i) => (
            <li key={i} className="flex items-center gap-1">
              <span className="w-1 h-1 rounded-full bg-[var(--color-text-muted)]" />
              {err}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// Security verification modal component
function SecurityVerificationModal({ isOpen, onClose, onVerify, requires2FA, isVerifying }) {
  const { t } = useTranslation()
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [error, setError] = useState('')
  
  const handleSubmit = (e) => {
    e.preventDefault()
    setError('')
    
    if (!password) {
      setError(t('profile.passwordRequired') || 'Password is required')
      return
    }
    
    if (requires2FA && !totpCode) {
      setError(t('profile.totpRequired') || '2FA code is required')
      return
    }
    
    onVerify(password, totpCode)
  }
  
  // Reset state when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setPassword('')
      setTotpCode('')
      setError('')
    }
  }, [isOpen])
  
  if (!isOpen) return null
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="bg-[var(--color-bg-card)] rounded-2xl p-6 w-full max-w-sm border border-[var(--color-border)]">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-amber-500/20 flex items-center justify-center">
            <span className="material-icons-outlined text-amber-500">lock</span>
          </div>
          <div>
            <h3 className="text-base font-semibold">{t('profile.verifyIdentity') || 'Verify Your Identity'}</h3>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {t('profile.verifyIdentityDesc') || 'Enter your password to confirm changes'}
            </p>
          </div>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-500 px-3 py-2 rounded-lg text-sm">
              {error}
            </div>
          )}
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('profile.currentPassword') || 'Current Password'}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
              placeholder="••••••••"
              autoFocus
            />
          </div>
          
          {requires2FA && (
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('profile.twoFactorCode') || '2FA Code'}
              </label>
              <input
                type="text"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="input text-center tracking-widest"
                placeholder="000000"
                maxLength={6}
              />
            </div>
          )}
          
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-3 rounded-xl bg-[var(--color-bg-tertiary)] font-medium text-sm"
            >
              {t('common.cancel') || 'Cancel'}
            </button>
            <button
              type="submit"
              disabled={isVerifying}
              className="flex-1 py-3 rounded-xl bg-[var(--color-accent)] text-white font-medium text-sm disabled:opacity-50"
            >
              {isVerifying ? (t('common.verifying') || 'Verifying...') : (t('common.confirm') || 'Confirm')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Profile() {
  const navigate = useNavigate()
  const { user, updateUser, refreshUser } = useAuth()
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState('profile')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [show2FASetup, setShow2FASetup] = useState(false)
  
  // Password visibility state
  const [showCurrentPassword, setShowCurrentPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  
  // Security verification state
  const [showVerification, setShowVerification] = useState(false)
  const [pendingProfileData, setPendingProfileData] = useState(null)
  const [requires2FA, setRequires2FA] = useState(false)
  
  // 2FA status state
  const [twoFAStatus, setTwoFAStatus] = useState(null)
  
  // Email verification state
  const [isResendingVerification, setIsResendingVerification] = useState(false)
  
  // Avatar state
  const [showAvatarModal, setShowAvatarModal] = useState(false)
  const [avatarHistory, setAvatarHistory] = useState([])
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false)
  const avatarInputRef = useRef(null)
  
  // Track original values to detect changes
  const [originalValues, setOriginalValues] = useState({})
  
  useEffect(() => {
    if (user) {
      setOriginalValues({
        name: user.name || '',
        username: user.username || '',
        email: user.email || '',
      })
    }
  }, [user])
  
  // Fetch avatar history
  useEffect(() => {
    const fetchAvatars = async () => {
      try {
        const response = await authApi.getAvatars()
        setAvatarHistory(response.data.avatar_history || [])
      } catch (err) {
        console.error('Failed to fetch avatars:', err)
      }
    }
    fetchAvatars()
  }, [user?.avatar])
  
  // Fetch 2FA status when user has 2FA enabled
  useEffect(() => {
    const fetch2FAStatus = async () => {
      if (user?.two_factor_enabled) {
        try {
          const response = await api.get('/auth/2fa/status')
          setTwoFAStatus(response.data)
        } catch (err) {
          console.error('Failed to fetch 2FA status:', err)
        }
      } else {
        setTwoFAStatus(null)
      }
    }
    fetch2FAStatus()
  }, [user?.two_factor_enabled])
  
  const profileForm = useForm({
    defaultValues: {
      name: user?.name || '',
      username: user?.username || '',
      email: user?.email || '',
      language: user?.language || 'en',
      currency: user?.currency || 'EUR',
      distance_unit: user?.distance_unit || 'km',
      volume_unit: user?.volume_unit || 'liters',
      // Location settings
      location_auto_detect: user?.location_auto_detect !== false,
      location_lat: user?.location_lat || '',
      location_lon: user?.location_lon || '',
      location_name: user?.location_name || '',
    }
  })
  
  const passwordForm = useForm({
    defaultValues: {
      current_password: '',
      new_password: '',
      confirm_password: '',
      totp_code: '',
    }
  })
  
  const watchNewPassword = passwordForm.watch('new_password')
  
  // Check if sensitive fields have changed
  const hasSensitiveChanges = useCallback((data) => {
    return (
      (data.name && data.name !== originalValues.name) ||
      (data.username && data.username !== originalValues.username) ||
      (data.email && data.email !== originalValues.email)
    )
  }, [originalValues])
  
  const handleProfileUpdate = async (data) => {
    setError('')
    setSuccess('')
    
    // Check if sensitive changes require verification
    if (hasSensitiveChanges(data)) {
      setPendingProfileData(data)
      setRequires2FA(user?.two_factor_enabled || false)
      setShowVerification(true)
      return
    }
    
    // No sensitive changes, proceed directly
    await submitProfileUpdate(data)
  }
  
  const submitProfileUpdate = async (data, password = null, totpCode = null) => {
    setIsSubmitting(true)
    setError('')
    
    try {
      const payload = { ...data }
      if (password) {
        payload.current_password = password
      }
      if (totpCode) {
        payload.totp_code = totpCode
      }
      
      const response = await authApi.updateProfile(payload)
      updateUser(response.data.user)
      setSuccess(t('profile.profileUpdated') || 'Profile updated successfully')
      setShowVerification(false)
      setPendingProfileData(null)
      
      // Update original values
      setOriginalValues({
        name: response.data.user.name || response.data.user.display_name || '',
        username: response.data.user.username || '',
        email: response.data.user.email || '',
      })
    } catch (err) {
      const errorData = err.response?.data
      
      if (errorData?.requires_verification) {
        setPendingProfileData(data)
        setRequires2FA(user?.two_factor_enabled || false)
        setShowVerification(true)
      } else if (errorData?.requires_2fa) {
        setRequires2FA(true)
        setError(t('profile.totpRequired') || '2FA code is required')
      } else {
        setError(errorData?.error || t('profile.failedToUpdate') || 'Failed to update profile')
      }
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const handleVerification = async (password, totpCode) => {
    if (pendingProfileData) {
      await submitProfileUpdate(pendingProfileData, password, totpCode)
    }
  }
  
  const handlePasswordChange = async (data) => {
    if (data.new_password !== data.confirm_password) {
      setError(t('auth.passwordsNoMatch') || 'Passwords do not match')
      return
    }
    
    setIsSubmitting(true)
    setError('')
    setSuccess('')
    
    try {
      const payload = {
        current_password: data.current_password,
        new_password: data.new_password,
        confirm_password: data.confirm_password,
      }
      
      // Add 2FA code if enabled
      if (user?.two_factor_enabled && data.totp_code) {
        payload.totp_code = data.totp_code
      }
      
      await authApi.changePassword(payload)
      setSuccess(t('profile.passwordChanged') || 'Password changed successfully')
      passwordForm.reset()
    } catch (err) {
      const errorData = err.response?.data
      
      if (errorData?.requires_2fa) {
        setError(t('profile.totpRequired') || '2FA code is required')
      } else if (errorData?.password_errors) {
        setError(errorData.password_errors.join('. '))
      } else {
        setError(errorData?.error || t('profile.failedToChangePassword') || 'Failed to change password')
      }
    } finally {
      setIsSubmitting(false)
    }
  }
  
  // Handler for resending email verification
  const handleResendVerification = async () => {
    setIsResendingVerification(true)
    try {
      await authApi.sendVerificationEmail()
      setSuccess(t('auth.verificationEmailSent') || 'Verification email sent!')
    } catch (err) {
      setError(err.response?.data?.error || t('common.error') || 'Failed to send verification email')
    } finally {
      setIsResendingVerification(false)
    }
  }
  
  // Avatar handlers
  const handleAvatarUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    
    // Validate file size (2MB max)
    if (file.size > 2 * 1024 * 1024) {
      setError(t('profile.avatarTooLarge') || 'Avatar must be less than 2MB')
      return
    }
    
    // Validate file type
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if (!validTypes.includes(file.type)) {
      setError(t('profile.invalidAvatarType') || 'Invalid image type. Use JPG, PNG, GIF or WebP')
      return
    }
    
    setIsUploadingAvatar(true)
    setError('')
    
    try {
      const response = await authApi.uploadAvatar(file)
      setAvatarHistory(response.data.avatar_history || [])
      await refreshUser()
      setSuccess(t('profile.avatarUploaded') || 'Avatar uploaded successfully')
      setShowAvatarModal(false)
    } catch (err) {
      setError(err.response?.data?.error || t('profile.failedToUploadAvatar') || 'Failed to upload avatar')
    } finally {
      setIsUploadingAvatar(false)
      if (avatarInputRef.current) {
        avatarInputRef.current.value = ''
      }
    }
  }
  
  const handleSelectAvatar = async (avatarUrl) => {
    setIsUploadingAvatar(true)
    setError('')
    
    try {
      const response = await authApi.selectAvatar(avatarUrl)
      setAvatarHistory(response.data.avatar_history || [])
      await refreshUser()
      setSuccess(t('profile.avatarSelected') || 'Avatar selected')
      setShowAvatarModal(false)
    } catch (err) {
      setError(err.response?.data?.error || t('profile.failedToSelectAvatar') || 'Failed to select avatar')
    } finally {
      setIsUploadingAvatar(false)
    }
  }
  
  const handleDeleteAvatar = async (avatarUrl) => {
    const filename = avatarUrl.split('/').pop().split('?')[0]
    setError('')
    
    try {
      const response = await authApi.deleteAvatar(filename)
      setAvatarHistory(response.data.avatar_history || [])
      setSuccess(t('profile.avatarDeleted') || 'Avatar deleted')
    } catch (err) {
      setError(err.response?.data?.error || t('profile.failedToDeleteAvatar') || 'Failed to delete avatar')
    }
  }
  
  const handleRemoveCurrentAvatar = async () => {
    setIsUploadingAvatar(true)
    setError('')
    
    try {
      const response = await authApi.removeAvatar()
      setAvatarHistory(response.data.avatar_history || [])
      await refreshUser()
      setSuccess(t('profile.avatarRemoved') || 'Avatar removed')
      setShowAvatarModal(false)
    } catch (err) {
      setError(err.response?.data?.error || t('profile.failedToRemoveAvatar') || 'Failed to remove avatar')
    } finally {
      setIsUploadingAvatar(false)
    }
  }
  
  const tabLabels = {
    profile: t('profile.title') || 'Profile',
    password: t('common.password') || 'Password',
    security: t('profile.security') || 'Security'
  }
  
  return (
    <div className="pb-4">
      {/* Header */}
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          <span className="material-icons-outlined icon-md">arrow_back</span>
        </button>
        <h1 className="text-base font-semibold flex-1">{t('profile.updateProfile') || 'Update Profile'}</h1>
      </div>
      
      {/* Avatar - Clickable to change */}
      <div className="flex flex-col items-center py-6">
        <button 
          onClick={() => setShowAvatarModal(true)}
          className="relative group"
        >
          <div className="w-20 h-20 rounded-full bg-[var(--color-accent)] flex items-center justify-center overflow-hidden">
            {user?.avatar ? (
              <img 
                src={user.avatar} 
                alt={user?.name || 'Avatar'} 
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-3xl font-bold text-white">
                {user?.name?.charAt(0).toUpperCase() || 'U'}
              </span>
            )}
          </div>
          {/* Edit overlay */}
          <div className="absolute inset-0 rounded-full bg-black/50 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
            <span className="material-icons-outlined text-white text-xl">photo_camera</span>
          </div>
          {/* Edit badge */}
          <div className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-[var(--color-accent)] flex items-center justify-center border-2 border-[var(--color-bg)]">
            <span className="material-icons-outlined text-white text-sm">edit</span>
          </div>
        </button>
        <h2 className="text-base font-semibold mt-3">{user?.name}</h2>
        <p className="text-xs text-[var(--color-text-secondary)]">{user?.email}</p>
      </div>
      
      {/* Tabs */}
      <div className="px-4 mb-4">
        <div className="flex bg-[var(--color-bg-tertiary)] rounded-lg p-1">
          {['profile', 'password', 'security'].map(tab => (
            <button
              key={tab}
              onClick={() => { setActiveTab(tab); setError(''); setSuccess(''); }}
              className={`flex-1 py-2 rounded-md text-xs font-medium transition-colors ${
                activeTab === tab 
                  ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm' 
                  : 'text-[var(--color-text-secondary)]'
              }`}
            >
              {tabLabels[tab]}
            </button>
          ))}
        </div>
      </div>
      
      <div className="px-4">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-500 px-4 py-3 rounded-xl text-sm mb-4">
            {error}
          </div>
        )}
        
        {success && (
          <div className="bg-green-500/10 border border-green-500/20 text-green-500 px-4 py-3 rounded-xl text-sm mb-4">
            {success}
          </div>
        )}
        
        {/* Profile Tab */}
        {activeTab === 'profile' && (
          <form onSubmit={profileForm.handleSubmit(handleProfileUpdate)} className="space-y-4">
            <div className="card space-y-4">
              <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
                {t('profile.accountInfo') || 'Account Information'}
              </h3>
              
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('profile.displayName') || 'Display Name'}
                </label>
                <input
                  type="text"
                  {...profileForm.register('name', { required: true })}
                  className="input"
                  placeholder={t('profile.displayNamePlaceholder') || 'Your full name'}
                />
              </div>
              
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('common.username') || 'Username'}
                </label>
                <input
                  type="text"
                  {...profileForm.register('username')}
                  className="input"
                  placeholder={t('profile.usernamePlaceholder') || 'Choose a username'}
                />
              </div>
              
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('common.email') || 'Email'}
                </label>
                <input
                  type="email"
                  {...profileForm.register('email', { required: true })}
                  className="input"
                  placeholder="email@example.com"
                />
                <p className="text-2xs text-[var(--color-text-muted)] mt-1">
                  {t('profile.emailChangeNote') || 'Used for login and notifications'}
                </p>
                
                {/* Email Verification Status */}
                {user?.email_verified ? (
                  <div className="flex items-center gap-2 mt-2 text-green-500">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="text-xs">{t('profile.emailVerified') || 'Email verified'}</span>
                  </div>
                ) : (
                  <div className="mt-2 p-2 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                    <div className="flex items-center gap-2 text-amber-500">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <span className="text-xs">{t('auth.emailNotVerified') || 'Email not verified'}</span>
                    </div>
                    <button
                      type="button"
                      onClick={handleResendVerification}
                      disabled={isResendingVerification}
                      className="mt-2 text-xs text-[var(--color-accent)] hover:underline disabled:opacity-50"
                    >
                      {isResendingVerification 
                        ? (t('common.sending') || 'Sending...') 
                        : (t('auth.resendVerification') || 'Resend Verification Email')}
                    </button>
                  </div>
                )}
              </div>
              
              {/* Security notice for sensitive changes */}
              <div className="flex items-start gap-2 p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                <span className="material-icons-outlined text-amber-500 text-base">info</span>
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  {t('profile.sensitiveChangeNote') || 'Changing your name, username, or email will require password verification'}
                </p>
              </div>
            </div>
            
            <div className="card space-y-4">
              <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
                {t('profile.preferences') || 'Preferences'}
              </h3>
              
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                    {t('profile.language') || 'Language'}
                  </label>
                  <select {...profileForm.register('language')} className="input">
                    <option value="en">English</option>
                    <option value="de">Deutsch</option>
                    <option value="fr">Français</option>
                    <option value="es">Español</option>
                    <option value="ro">Română</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                    {t('profile.currency') || 'Currency'}
                  </label>
                  <select {...profileForm.register('currency')} className="input">
                    <option value="EUR">EUR (€)</option>
                    <option value="USD">USD ($)</option>
                    <option value="GBP">GBP (£)</option>
                    <option value="RON">RON (lei)</option>
                  </select>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                    {t('profile.distance') || 'Distance'}
                  </label>
                  <select {...profileForm.register('distance_unit')} className="input">
                    <option value="km">{t('profile.kilometers') || 'Kilometers'}</option>
                    <option value="mi">{t('common.miles') || 'Miles'}</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                    {t('profile.volume') || 'Volume'}
                  </label>
                  <select {...profileForm.register('volume_unit')} className="input">
                    <option value="liters">{t('common.liters') || 'Liters'}</option>
                    <option value="gallons">{t('common.gallons') || 'Gallons'}</option>
                  </select>
                </div>
              </div>
            </div>
            
            {/* Location Settings */}
            <div className="card space-y-4">
              <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
                {t('profile.locationSettings') || 'Location Settings'}
              </h3>
              
              <p className="text-xs text-[var(--color-text-muted)]">
                {t('profile.locationDescription') || 'Set your location for accurate weather and fuel prices on the dashboard.'}
              </p>
              
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-sm font-medium text-[var(--color-text-primary)]">
                    {t('profile.autoDetectLocation') || 'Auto-detect Location'}
                  </label>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {t('profile.autoDetectDescription') || 'Use your device GPS for precise location'}
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input 
                    type="checkbox" 
                    {...profileForm.register('location_auto_detect')}
                    className="sr-only peer" 
                  />
                  <div className="w-11 h-6 bg-[var(--color-bg-tertiary)] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--color-accent)]"></div>
                </label>
              </div>
              
              {!profileForm.watch('location_auto_detect') && (
                <div className="space-y-3 pt-2 border-t border-[var(--color-border)]">
                  <div>
                    <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                      {t('profile.locationName') || 'Location Name'}
                    </label>
                    <input
                      type="text"
                      {...profileForm.register('location_name')}
                      className="input"
                      placeholder={t('profile.locationPlaceholder') || 'e.g., Brighton, United Kingdom'}
                    />
                  </div>
                  
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                        {t('profile.latitude') || 'Latitude'}
                      </label>
                      <input
                        type="number"
                        step="any"
                        {...profileForm.register('location_lat', { valueAsNumber: true })}
                        className="input"
                        placeholder="51.5074"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                        {t('profile.longitude') || 'Longitude'}
                      </label>
                      <input
                        type="number"
                        step="any"
                        {...profileForm.register('location_lon', { valueAsNumber: true })}
                        className="input"
                        placeholder="-0.1278"
                      />
                    </div>
                  </div>
                  
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {t('profile.locationTip') || 'Tip: You can find coordinates by right-clicking on Google Maps.'}
                  </p>
                </div>
              )}
            </div>
            
            <button
              type="submit"
              disabled={isSubmitting}
              className="btn btn-primary w-full"
            >
              {isSubmitting ? (t('common.saving') || 'Saving...') : (t('profile.saveChanges') || 'Save Changes')}
            </button>
          </form>
        )}
        
        {/* Password Tab */}
        {activeTab === 'password' && (
          <form onSubmit={passwordForm.handleSubmit(handlePasswordChange)} className="space-y-4">
            <div className="card space-y-4">
              <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
                {t('profile.changePassword') || 'Change Password'}
              </h3>
              
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('profile.currentPassword') || 'Current Password'}
                </label>
                <div className="relative">
                  <input
                    type={showCurrentPassword ? 'text' : 'password'}
                    {...passwordForm.register('current_password', { required: true })}
                    className="input pr-10"
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
                  >
                    <span className="material-icons-outlined text-lg">
                      {showCurrentPassword ? 'visibility_off' : 'visibility'}
                    </span>
                  </button>
                </div>
              </div>
              
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('profile.newPassword') || 'New Password'}
                </label>
                <div className="relative">
                  <input
                    type={showNewPassword ? 'text' : 'password'}
                    {...passwordForm.register('new_password', { 
                      required: true,
                      minLength: { value: 12, message: t('profile.minEightChars') || 'Min 12 characters' }
                    })}
                    className="input pr-10"
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
                  >
                    <span className="material-icons-outlined text-lg">
                      {showNewPassword ? 'visibility_off' : 'visibility'}
                    </span>
                  </button>
                </div>
                <PasswordStrength password={watchNewPassword} useServerValidation />
              </div>
              
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('profile.confirmNewPassword') || 'Confirm New Password'}
                </label>
                <div className="relative">
                  <input
                    type={showConfirmPassword ? 'text' : 'password'}
                    {...passwordForm.register('confirm_password', { required: true })}
                    className="input pr-10"
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
                  >
                    <span className="material-icons-outlined text-lg">
                      {showConfirmPassword ? 'visibility_off' : 'visibility'}
                    </span>
                  </button>
                </div>
              </div>
              
              {user?.two_factor_enabled && (
                <div>
                  <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                    {t('profile.twoFactorCode') || '2FA Code'}
                  </label>
                  <input
                    type="text"
                    {...passwordForm.register('totp_code')}
                    className="input text-center tracking-widest"
                    placeholder="000000"
                    maxLength={6}
                  />
                  <p className="text-2xs text-[var(--color-text-muted)] mt-1">
                    {t('profile.enterAuthCode') || 'Enter code from your authenticator app'}
                  </p>
                </div>
              )}
            </div>
            
            {/* Password requirements */}
            <div className="card">
              <h4 className="text-xs font-medium text-[var(--color-text-secondary)] mb-2">
                {t('profile.passwordRequirements') || 'Password Requirements'}
              </h4>
              <ul className="text-2xs text-[var(--color-text-muted)] space-y-1">
                <li className="flex items-center gap-2">
                  <span className="material-icons-outlined text-xs">check_circle</span>
                  {t('profile.reqMinLength') || 'At least 12 characters'}
                </li>
                <li className="flex items-center gap-2">
                  <span className="material-icons-outlined text-xs">check_circle</span>
                  {t('profile.reqMixCase') || 'Mix of uppercase and lowercase'}
                </li>
                <li className="flex items-center gap-2">
                  <span className="material-icons-outlined text-xs">check_circle</span>
                  {t('profile.reqNumber') || 'At least one number'}
                </li>
                <li className="flex items-center gap-2">
                  <span className="material-icons-outlined text-xs">info</span>
                  {t('profile.reqSpecial') || 'Special characters recommended'}
                </li>
              </ul>
            </div>
            
            <button
              type="submit"
              disabled={isSubmitting}
              className="btn btn-primary w-full"
            >
              {isSubmitting ? (t('profile.changingPassword') || 'Changing...') : (t('profile.changePassword') || 'Change Password')}
            </button>
          </form>
        )}
        
        {/* Security Tab */}
        {activeTab === 'security' && (
          <div className="space-y-4">
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-medium">{t('auth.twoFactorAuth') || 'Two-Factor Authentication'}</h3>
                  <p className="text-2xs text-[var(--color-text-muted)]">
                    {t('profile.addExtraSecurity') || 'Add an extra layer of security'}
                  </p>
                </div>
                <span className={`badge ${user?.two_factor_enabled ? 'badge-success' : 'badge-warning'}`}>
                  {user?.two_factor_enabled ? (t('common.enabled') || 'Enabled') : (t('common.disabled') || 'Disabled')}
                </span>
              </div>
              
              {/* Show backup codes remaining when 2FA is enabled */}
              {user?.two_factor_enabled && twoFAStatus && (
                <div className={`mb-4 p-3 rounded-lg ${twoFAStatus.backup_codes_count <= 2 ? 'bg-amber-500/10 border border-amber-500/30' : 'bg-[var(--color-bg-tertiary)]'}`}>
                  <div className="flex items-center gap-2">
                    <span className={`material-icons-outlined icon-sm ${twoFAStatus.backup_codes_count <= 2 ? 'text-amber-500' : 'text-[var(--color-text-muted)]'}`}>
                      vpn_key
                    </span>
                    <span className={`text-xs ${twoFAStatus.backup_codes_count <= 2 ? 'text-amber-500 font-medium' : 'text-[var(--color-text-muted)]'}`}>
                      {twoFAStatus.backup_codes_count} {t('profile.backupCodesRemaining') || 'backup codes remaining'}
                    </span>
                  </div>
                  {twoFAStatus.backup_codes_count <= 2 && (
                    <p className="text-2xs text-amber-500/80 mt-1 ml-6">
                      {t('profile.considerRegenerating') || 'Consider regenerating your backup codes'}
                    </p>
                  )}
                </div>
              )}
              
              <button 
                onClick={() => setShow2FASetup(true)}
                className="btn btn-secondary w-full text-sm"
              >
                {user?.two_factor_enabled ? (t('profile.manage2FA') || 'Manage 2FA') : (t('profile.enable2FA') || 'Enable 2FA')}
              </button>
            </div>
            
            <div className="card">
              <h3 className="text-sm font-medium mb-3">{t('profile.activeSessions') || 'Active Sessions'}</h3>
              
              <div className="space-y-3">
                <div className="flex items-center gap-3 p-2 bg-[var(--color-bg-tertiary)] rounded-lg">
                  <span className="material-icons-outlined icon-sm text-green-500">
                    smartphone
                  </span>
                  <div className="flex-1">
                    <p className="text-xs font-medium">{t('profile.currentDevice') || 'Current Device'}</p>
                    <p className="text-2xs text-[var(--color-text-muted)]">
                      {t('common.active') || 'Active now'}
                    </p>
                  </div>
                </div>
              </div>
              
              <button className="btn btn-ghost w-full mt-4 text-red-500 text-sm">
                {t('profile.logoutAllDevices') || 'Logout All Devices'}
              </button>
            </div>
            
            <div className="card">
              <h3 className="text-sm font-medium text-red-500 mb-3">{t('profile.dangerZone') || 'Danger Zone'}</h3>
              
              <button className="btn w-full border-red-500 text-red-500 hover:bg-red-500/10 text-sm">
                {t('profile.deleteAccount') || 'Delete Account'}
              </button>
              <p className="text-2xs text-[var(--color-text-muted)] mt-2 text-center">
                {t('profile.cannotBeUndone') || 'This action cannot be undone'}
              </p>
            </div>
          </div>
        )}
      </div>
      
      {/* Security Verification Modal */}
      <SecurityVerificationModal
        isOpen={showVerification}
        onClose={() => { setShowVerification(false); setPendingProfileData(null); }}
        onVerify={handleVerification}
        requires2FA={requires2FA}
        isVerifying={isSubmitting}
      />
      
      {/* 2FA Setup Modal */}
      <TwoFactorSetup
        isOpen={show2FASetup}
        onClose={() => {
          setShow2FASetup(false)
          // Refresh 2FA status in case codes were regenerated
          if (user?.two_factor_enabled) {
            api.get('/auth/2fa/status').then(res => setTwoFAStatus(res.data)).catch(() => {})
          }
        }}
        onSuccess={() => refreshUser()}
        isEnabled={user?.two_factor_enabled}
      />
      
      {/* Avatar Modal */}
      {showAvatarModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-[var(--color-bg-card)] rounded-2xl w-full max-w-sm max-h-[80vh] overflow-hidden flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
              <h3 className="text-base font-semibold">{t('profile.changeAvatar') || 'Change Avatar'}</h3>
              <button 
                onClick={() => setShowAvatarModal(false)}
                className="btn-icon"
                disabled={isUploadingAvatar}
              >
                <span className="material-icons-outlined">close</span>
              </button>
            </div>
            
            {/* Modal Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {/* Current Avatar */}
              <div className="flex flex-col items-center mb-6">
                <div className="w-24 h-24 rounded-full bg-[var(--color-accent)] flex items-center justify-center overflow-hidden mb-3">
                  {user?.avatar ? (
                    <img 
                      src={user.avatar} 
                      alt={user?.name || 'Avatar'} 
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <span className="text-4xl font-bold text-white">
                      {user?.name?.charAt(0).toUpperCase() || 'U'}
                    </span>
                  )}
                </div>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('profile.currentAvatar') || 'Current Avatar'}
                </p>
              </div>
              
              {/* Upload New Button */}
              <input
                ref={avatarInputRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp"
                onChange={handleAvatarUpload}
                className="hidden"
                id="avatar-upload"
              />
              <label
                htmlFor="avatar-upload"
                className={`btn btn-primary w-full mb-4 cursor-pointer flex items-center justify-center gap-2 ${isUploadingAvatar ? 'opacity-50 pointer-events-none' : ''}`}
              >
                <span className="material-icons-outlined text-lg">cloud_upload</span>
                {isUploadingAvatar ? (t('common.uploading') || 'Uploading...') : (t('profile.uploadNewAvatar') || 'Upload New Avatar')}
              </label>
              
              {/* Remove Current Avatar */}
              {user?.avatar && (
                <button
                  onClick={handleRemoveCurrentAvatar}
                  disabled={isUploadingAvatar}
                  className="btn btn-ghost w-full mb-4 text-red-500 flex items-center justify-center gap-2"
                >
                  <span className="material-icons-outlined text-lg">delete</span>
                  {t('profile.removeAvatar') || 'Remove Current Avatar'}
                </button>
              )}
              
              {/* Previous Avatars */}
              {avatarHistory.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-[var(--color-text-muted)] mb-3">
                    {t('profile.previousAvatars') || 'Previous Avatars'}
                  </h4>
                  <div className="grid grid-cols-4 gap-3">
                    {avatarHistory.map((avatarUrl, index) => (
                      <div key={index} className="relative group">
                        <button
                          onClick={() => handleSelectAvatar(avatarUrl)}
                          disabled={isUploadingAvatar}
                          className="w-full aspect-square rounded-lg overflow-hidden border-2 border-transparent hover:border-[var(--color-accent)] transition-colors"
                        >
                          <img 
                            src={avatarUrl} 
                            alt={`Previous avatar ${index + 1}`}
                            className="w-full h-full object-cover"
                          />
                        </button>
                        {/* Delete button */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleDeleteAvatar(avatarUrl)
                          }}
                          className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <span className="material-icons-outlined text-white text-xs">close</span>
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Help text */}
              <p className="text-2xs text-[var(--color-text-muted)] mt-4 text-center">
                {t('profile.avatarHint') || 'JPG, PNG, GIF or WebP. Max 2MB.'}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
