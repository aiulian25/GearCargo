import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useLanguage } from '../../contexts/LanguageContext'
import { authApi } from '../../services/api'
import toast from 'react-hot-toast'

// Password strength indicator component
function PasswordStrength({ password }) {
  const { t } = useLanguage()
  const [strength, setStrength] = useState({ score: 0, level: 'weak', errors: [] })
  
  useEffect(() => {
    if (!password) {
      setStrength({ score: 0, level: 'weak', errors: [] })
      return
    }
    
    let score = 0
    const errors = []
    
    // Length checks (S03: minimum raised to 12)
    if (password.length >= 12) score += 20
    if (password.length >= 16) score += 10
    if (password.length < 12) errors.push(t('profile.passwordMinLength') || 'At least 12 characters')
    
    // Character type checks
    if (/[A-Z]/.test(password)) score += 15
    else errors.push(t('profile.passwordUppercase') || 'Add uppercase letter')
    
    if (/[a-z]/.test(password)) score += 15
    else errors.push(t('profile.passwordLowercase') || 'Add lowercase letter')
    
    if (/\d/.test(password)) score += 15
    else errors.push(t('profile.passwordNumber') || 'Add a number')
    
    if (/[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;'`~]/.test(password)) score += 15
    
    // Common password check
    const commonPasswords = ['password', 'password123', '123456', 'qwerty', 'letmein', 'admin', 'welcome']
    if (commonPasswords.includes(password.toLowerCase())) {
      errors.push(t('profile.passwordCommon') || 'Too common')
      score = Math.min(score, 20)
    }
    
    let level = 'weak'
    if (score >= 70) level = 'strong'
    else if (score >= 50) level = 'medium'
    
    setStrength({ score, level, errors })
  }, [password, t])
  
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
        <div className="flex-1 h-1 bg-gray-200 rounded-full overflow-hidden">
          <div 
            className={`h-full transition-all duration-300 ${getColor()}`}
            style={{ width: `${strength.score}%` }}
          />
        </div>
        <span className={`text-xs font-medium ${
          strength.level === 'strong' ? 'text-green-500' :
          strength.level === 'medium' ? 'text-amber-500' : 'text-red-500'
        }`}>
          {getLabel()}
        </span>
      </div>
      {strength.errors.length > 0 && (
        <ul className="text-xs text-gray-500 space-y-0.5">
          {strength.errors.map((error, i) => (
            <li key={i} className="flex items-center gap-1">
              <span className="w-1 h-1 rounded-full bg-gray-400" />
              {error}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function ResetPassword() {
  const { t } = useLanguage()
  const [searchParams] = useSearchParams()
  const [isLoading, setIsLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [isInvalidToken, setIsInvalidToken] = useState(false)
  
  const token = searchParams.get('token')
  
  const { register, handleSubmit, watch, formState: { errors } } = useForm()
  const watchPassword = watch('password')
  
  useEffect(() => {
    if (!token) {
      setIsInvalidToken(true)
    }
  }, [token])
  
  const onSubmit = async (data) => {
    if (data.password !== data.confirmPassword) {
      toast.error(t('auth.passwordsNoMatch') || 'Passwords do not match')
      return
    }
    
    setIsLoading(true)
    try {
      await authApi.verifyPasswordReset(token, data.password)
      setIsSuccess(true)
      toast.success(t('auth.passwordResetSuccess') || 'Password reset successfully!')
    } catch (error) {
      const errorMsg = error.response?.data?.error
      if (errorMsg?.includes('expired') || errorMsg?.includes('invalid')) {
        setIsInvalidToken(true)
      } else {
        toast.error(errorMsg || t('auth.passwordResetFailed') || 'Failed to reset password')
      }
    } finally {
      setIsLoading(false)
    }
  }
  
  // Invalid/expired token state
  if (isInvalidToken) {
    return (
      <div className="slide-up-enter">
        <div className="text-center">
          {/* Error Icon */}
          <div className="mx-auto w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-6">
            <svg className="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          
          <h1 className="text-2xl font-bold text-gray-800 mb-4">
            {t('auth.invalidResetLink') || 'Invalid Reset Link'}
          </h1>
          
          <p className="text-gray-500 mb-8">
            {t('auth.resetLinkExpired') || 'This password reset link is invalid or has expired. Please request a new one.'}
          </p>
          
          <div className="space-y-4">
            <Link
              to="/forgot-password"
              className="block w-full text-white font-medium py-3 px-6 rounded-full transition-colors text-center"
              style={{ backgroundColor: '#1a3a3a' }}
            >
              {t('auth.requestNewLink') || 'Request New Link'}
            </Link>
            
            <Link
              to="/login"
              className="block w-full text-gray-500 hover:text-gray-700 font-medium py-2 transition-colors"
            >
              {t('auth.backToLogin') || 'Back to Login'}
            </Link>
          </div>
        </div>
      </div>
    )
  }
  
  // Success state
  if (isSuccess) {
    return (
      <div className="slide-up-enter">
        <div className="text-center">
          {/* Success Icon */}
          <div className="mx-auto w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-6">
            <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          
          <h1 className="text-2xl font-bold text-gray-800 mb-4">
            {t('auth.passwordReset') || 'Password Reset!'}
          </h1>
          
          <p className="text-gray-500 mb-8">
            {t('auth.passwordResetSuccessDesc') || 'Your password has been successfully reset. You can now login with your new password.'}
          </p>
          
          <Link
            to="/login"
            className="block w-full text-white font-medium py-3 px-6 rounded-full transition-colors text-center"
            style={{ backgroundColor: '#1a3a3a' }}
          >
            {t('auth.continueToLogin') || 'Continue to Login'}
          </Link>
        </div>
      </div>
    )
  }
  
  return (
    <div className="slide-up-enter">
      <h1 className="text-2xl font-bold text-gray-800 mb-2">
        {t('auth.resetPassword') || 'Reset Password'}
      </h1>
      <p className="text-sm text-gray-500 mb-8">
        {t('auth.resetPasswordDesc') || 'Enter your new password below.'}
      </p>
      
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* New Password Field */}
        <div className="flex items-center gap-3">
          <div className="text-gray-400 flex-shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <div className="flex-1 relative">
            <input
              type={showPassword ? 'text' : 'password'}
              className="w-full px-4 py-3 pr-12 border border-gray-200 rounded-full focus:outline-none focus:border-teal-500 transition-colors text-gray-700 placeholder-gray-400"
              placeholder={t('auth.newPassword') || 'New password'}
              autoComplete="new-password"
              autoFocus
              {...register('password', { 
                required: t('auth.passwordRequired') || 'Password is required',
                minLength: {
                  value: 12,
                  message: t('auth.passwordMinLength') || 'Password must be at least 12 characters'
                }
              })}
            />
            <button
              type="button"
              className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
            {errors.password && (
              <p className="text-xs text-red-500 mt-2 ml-4">{errors.password.message}</p>
            )}
            <PasswordStrength password={watchPassword} />
          </div>
        </div>
        
        {/* Confirm Password Field */}
        <div className="flex items-center gap-3">
          <div className="text-gray-400 flex-shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <div className="flex-1 relative">
            <input
              type={showConfirmPassword ? 'text' : 'password'}
              className="w-full px-4 py-3 pr-12 border border-gray-200 rounded-full focus:outline-none focus:border-teal-500 transition-colors text-gray-700 placeholder-gray-400"
              placeholder={t('auth.confirmPassword') || 'Confirm password'}
              autoComplete="new-password"
              {...register('confirmPassword', { 
                required: t('auth.confirmPasswordRequired') || 'Please confirm your password',
                validate: value => value === watchPassword || (t('auth.passwordsNoMatch') || 'Passwords do not match')
              })}
            />
            <button
              type="button"
              className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
            >
              {showConfirmPassword ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
            {errors.confirmPassword && (
              <p className="text-xs text-red-500 mt-2 ml-4">{errors.confirmPassword.message}</p>
            )}
          </div>
        </div>
        
        {/* Submit Button */}
        <button 
          type="submit" 
          className="w-full text-white font-medium py-3 px-6 rounded-full transition-colors flex items-center justify-center gap-2"
          style={{ backgroundColor: '#1a3a3a' }}
          disabled={isLoading}
          onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#152e2e'}
          onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#1a3a3a'}
        >
          {isLoading ? (
            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          ) : (
            <>
              {t('auth.resetPassword') || 'Reset Password'}
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </>
          )}
        </button>
      </form>
      
      <p className="text-sm mt-12 text-gray-500 text-center">
        <Link to="/login" className="text-teal-600 hover:text-teal-700 underline font-medium">
          {t('auth.backToLogin') || 'Back to Login'}
        </Link>
      </p>
    </div>
  )
}
