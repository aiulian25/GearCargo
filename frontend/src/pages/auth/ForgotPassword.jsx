import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useLanguage } from '../../contexts/LanguageContext'
import { authApi } from '../../services/api'
import toast from 'react-hot-toast'

export default function ForgotPassword() {
  const { t } = useLanguage()
  const [isLoading, setIsLoading] = useState(false)
  const [emailSent, setEmailSent] = useState(false)
  const [sentEmail, setSentEmail] = useState('')
  
  const { register, handleSubmit, formState: { errors } } = useForm()
  
  const onSubmit = async (data) => {
    setIsLoading(true)
    try {
      await authApi.requestPasswordReset(data.email)
      setSentEmail(data.email)
      setEmailSent(true)
      toast.success(t('auth.resetEmailSent') || 'Reset email sent!')
    } catch (error) {
      // Always show success to prevent email enumeration
      setSentEmail(data.email)
      setEmailSent(true)
    } finally {
      setIsLoading(false)
    }
  }
  
  if (emailSent) {
    return (
      <div className="slide-up-enter">
        <div className="text-center">
          {/* Success Icon */}
          <div className="mx-auto w-16 h-16 bg-teal-100 rounded-full flex items-center justify-center mb-6">
            <svg className="w-8 h-8 text-teal-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          
          <h1 className="text-2xl font-bold text-gray-800 mb-4">
            {t('auth.checkEmail') || 'Check Your Email'}
          </h1>
          
          <p className="text-gray-500 mb-2">
            {t('auth.resetEmailSentTo') || 'If an account exists for'}
          </p>
          <p className="text-teal-600 font-medium mb-4">{sentEmail}</p>
          <p className="text-gray-500 mb-8">
            {t('auth.resetEmailInstructions') || "you'll receive a password reset link shortly."}
          </p>
          
          <div className="space-y-4">
            <button
              onClick={() => setEmailSent(false)}
              className="w-full text-teal-600 hover:text-teal-700 font-medium py-2 transition-colors"
            >
              {t('auth.tryDifferentEmail') || 'Try a different email'}
            </button>
            
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
  
  return (
    <div className="slide-up-enter">
      <h1 className="text-2xl font-bold text-gray-800 mb-2">
        {t('auth.forgotPassword') || 'Forgot Password?'}
      </h1>
      <p className="text-sm text-gray-500 mb-8">
        {t('auth.forgotPasswordDesc') || "Enter your email and we'll send you a reset link."}
      </p>
      
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* Email Field */}
        <div className="flex items-center gap-3">
          <div className="text-gray-400 flex-shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <div className="flex-1">
            <input
              type="email"
              className="w-full px-4 py-3 border border-gray-200 rounded-full focus:outline-none focus:border-teal-500 transition-colors text-gray-700 placeholder-gray-400"
              placeholder={t('auth.emailAddress') || 'Email address'}
              autoComplete="email"
              autoFocus
              {...register('email', { 
                required: t('auth.emailRequired') || 'Email is required',
                pattern: {
                  value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
                  message: t('auth.invalidEmail') || 'Invalid email address'
                }
              })}
            />
            {errors.email && (
              <p className="text-xs text-red-500 mt-2 ml-4">{errors.email.message}</p>
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
              {t('auth.sendResetLink') || 'Send Reset Link'}
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </>
          )}
        </button>
      </form>
      
      <p className="text-sm mt-12 text-gray-500">
        {t('auth.rememberedPassword') || 'Remembered your password?'}{' '}
        <Link to="/login" className="text-teal-600 hover:text-teal-700 underline font-medium">
          {t('auth.backToLogin') || 'Back to Login'}
        </Link>
      </p>
    </div>
  )
}
