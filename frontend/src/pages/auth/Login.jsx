import { useState, useRef, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useAuth } from '../../contexts/AuthContext'
import { useLanguage } from '../../contexts/LanguageContext'
import toast from 'react-hot-toast'

export default function Login() {
  const { login } = useAuth()
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [isLoading, setIsLoading] = useState(false)
  const [requires2FA, setRequires2FA] = useState(false)
  const [credentials, setCredentials] = useState(null)
  const [showPassword, setShowPassword] = useState(false)
  const [rememberPassword, setRememberPassword] = useState(false)
  const [useBackupCode, setUseBackupCode] = useState(false)
  const [codeValue, setCodeValue] = useState('')
  const usernameRef = useRef(null)
  const passwordRef = useRef(null)
  const codeInputRef = useRef(null)
  
  const { register, handleSubmit, formState: { errors } } = useForm()
  const { register: register2FA, handleSubmit: handleSubmit2FA, setValue: setValue2FA } = useForm()
  
  // Auto-focus username field on mount
  useEffect(() => {
    if (usernameRef.current) {
      usernameRef.current.focus()
    }
  }, [])
  
  // Auto-focus code input when 2FA is required
  useEffect(() => {
    if (requires2FA && codeInputRef.current) {
      codeInputRef.current.focus()
    }
  }, [requires2FA, useBackupCode])
  
  // Auto-submit when code is complete
  useEffect(() => {
    const requiredLength = useBackupCode ? 8 : 6
    if (codeValue.length === requiredLength && !isLoading) {
      // Submit automatically
      handleSubmit2FA(onSubmit2FA)()
    }
  }, [codeValue])
  
  const handleCodeChange = (e) => {
    let value = e.target.value
    // For authenticator code, only allow numbers
    if (!useBackupCode) {
      value = value.replace(/\D/g, '')
    }
    // For backup code, allow alphanumeric and uppercase
    if (useBackupCode) {
      value = value.toUpperCase().replace(/[^A-Z0-9]/g, '')
    }
    const maxLength = useBackupCode ? 8 : 6
    value = value.slice(0, maxLength)
    setCodeValue(value)
    setValue2FA('code', value)
  }
  
  const onSubmit = async (data) => {
    setIsLoading(true)
    try {
      const result = await login(data.email, data.password, null, rememberPassword)
      
      if (result.requires2FA) {
        setCredentials(data)
        setRequires2FA(true)
        setIsLoading(false)
        return
      }
      
      toast.success(t('auth.welcomeBack'))
      navigate('/')
    } catch (error) {
      toast.error(error.response?.data?.error || t('auth.loginFailed'))
    } finally {
      setIsLoading(false)
    }
  }
  
  const onSubmit2FA = async (data) => {
    setIsLoading(true)
    try {
      // If using backup code, pass it differently
      if (useBackupCode) {
        await login(credentials.email, credentials.password, null, rememberPassword, data.code)
      } else {
        await login(credentials.email, credentials.password, data.code, rememberPassword)
      }
      toast.success(t('auth.welcomeBack'))
      navigate('/')
    } catch (error) {
      toast.error(error.response?.data?.error || t('auth.invalidCode'))
    } finally {
      setIsLoading(false)
    }
  }
  
  if (requires2FA) {
    return (
      <div className="slide-up-enter">
        <h1 className="text-2xl font-bold text-gray-800 mb-2">
          {t('auth.twoFactorAuth')}
        </h1>
        <p className="text-sm text-gray-500 mb-8">
          {useBackupCode 
            ? (t('auth.enterBackupCode') || 'Enter one of your backup codes')
            : (t('auth.enterCodeFromApp') || 'Enter the code from your authenticator app')}
        </p>
        
        <form onSubmit={handleSubmit2FA(onSubmit2FA)} className="space-y-6">
          <div>
            <input
              ref={codeInputRef}
              type="text"
              inputMode={useBackupCode ? "text" : "numeric"}
              autoComplete="one-time-code"
              className="w-full px-4 py-3 text-center text-xl tracking-widest border border-gray-200 rounded-full focus:outline-none focus:border-teal-500 transition-colors font-mono text-gray-800 bg-white"
              placeholder={useBackupCode ? "XXXXXXXX" : "000000"}
              maxLength={useBackupCode ? 8 : 6}
              value={codeValue}
              onChange={handleCodeChange}
            />
          </div>
          
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
                {t('auth.verify')}
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </>
            )}
          </button>
          
          <div className="flex flex-col gap-2">
            <button 
              type="button"
              className="w-full text-teal-600 hover:text-teal-700 font-medium py-2 transition-colors text-sm"
              onClick={() => {
                setUseBackupCode(!useBackupCode)
                setCodeValue('')
                setValue2FA('code', '')
              }}
            >
              {useBackupCode 
                ? (t('auth.useAuthenticatorApp') || 'Use authenticator app instead')
                : (t('auth.useBackupCodeInstead') || 'Use backup code instead')}
            </button>
            
            <button 
              type="button"
              className="w-full text-gray-500 hover:text-gray-700 font-medium py-2 transition-colors"
              onClick={() => {
                setRequires2FA(false)
                setCredentials(null)
                setCodeValue('')
                setUseBackupCode(false)
              }}
            >
              {t('auth.backToLogin')}
            </button>
          </div>
        </form>
      </div>
    )
  }
  
  return (
    <div className="slide-up-enter">
      <h1 className="text-2xl font-bold text-gray-800 mb-8">
        {t('auth.loginHere')}
      </h1>
      
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* Username/Email Field */}
        <div className="flex items-center gap-3">
          <div className="text-gray-400 flex-shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </div>
          <div className="flex-1">
            <input
              type="text"
              className="w-full px-4 py-3 border border-gray-200 rounded-full focus:outline-none focus:border-teal-500 transition-colors text-gray-700 placeholder-gray-400"
              placeholder={t('auth.username')}
              autoComplete="username"
              {...register('email', { 
                required: t('auth.usernameRequired')
              })}
              ref={(e) => {
                register('email').ref(e)
                usernameRef.current = e
              }}
            />
            {errors.email && (
              <p className="text-xs text-red-500 mt-2 ml-4">{errors.email.message}</p>
            )}
          </div>
        </div>
        
        {/* Password Field */}
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
              placeholder={t('auth.password')}
              autoComplete="current-password"
              {...register('password', { required: t('auth.passwordRequired') })}
              ref={(e) => {
                register('password').ref(e)
                passwordRef.current = e
              }}
            />
            <button
              type="button"
              className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
              onClick={() => {
                setShowPassword(!showPassword)
                // Keep focus on password field after toggling
                setTimeout(() => {
                  if (passwordRef.current) {
                    passwordRef.current.focus()
                  }
                }, 0)
              }}
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
          </div>
        </div>
        
        {/* Remember Password & Login Button Row */}
        <div className="flex items-center justify-between pt-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={rememberPassword}
              onChange={(e) => setRememberPassword(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
            />
            <span className="text-sm text-gray-500">{t('auth.rememberPassword')}</span>
          </label>
          
          <button 
            type="submit" 
            className="text-white font-medium py-2.5 px-6 rounded-full transition-colors flex items-center gap-2 text-sm tracking-wider"
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
                {t('auth.login').toUpperCase()}
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </>
            )}
          </button>
        </div>
        
        {/* Forgot Password Link */}
        <div className="text-center pt-2">
          <Link to="/forgot-password" className="text-sm text-teal-600 hover:text-teal-700 transition-colors">
            {t('auth.forgotPassword')}
          </Link>
        </div>
      </form>
      
      <p className="text-sm mt-12 text-gray-500">
        {t('auth.noAccount')} {t('auth.createAccountHere')}{' '}
        <Link to="/register" className="text-teal-600 hover:text-teal-700 underline font-medium">
          {t('auth.here')}
        </Link>
      </p>
    </div>
  )
}
