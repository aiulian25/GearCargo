/**
 * GearCargo - Security Questions Setup Component
 * Allows users to set up security questions for account recovery
 */

import { useState, useEffect } from 'react'
import { authApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import toast from 'react-hot-toast'

// Icons
const Icons = {
  close: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  shield: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  check: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  questionMark: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  lock: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  ),
  plus: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  ),
  trash: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </svg>
  ),
}

export default function SecurityQuestionsSetup({ isOpen, onClose, onSuccess, isConfigured = false }) {
  const { t } = useTranslation()
  const { user, refreshUser } = useAuth()
  
  const [step, setStep] = useState(1) // 1: intro, 2: select questions, 3: verify password, 4: complete
  const [availableQuestions, setAvailableQuestions] = useState([])
  const [selectedQuestions, setSelectedQuestions] = useState([
    { question: '', answer: '' },
    { question: '', answer: '' },
  ])
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [requires2FA, setRequires2FA] = useState(false)
  
  // Mapping from English question text to translation key
  const questionKeyMap = {
    "What was the name of your first pet?": 'pet',
    "What is your mother's maiden name?": 'mother',
    "What was the name of your first school?": 'school',
    "In what city were you born?": 'city',
    "What is the name of your favorite childhood friend?": 'friend',
    "What was your childhood nickname?": 'nickname',
    "What is your oldest sibling's middle name?": 'sibling',
    "What is the name of the first street you lived on?": 'street',
    "What was the make of your first car?": 'car',
    "What was your dream job as a child?": 'dream',
    "What is your favorite movie?": 'movie',
    "What was the first concert you attended?": 'concert',
    "What is your favorite book?": 'book',
    "What is your favorite sports team?": 'sports',
    "What was the name of your first employer?": 'employer',
  }
  
  // Translate a question from English to current language
  const translateQuestion = (englishQuestion) => {
    const key = questionKeyMap[englishQuestion]
    if (key) {
      const translated = t(`securityQuestions.questions.${key}`)
      // If translation exists and is different from the key path, use it
      if (translated && !translated.includes('securityQuestions.questions.')) {
        return translated
      }
    }
    // Fallback to English if no translation found
    return englishQuestion
  }
  
  // Load available questions on mount
  useEffect(() => {
    if (isOpen) {
      loadAvailableQuestions()
      setRequires2FA(user?.two_factor_enabled || false)
      // Reset state when opening
      setStep(1)
      setSelectedQuestions([{ question: '', answer: '' }, { question: '', answer: '' }])
      setPassword('')
      setTotpCode('')
      setError('')
    }
  }, [isOpen, user])
  
  const loadAvailableQuestions = async () => {
    try {
      const response = await authApi.getAvailableSecurityQuestions()
      setAvailableQuestions(response.data.questions || [])
    } catch (err) {
      console.error('Failed to load security questions:', err)
      toast.error(t('securityQuestions.loadError') || 'Failed to load security questions')
    }
  }
  
  const handleAddQuestion = () => {
    if (selectedQuestions.length < 5) {
      setSelectedQuestions([...selectedQuestions, { question: '', answer: '' }])
    }
  }
  
  const handleRemoveQuestion = (index) => {
    if (selectedQuestions.length > 2) {
      setSelectedQuestions(selectedQuestions.filter((_, i) => i !== index))
    }
  }
  
  const handleQuestionChange = (index, field, value) => {
    const updated = [...selectedQuestions]
    updated[index][field] = value
    setSelectedQuestions(updated)
  }
  
  const isQuestionsValid = () => {
    return selectedQuestions.every(q => q.question && q.answer.trim().length >= 2) &&
           new Set(selectedQuestions.map(q => q.question)).size === selectedQuestions.length // No duplicate questions
  }
  
  const handleSubmit = async () => {
    setIsLoading(true)
    setError('')
    
    try {
      const payload = {
        password,
        questions: selectedQuestions,
      }
      
      if (requires2FA && totpCode) {
        payload.totp_code = totpCode
      }
      
      await authApi.setSecurityQuestions(payload)
      
      toast.success(t('securityQuestions.setupSuccess') || 'Security questions saved successfully!')
      
      // Refresh user data
      await refreshUser()
      
      setStep(4) // Show success
      
      if (onSuccess) {
        setTimeout(() => {
          onSuccess()
        }, 2000)
      }
    } catch (err) {
      const errorData = err.response?.data
      if (errorData?.requires_2fa) {
        setRequires2FA(true)
        setError(t('securityQuestions.2faRequired') || '2FA code required')
      } else {
        setError(errorData?.error || t('securityQuestions.setupError') || 'Failed to save security questions')
      }
    } finally {
      setIsLoading(false)
    }
  }
  
  if (!isOpen) return null
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-[var(--color-bg-card)] rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-[var(--color-accent)]/10">
              <span className="text-[var(--color-accent)]">{Icons.shield}</span>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                {t('securityQuestions.title') || 'Security Questions'}
              </h2>
              <p className="text-xs text-[var(--color-text-muted)]">
                {t('securityQuestions.subtitle') || 'For account recovery'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]"
          >
            {Icons.close}
          </button>
        </div>
        
        {/* Content */}
        <div className="p-6">
          {/* Step 1: Introduction */}
          {step === 1 && (
            <div className="text-center">
              <div className="mx-auto w-16 h-16 bg-[var(--color-accent)]/10 rounded-full flex items-center justify-center mb-4">
                {Icons.questionMark}
              </div>
              <h3 className="text-lg font-medium mb-2">
                {isConfigured 
                  ? (t('securityQuestions.updateTitle') || 'Update Security Questions')
                  : (t('securityQuestions.setupTitle') || 'Set Up Security Questions')}
              </h3>
              <p className="text-sm text-[var(--color-text-muted)] mb-6">
                {t('securityQuestions.description') || 
                  'Security questions provide an alternative way to recover your account if you forget your password and cannot access your email.'}
              </p>
              
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4 mb-6 text-left">
                <h4 className="font-medium text-amber-600 dark:text-amber-400 mb-2">
                  {t('securityQuestions.tipsTitle') || 'Tips for good answers:'}
                </h4>
                <ul className="text-sm text-[var(--color-text-muted)] space-y-1">
                  <li>• {t('securityQuestions.tip1') || 'Choose answers only you would know'}</li>
                  <li>• {t('securityQuestions.tip2') || 'Answers are case-insensitive'}</li>
                  <li>• {t('securityQuestions.tip3') || "Don't share your answers with anyone"}</li>
                </ul>
              </div>
              
              <button
                onClick={() => setStep(2)}
                className="w-full bg-[var(--color-accent)] text-white py-3 rounded-lg font-medium hover:opacity-90 transition-opacity"
              >
                {t('common.continue') || 'Continue'}
              </button>
            </div>
          )}
          
          {/* Step 2: Select Questions */}
          {step === 2 && (
            <div>
              <h3 className="text-lg font-medium mb-4">
                {t('securityQuestions.chooseQuestions') || 'Choose Your Questions'}
              </h3>
              <p className="text-sm text-[var(--color-text-muted)] mb-6">
                {t('securityQuestions.chooseDescription') || 'Select at least 2 questions and provide memorable answers.'}
              </p>
              
              <div className="space-y-4">
                {selectedQuestions.map((q, index) => (
                  <div key={index} className="bg-[var(--color-bg-tertiary)] rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">
                        {t('securityQuestions.question') || 'Question'} {index + 1}
                      </span>
                      {selectedQuestions.length > 2 && (
                        <button
                          onClick={() => handleRemoveQuestion(index)}
                          className="p-1 text-red-500 hover:bg-red-500/10 rounded"
                        >
                          {Icons.trash}
                        </button>
                      )}
                    </div>
                    
                    <select
                      value={q.question}
                      onChange={(e) => handleQuestionChange(index, 'question', e.target.value)}
                      className="w-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm mb-2"
                    >
                      <option value="">{t('securityQuestions.selectQuestion') || 'Select a question...'}</option>
                      {availableQuestions
                        .filter(aq => !selectedQuestions.some((sq, i) => i !== index && sq.question === aq))
                        .map((aq, i) => (
                          <option key={i} value={aq}>{translateQuestion(aq)}</option>
                        ))}
                    </select>
                    
                    <input
                      type="text"
                      value={q.answer}
                      onChange={(e) => handleQuestionChange(index, 'answer', e.target.value)}
                      placeholder={t('securityQuestions.yourAnswer') || 'Your answer...'}
                      className="w-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
                    />
                  </div>
                ))}
                
                {selectedQuestions.length < 5 && (
                  <button
                    onClick={handleAddQuestion}
                    className="w-full flex items-center justify-center gap-2 py-2 border border-dashed border-[var(--color-border)] rounded-lg text-sm text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors"
                  >
                    {Icons.plus}
                    {t('securityQuestions.addAnother') || 'Add another question'}
                  </button>
                )}
              </div>
              
              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setStep(1)}
                  className="flex-1 py-2 border border-[var(--color-border)] rounded-lg text-sm hover:bg-[var(--color-bg-tertiary)]"
                >
                  {t('common.back') || 'Back'}
                </button>
                <button
                  onClick={() => setStep(3)}
                  disabled={!isQuestionsValid()}
                  className="flex-1 bg-[var(--color-accent)] text-white py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {t('common.continue') || 'Continue'}
                </button>
              </div>
            </div>
          )}
          
          {/* Step 3: Verify Password */}
          {step === 3 && (
            <div>
              <h3 className="text-lg font-medium mb-4">
                {t('securityQuestions.verifyIdentity') || 'Verify Your Identity'}
              </h3>
              <p className="text-sm text-[var(--color-text-muted)] mb-6">
                {t('securityQuestions.verifyDescription') || 'Enter your password to confirm these changes.'}
              </p>
              
              {error && (
                <div className="bg-red-500/10 border border-red-500/20 text-red-500 rounded-lg p-3 mb-4 text-sm">
                  {error}
                </div>
              )}
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">
                    {t('profile.currentPassword') || 'Current Password'}
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]">
                      {Icons.lock}
                    </span>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg pl-10 pr-3 py-2"
                      placeholder="••••••••"
                    />
                  </div>
                </div>
                
                {requires2FA && (
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      {t('auth.twoFactorCode') || '2FA Code'}
                    </label>
                    <input
                      type="text"
                      value={totpCode}
                      onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-center tracking-widest font-mono"
                      placeholder="000000"
                      maxLength={6}
                    />
                  </div>
                )}
              </div>
              
              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setStep(2)}
                  className="flex-1 py-2 border border-[var(--color-border)] rounded-lg text-sm hover:bg-[var(--color-bg-tertiary)]"
                  disabled={isLoading}
                >
                  {t('common.back') || 'Back'}
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={!password || isLoading || (requires2FA && totpCode.length !== 6)}
                  className="flex-1 bg-[var(--color-accent)] text-white py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isLoading ? (
                    <>
                      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      {t('common.saving') || 'Saving...'}
                    </>
                  ) : (
                    t('securityQuestions.saveQuestions') || 'Save Questions'
                  )}
                </button>
              </div>
            </div>
          )}
          
          {/* Step 4: Success */}
          {step === 4 && (
            <div className="text-center py-6">
              <div className="mx-auto w-16 h-16 bg-green-500/10 rounded-full flex items-center justify-center mb-4">
                <span className="text-green-500">{Icons.check}</span>
              </div>
              <h3 className="text-lg font-medium mb-2 text-green-500">
                {t('securityQuestions.successTitle') || 'Security Questions Saved!'}
              </h3>
              <p className="text-sm text-[var(--color-text-muted)] mb-6">
                {t('securityQuestions.successDescription') || 
                  'You can now use these questions to recover your account if you forget your password.'}
              </p>
              <button
                onClick={onClose}
                className="px-6 py-2 bg-[var(--color-accent)] text-white rounded-lg font-medium hover:opacity-90"
              >
                {t('common.done') || 'Done'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
