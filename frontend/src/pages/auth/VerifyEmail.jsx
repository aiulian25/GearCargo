import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useLanguage } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { authApi } from '../../services/api'

export default function VerifyEmail() {
  const { t } = useLanguage()
  const { refreshUser } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  
  const [status, setStatus] = useState('verifying') // verifying, success, error, expired
  const [error, setError] = useState('')
  
  useEffect(() => {
    const token = searchParams.get('token')
    
    if (!token) {
      setStatus('error')
      setError(t('auth.noVerificationToken') || 'No verification token provided')
      return
    }
    
    verifyToken(token)
  }, [searchParams])
  
  const verifyToken = async (token) => {
    try {
      await authApi.verifyEmail(token)
      setStatus('success')
      
      // Refresh user data to update email_verified status
      await refreshUser()
      
      // Redirect to dashboard after 3 seconds
      setTimeout(() => {
        navigate('/')
      }, 3000)
    } catch (err) {
      const errorData = err.response?.data
      if (errorData?.error?.includes('expired')) {
        setStatus('expired')
        setError(t('auth.verificationLinkExpired') || 'This verification link has expired')
      } else {
        setStatus('error')
        setError(errorData?.error || t('auth.verificationFailed') || 'Email verification failed')
      }
    }
  }
  
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 px-4">
      <div className="max-w-md w-full">
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <div className="w-20 h-20 bg-white/10 rounded-2xl flex items-center justify-center backdrop-blur-sm">
            <svg className="w-12 h-12 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
            </svg>
          </div>
        </div>
        
        {/* Card */}
        <div className="bg-white/95 backdrop-blur-sm rounded-3xl shadow-2xl p-8 text-center">
          {/* Verifying */}
          {status === 'verifying' && (
            <>
              <div className="mx-auto w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-6">
                <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                {t('auth.verifyingEmail') || 'Verifying Email'}
              </h2>
              <p className="text-gray-600">
                {t('auth.pleaseWait') || 'Please wait while we verify your email address...'}
              </p>
            </>
          )}
          
          {/* Success */}
          {status === 'success' && (
            <>
              <div className="mx-auto w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-6">
                <svg className="w-10 h-10 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                {t('auth.emailVerified') || 'Email Verified!'}
              </h2>
              <p className="text-gray-600 mb-6">
                {t('auth.emailVerifiedDesc') || 'Your email has been successfully verified. You can now use all features of GearCargo.'}
              </p>
              <Link 
                to="/"
                className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-full font-medium hover:from-blue-700 hover:to-blue-800 transition-all"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                </svg>
                {t('auth.goToDashboard') || 'Go to Dashboard'}
              </Link>
              <p className="text-sm text-gray-500 mt-4">
                {t('auth.redirectingIn') || 'Redirecting in 3 seconds...'}
              </p>
            </>
          )}
          
          {/* Expired */}
          {status === 'expired' && (
            <>
              <div className="mx-auto w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mb-6">
                <svg className="w-10 h-10 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                {t('auth.linkExpired') || 'Link Expired'}
              </h2>
              <p className="text-gray-600 mb-6">
                {error}
              </p>
              <p className="text-gray-600 mb-6">
                {t('auth.requestNewVerification') || 'Please request a new verification email from your profile settings.'}
              </p>
              <Link 
                to="/login"
                className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-full font-medium hover:from-blue-700 hover:to-blue-800 transition-all"
              >
                {t('auth.backToLogin') || 'Back to Login'}
              </Link>
            </>
          )}
          
          {/* Error */}
          {status === 'error' && (
            <>
              <div className="mx-auto w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-6">
                <svg className="w-10 h-10 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                {t('auth.verificationFailed') || 'Verification Failed'}
              </h2>
              <p className="text-gray-600 mb-6">
                {error}
              </p>
              <Link 
                to="/login"
                className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-full font-medium hover:from-blue-700 hover:to-blue-800 transition-all"
              >
                {t('auth.backToLogin') || 'Back to Login'}
              </Link>
            </>
          )}
        </div>
        
        {/* Footer */}
        <p className="text-center mt-6 text-white/60 text-sm">
          © {new Date().getFullYear()} GearCargo
        </p>
      </div>
    </div>
  )
}
