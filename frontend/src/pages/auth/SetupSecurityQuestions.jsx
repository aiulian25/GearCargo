/**
 * GearCargo - Setup Security Questions Page
 * Shown after first login password change to encourage security question setup
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { authApi } from '../../services/api'
import toast from 'react-hot-toast'

// Icons
const ShieldIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
  </svg>
)

const QuestionIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />
  </svg>
)

const LockIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
  </svg>
)

const CheckIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
  </svg>
)

const PlusIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
  </svg>
)

const TrashIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
  </svg>
)

export default function SetupSecurityQuestions() {
  const { t } = useTranslation()
  const { user, refreshUser } = useAuth()
  const navigate = useNavigate()
  
  const [step, setStep] = useState(1) // 1: intro, 2: questions, 3: success
  const [availableQuestions, setAvailableQuestions] = useState([])
  const [selectedQuestions, setSelectedQuestions] = useState([
    { question: '', answer: '' },
    { question: '', answer: '' },
  ])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  
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
      if (translated && !translated.includes('securityQuestions.questions.')) {
        return translated
      }
    }
    return englishQuestion
  }
  
  // Load available questions on mount
  useEffect(() => {
    loadAvailableQuestions()
  }, [])
  
  const loadAvailableQuestions = async () => {
    try {
      const response = await authApi.getAvailableSecurityQuestions()
      setAvailableQuestions(response.data.questions || [])
    } catch (err) {
      console.error('Failed to load security questions:', err)
    }
  }
  
  const handleSkip = () => {
    toast(t('securityQuestions.skippedMessage') || 'You can set up security questions later in Settings → Security', {
      icon: '💡',
      duration: 5000,
    })
    navigate('/')
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
           new Set(selectedQuestions.map(q => q.question)).size === selectedQuestions.length
  }
  
  const handleSubmit = async () => {
    setIsLoading(true)
    setError('')
    
    try {
      // Note: After forced password change, we have a valid session
      // The backend should allow setting security questions without re-entering password
      // if the session was just authenticated from password change
      await authApi.setSecurityQuestionsFirstTime({
        questions: selectedQuestions,
      })
      
      toast.success(t('securityQuestions.setupSuccess') || 'Security questions saved!')
      await refreshUser()
      setStep(3)
      
      // Auto-redirect after showing success
      setTimeout(() => {
        navigate('/')
      }, 2500)
    } catch (err) {
      const errorData = err.response?.data
      setError(errorData?.error || t('securityQuestions.setupError') || 'Failed to save security questions')
    } finally {
      setIsLoading(false)
    }
  }
  
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-primary)] px-4 py-8">
      <div className="max-w-lg w-full">
        {/* Step 1: Introduction */}
        {step === 1 && (
          <div className="text-center">
            <div className="mx-auto h-20 w-20 bg-[var(--color-accent)]/10 rounded-full flex items-center justify-center mb-6">
              <ShieldIcon className="h-10 w-10 text-[var(--color-accent)]" />
            </div>
            
            <h1 className="text-2xl font-bold text-[var(--color-text-primary)] mb-3">
              {t('securityQuestions.welcomeTitle') || 'One More Step for Security'}
            </h1>
            
            <p className="text-[var(--color-text-secondary)] mb-8">
              {t('securityQuestions.welcomeDescription') || 
                'Set up security questions to help recover your account if you ever forget your password.'}
            </p>
            
            {/* Benefits */}
            <div className="bg-[var(--color-bg-card)] rounded-xl p-6 mb-8 text-left border border-[var(--color-border)]">
              <h3 className="font-medium mb-4 text-[var(--color-text-primary)]">
                {t('securityQuestions.whySetup') || 'Why set up security questions?'}
              </h3>
              <ul className="space-y-3">
                <li className="flex items-start gap-3">
                  <div className="mt-0.5 p-1 rounded bg-green-500/10">
                    <CheckIcon className="w-4 h-4 text-green-500" />
                  </div>
                  <span className="text-sm text-[var(--color-text-secondary)]">
                    {t('securityQuestions.benefit1') || 'Recover your account without email access'}
                  </span>
                </li>
                <li className="flex items-start gap-3">
                  <div className="mt-0.5 p-1 rounded bg-green-500/10">
                    <CheckIcon className="w-4 h-4 text-green-500" />
                  </div>
                  <span className="text-sm text-[var(--color-text-secondary)]">
                    {t('securityQuestions.benefit2') || 'Additional layer of account protection'}
                  </span>
                </li>
                <li className="flex items-start gap-3">
                  <div className="mt-0.5 p-1 rounded bg-green-500/10">
                    <CheckIcon className="w-4 h-4 text-green-500" />
                  </div>
                  <span className="text-sm text-[var(--color-text-secondary)]">
                    {t('securityQuestions.benefit3') || 'Quick and easy - takes less than a minute'}
                  </span>
                </li>
              </ul>
            </div>
            
            <div className="space-y-3">
              <button
                onClick={() => setStep(2)}
                className="w-full bg-[var(--color-accent)] text-white py-3 px-6 rounded-xl font-medium hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
              >
                <QuestionIcon className="w-5 h-5" />
                {t('securityQuestions.setUpNow') || 'Set Up Security Questions'}
              </button>
              
              <button
                onClick={handleSkip}
                className="w-full text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] py-2 text-sm transition-colors"
              >
                {t('securityQuestions.skipForNow') || "Skip for now (you can do this later)"}
              </button>
            </div>
          </div>
        )}
        
        {/* Step 2: Questions Form */}
        {step === 2 && (
          <div>
            <div className="text-center mb-8">
              <div className="mx-auto h-16 w-16 bg-[var(--color-accent)]/10 rounded-full flex items-center justify-center mb-4">
                <QuestionIcon className="h-8 w-8 text-[var(--color-accent)]" />
              </div>
              <h1 className="text-xl font-bold text-[var(--color-text-primary)] mb-2">
                {t('securityQuestions.chooseQuestions') || 'Choose Your Questions'}
              </h1>
              <p className="text-sm text-[var(--color-text-muted)]">
                {t('securityQuestions.chooseDescription') || 'Pick questions with answers only you would know'}
              </p>
            </div>
            
            {error && (
              <div className="bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl p-4 mb-6 text-sm">
                {error}
              </div>
            )}
            
            <div className="space-y-4 mb-6">
              {selectedQuestions.map((q, index) => (
                <div 
                  key={index} 
                  className="bg-[var(--color-bg-card)] rounded-xl p-4 border border-[var(--color-border)]"
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">
                      {t('securityQuestions.question') || 'Question'} {index + 1}
                    </span>
                    {selectedQuestions.length > 2 && (
                      <button
                        onClick={() => handleRemoveQuestion(index)}
                        className="p-1.5 text-red-500 hover:bg-red-500/10 rounded-lg transition-colors"
                      >
                        <TrashIcon className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                  
                  <select
                    value={q.question}
                    onChange={(e) => handleQuestionChange(index, 'question', e.target.value)}
                    className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2.5 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/50"
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
                    className="w-full bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/50"
                  />
                </div>
              ))}
              
              {selectedQuestions.length < 5 && (
                <button
                  onClick={handleAddQuestion}
                  className="w-full flex items-center justify-center gap-2 py-3 border-2 border-dashed border-[var(--color-border)] rounded-xl text-sm text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors"
                >
                  <PlusIcon className="w-4 h-4" />
                  {t('securityQuestions.addAnother') || 'Add another question (optional)'}
                </button>
              )}
            </div>
            
            <div className="flex gap-3">
              <button
                onClick={() => setStep(1)}
                className="flex-1 py-3 border border-[var(--color-border)] rounded-xl text-sm font-medium hover:bg-[var(--color-bg-tertiary)] transition-colors"
                disabled={isLoading}
              >
                {t('common.back') || 'Back'}
              </button>
              <button
                onClick={handleSubmit}
                disabled={!isQuestionsValid() || isLoading}
                className="flex-1 bg-[var(--color-accent)] text-white py-3 rounded-xl text-sm font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
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
                  <>
                    <LockIcon className="w-4 h-4" />
                    {t('securityQuestions.saveQuestions') || 'Save Questions'}
                  </>
                )}
              </button>
            </div>
          </div>
        )}
        
        {/* Step 3: Success */}
        {step === 3 && (
          <div className="text-center">
            <div className="mx-auto h-20 w-20 bg-green-500/10 rounded-full flex items-center justify-center mb-6 animate-bounce">
              <CheckIcon className="h-10 w-10 text-green-500" />
            </div>
            
            <h1 className="text-2xl font-bold text-green-500 mb-3">
              {t('securityQuestions.allSet') || "You're All Set!"}
            </h1>
            
            <p className="text-[var(--color-text-secondary)] mb-6">
              {t('securityQuestions.successMessage') || 
                'Your security questions have been saved. You can use them to recover your account if needed.'}
            </p>
            
            <p className="text-sm text-[var(--color-text-muted)]">
              {t('securityQuestions.redirecting') || 'Redirecting to dashboard...'}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
