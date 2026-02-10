import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useAuth } from '../../contexts/AuthContext'
import { useTranslation } from '../../contexts/LanguageContext'
import toast from 'react-hot-toast'

// Password strength indicator component (client-side only for registration)
function PasswordStrength({ password }) {
  const { t } = useTranslation()
  const [strength, setStrength] = useState({ score: 0, level: 'weak', errors: [] })
  
  useEffect(() => {
    if (!password) {
      setStrength({ score: 0, level: 'weak', errors: [] })
      return
    }
    
    let score = 0
    const errors = []
    
    // Length checks
    if (password.length >= 8) score += 20
    if (password.length >= 12) score += 10
    if (password.length >= 16) score += 10
    else if (password.length < 8) errors.push(t('profile.passwordMinLength') || 'At least 8 characters')
    
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
    
    // Sequential check
    if (/123|234|345|456|567|678|789|abc|bcd|cde|qwe|wer|asd/.test(password.toLowerCase())) {
      score = Math.max(0, score - 10)
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
        <div className="flex-1 h-1 bg-[var(--color-bg-tertiary)] rounded-full overflow-hidden">
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
        <ul className="text-xs text-[var(--color-text-muted)] space-y-0.5">
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

export default function Register() {
  const { register: registerUser } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [isLoading, setIsLoading] = useState(false)
  
  const { register, handleSubmit, watch, formState: { errors } } = useForm()
  const password = watch('password')
  
  const onSubmit = async (data) => {
    setIsLoading(true)
    try {
      await registerUser({
        name: data.name,
        email: data.email,
        password: data.password,
      })
      
      toast.success(t('auth.accountCreated') || 'Account created successfully!')
      navigate('/')
    } catch (error) {
      toast.error(error.response?.data?.error || t('auth.registrationFailed') || 'Registration failed')
    } finally {
      setIsLoading(false)
    }
  }
  
  return (
    <div className="slide-up-enter">
      <h1 className="text-xl font-bold text-center mb-2">
        {t('auth.createAccount') || 'Create Account'}
      </h1>
      <p className="text-sm text-[var(--color-text-secondary)] text-center mb-6">
        {t('auth.startTracking') || 'Start managing your vehicles today'}
      </p>
      
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <label className="label">{t('common.name') || 'Name'}</label>
          <input
            type="text"
            className="input"
            placeholder={t('auth.enterYourName') || 'Your name'}
            autoComplete="name"
            {...register('name', { 
              required: t('auth.nameRequired') || 'Name is required',
              minLength: { value: 2, message: t('auth.nameMinLength') || 'Name must be at least 2 characters' }
            })}
          />
          {errors.name && (
            <p className="text-xs text-red-500 mt-1">{errors.name.message}</p>
          )}
        </div>
        
        <div>
          <label className="label">{t('common.email') || 'Email'}</label>
          <input
            type="email"
            className="input"
            placeholder={t('auth.enterYourEmail') || 'your@email.com'}
            autoComplete="email"
            {...register('email', { 
              required: t('auth.emailRequired') || 'Email is required',
              pattern: {
                value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
                message: t('auth.invalidEmail') || 'Invalid email address'
              }
            })}
          />
          {errors.email && (
            <p className="text-xs text-red-500 mt-1">{errors.email.message}</p>
          )}
        </div>
        
        <div>
          <label className="label">{t('common.password') || 'Password'}</label>
          <input
            type="password"
            className="input"
            placeholder="••••••••"
            autoComplete="new-password"
            {...register('password', { 
              required: t('auth.passwordRequired') || 'Password is required',
              minLength: { value: 8, message: t('auth.passwordMinLength') || 'Password must be at least 8 characters' }
            })}
          />
          {errors.password && (
            <p className="text-xs text-red-500 mt-1">{errors.password.message}</p>
          )}
          <PasswordStrength password={password} />
        </div>
        
        <div>
          <label className="label">{t('auth.confirmPassword') || 'Confirm Password'}</label>
          <input
            type="password"
            className="input"
            placeholder="••••••••"
            autoComplete="new-password"
            {...register('confirmPassword', { 
              required: t('validation.required') || 'Please confirm your password',
              validate: value => value === password || t('auth.passwordsNoMatch') || 'Passwords do not match'
            })}
          />
          {errors.confirmPassword && (
            <p className="text-xs text-red-500 mt-1">{errors.confirmPassword.message}</p>
          )}
        </div>
        
        <button 
          type="submit" 
          className="btn btn-primary w-full"
          disabled={isLoading}
        >
          {isLoading ? (
            <span className="animate-spin material-icons-outlined icon-sm">refresh</span>
          ) : (t('auth.createAccount') || 'Create Account')}
        </button>
      </form>
      
      <p className="text-sm text-center mt-6 text-[var(--color-text-secondary)]">
        {t('auth.hasAccount') || 'Already have an account?'}{' '}
        <Link to="/login" className="text-[var(--color-accent)] font-medium">
          {t('auth.login') || 'Sign In'}
        </Link>
      </p>
    </div>
  )
}
