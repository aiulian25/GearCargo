import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { authApi } from '../../services/api'
import toast from 'react-hot-toast'

// Inline SVG Icons
const ShieldCheckIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
  </svg>
)

const EyeIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
  </svg>
)

const EyeSlashIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
  </svg>
)

const KeyIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
  </svg>
)

export default function ForcePasswordChange() {
  const { t } = useTranslation()
  const { user, refreshUser, logout } = useAuth()
  const navigate = useNavigate()
  
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showCurrentPassword, setShowCurrentPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [passwordStrength, setPasswordStrength] = useState(null)
  
  const validatePassword = async (password) => {
    if (password.length < 8) {
      setPasswordStrength(null)
      return
    }
    try {
      const response = await authApi.validatePassword(password)
      setPasswordStrength(response.data)
    } catch (err) {
      setPasswordStrength(null)
    }
  }
  
  const handleNewPasswordChange = (e) => {
    const value = e.target.value
    setNewPassword(value)
    if (value.length >= 8) {
      validatePassword(value)
    } else {
      setPasswordStrength(null)
    }
  }
  
  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    
    if (newPassword !== confirmPassword) {
      setError(t('profile.passwordsDoNotMatch') || 'Passwords do not match')
      return
    }
    
    if (newPassword.length < 8) {
      setError(t('profile.passwordMinLength') || 'Password must be at least 8 characters')
      return
    }
    
    setIsSubmitting(true)
    
    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword
      })
      
      toast.success(t('profile.passwordChanged') || 'Password changed successfully')
      
      // Refresh user to clear must_change_password flag
      await refreshUser()
      
      // Redirect to security questions setup (user can skip if they want)
      navigate('/setup-security-questions')
    } catch (err) {
      const errorData = err.response?.data
      setError(errorData?.error || t('profile.failedToChangePassword') || 'Failed to change password')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }
  
  const getStrengthColor = (strength) => {
    switch (strength) {
      case 'weak': return 'text-red-500 bg-red-500'
      case 'fair': return 'text-orange-500 bg-orange-500'
      case 'good': return 'text-yellow-500 bg-yellow-500'
      case 'strong': return 'text-green-500 bg-green-500'
      case 'very_strong': return 'text-emerald-500 bg-emerald-500'
      default: return 'text-gray-500 bg-gray-500'
    }
  }
  
  const getStrengthLabel = (strength) => {
    switch (strength) {
      case 'weak': return t('profile.passwordWeak') || 'Weak'
      case 'fair': return t('profile.passwordFair') || 'Fair'
      case 'good': return t('profile.passwordGood') || 'Good'
      case 'strong': return t('profile.passwordStrong') || 'Strong'
      case 'very_strong': return t('profile.passwordVeryStrong') || 'Very Strong'
      default: return ''
    }
  }
  
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-primary)] px-4">
      <div className="max-w-md w-full space-y-8">
        {/* Header */}
        <div className="text-center">
          <div className="mx-auto h-16 w-16 bg-amber-500/10 rounded-full flex items-center justify-center">
            <ShieldCheckIcon className="h-8 w-8 text-amber-500" />
          </div>
          <h2 className="mt-6 text-3xl font-extrabold text-[var(--color-text-primary)]">
            {t('auth.passwordChangeRequired') || 'Password Change Required'}
          </h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            {t('auth.passwordChangeDescription') || 'For security reasons, you must change your password before continuing.'}
          </p>
        </div>
        
        {/* Form */}
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}
          
          <div className="space-y-4">
            {/* Current Password */}
            <div>
              <label htmlFor="current-password" className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                {t('profile.currentPassword') || 'Current Password'}
              </label>
              <div className="relative">
                <input
                  id="current-password"
                  type={showCurrentPassword ? 'text' : 'password'}
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                  className="w-full px-3 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] pr-10"
                  placeholder={t('profile.enterCurrentPassword') || 'Enter current password'}
                />
                <button
                  type="button"
                  onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
                >
                  {showCurrentPassword ? <EyeSlashIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
                </button>
              </div>
            </div>
            
            {/* New Password */}
            <div>
              <label htmlFor="new-password" className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                {t('profile.newPassword') || 'New Password'}
              </label>
              <div className="relative">
                <input
                  id="new-password"
                  type={showNewPassword ? 'text' : 'password'}
                  value={newPassword}
                  onChange={handleNewPasswordChange}
                  required
                  className="w-full px-3 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] pr-10"
                  placeholder={t('profile.enterNewPassword') || 'Enter new password'}
                />
                <button
                  type="button"
                  onClick={() => setShowNewPassword(!showNewPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
                >
                  {showNewPassword ? <EyeSlashIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
                </button>
              </div>
              
              {/* Password Strength Indicator */}
              {passwordStrength && (
                <div className="mt-2">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-[var(--color-bg-tertiary)] rounded-full overflow-hidden">
                      <div 
                        className={`h-full transition-all ${getStrengthColor(passwordStrength.strength)}`}
                        style={{ width: `${(passwordStrength.score / 5) * 100}%` }}
                      />
                    </div>
                    <span className={`text-xs font-medium ${getStrengthColor(passwordStrength.strength).split(' ')[0]}`}>
                      {getStrengthLabel(passwordStrength.strength)}
                    </span>
                  </div>
                </div>
              )}
            </div>
            
            {/* Confirm Password */}
            <div>
              <label htmlFor="confirm-password" className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                {t('profile.confirmPassword') || 'Confirm Password'}
              </label>
              <div className="relative">
                <input
                  id="confirm-password"
                  type={showConfirmPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  className="w-full px-3 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] pr-10"
                  placeholder={t('profile.confirmNewPassword') || 'Confirm new password'}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
                >
                  {showConfirmPassword ? <EyeSlashIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
                </button>
              </div>
              
              {/* Password Match Indicator */}
              {confirmPassword && (
                <p className={`mt-1 text-xs ${newPassword === confirmPassword ? 'text-green-500' : 'text-red-500'}`}>
                  {newPassword === confirmPassword 
                    ? (t('profile.passwordsMatch') || 'Passwords match')
                    : (t('profile.passwordsDoNotMatch') || 'Passwords do not match')
                  }
                </p>
              )}
            </div>
          </div>
          
          {/* Submit Button */}
          <div className="space-y-3">
            <button
              type="submit"
              disabled={isSubmitting || !currentPassword || !newPassword || !confirmPassword || newPassword !== confirmPassword}
              className="w-full flex justify-center items-center gap-2 py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--color-accent)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? (
                <>
                  <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                  {t('common.saving') || 'Saving...'}
                </>
              ) : (
                <>
                  <KeyIcon className="h-5 w-5" />
                  {t('profile.changePassword') || 'Change Password'}
                </>
              )}
            </button>
            
            <button
              type="button"
              onClick={handleLogout}
              className="w-full py-2.5 px-4 border border-[var(--color-border)] rounded-lg text-sm font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] transition-colors"
            >
              {t('common.logout') || 'Logout'}
            </button>
          </div>
        </form>
        
        {/* User Info */}
        {user && (
          <div className="text-center text-sm text-[var(--color-text-tertiary)]">
            {t('auth.loggedInAs') || 'Logged in as'}: <span className="text-[var(--color-text-secondary)]">{user.email}</span>
          </div>
        )}
      </div>
    </div>
  )
}
