/**
 * GearCargo - Two-Factor Authentication Setup Component
 * Complete 2FA flow with QR code, verification, backup codes, and PDF download
 */

import { useState, useEffect, useRef } from 'react'
import { jsPDF } from 'jspdf'
import api from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { formatDate, formatDateTime } from '../../utils/dateFormat'

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
  download: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  ),
  copy: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  ),
  warning: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  refresh: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </svg>
  ),
  key: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
    </svg>
  ),
  arrowLeft: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
    </svg>
  ),
  arrowRight: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
    </svg>
  ),
}

// Step indicator component
const StepIndicator = ({ currentStep, totalSteps, t }) => {
  const steps = [
    { num: 1, label: t('twoFactor.stepSetup') || 'Setup' },
    { num: 2, label: t('twoFactor.stepVerify') || 'Verify' },
    { num: 3, label: t('twoFactor.stepBackup') || 'Backup' },
    { num: 4, label: t('twoFactor.stepComplete') || 'Complete' },
  ]
  
  return (
    <div className="flex items-center justify-center gap-2 mb-6">
      {steps.slice(0, totalSteps).map((step, idx) => (
        <div key={step.num} className="flex items-center">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
            currentStep > step.num 
              ? 'bg-green-500 text-white' 
              : currentStep === step.num 
                ? 'bg-[var(--color-accent)] text-white' 
                : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]'
          }`}>
            {currentStep > step.num ? Icons.check : step.num}
          </div>
          {idx < totalSteps - 1 && (
            <div className={`w-8 h-0.5 mx-1 ${
              currentStep > step.num ? 'bg-green-500' : 'bg-[var(--color-bg-tertiary)]'
            }`} />
          )}
        </div>
      ))}
    </div>
  )
}

export default function TwoFactorSetup({ isOpen, onClose, onSuccess, isEnabled = false }) {
  const { t } = useTranslation()
  const { refreshUser } = useAuth()
  
  // Setup flow states
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  
  // 2FA setup data
  const [qrCode, setQrCode] = useState('')
  const [secret, setSecret] = useState('')
  const [verificationCode, setVerificationCode] = useState('')
  const [backupCodes, setBackupCodes] = useState([])
  
  // Disable 2FA states
  const [showDisable, setShowDisable] = useState(false)
  const [disablePassword, setDisablePassword] = useState('')
  
  // Regenerate backup codes states
  const [showRegenerate, setShowRegenerate] = useState(false)
  const [regeneratePassword, setRegeneratePassword] = useState('')
  
  // Backup codes saved confirmation
  const [backupCodesSaved, setBackupCodesSaved] = useState(false)
  
  const codeInputRef = useRef(null)
  
  useEffect(() => {
    if (isOpen && !isEnabled) {
      // Start setup flow
      initSetup()
    }
  }, [isOpen])
  
  useEffect(() => {
    if (step === 2 && codeInputRef.current) {
      codeInputRef.current.focus()
    }
  }, [step])
  
  const initSetup = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.post('/auth/2fa/setup')
      setQrCode(response.data.qr_code)
      setSecret(response.data.secret)
    } catch (err) {
      setError(err.response?.data?.error || t('common.errorOccurred') || 'An error occurred')
    } finally {
      setLoading(false)
    }
  }
  
  const handleVerify = async (e) => {
    e.preventDefault()
    if (verificationCode.length !== 6) {
      setError(t('twoFactor.enterSixDigit') || 'Please enter a 6-digit code')
      return
    }
    
    setLoading(true)
    setError('')
    try {
      const response = await api.post('/auth/2fa/verify', { code: verificationCode })
      setBackupCodes(response.data.backup_codes)
      setStep(3)
    } catch (err) {
      setError(err.response?.data?.error || t('twoFactor.invalidCode') || 'Invalid code')
    } finally {
      setLoading(false)
    }
  }
  
  const handleDisable = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await api.post('/auth/2fa/disable', { password: disablePassword })
      await refreshUser()
      onSuccess?.()
      onClose()
    } catch (err) {
      setError(err.response?.data?.error || t('common.errorOccurred') || 'An error occurred')
    } finally {
      setLoading(false)
    }
  }
  
  const handleRegenerate = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const response = await api.post('/auth/2fa/regenerate-backup', { password: regeneratePassword })
      setBackupCodes(response.data.backup_codes)
      setShowRegenerate(false)
      setRegeneratePassword('')
      setBackupCodesSaved(false)
    } catch (err) {
      setError(err.response?.data?.error || t('common.errorOccurred') || 'An error occurred')
    } finally {
      setLoading(false)
    }
  }
  
  const copySecret = () => {
    navigator.clipboard.writeText(secret)
  }
  
  const copyBackupCodes = () => {
    navigator.clipboard.writeText(backupCodes.join('\n'))
  }
  
  const downloadBackupCodesPDF = () => {
    // Create PDF document
    const doc = new jsPDF()
    const pageWidth = doc.internal.pageSize.getWidth()
    
    // Header background
    doc.setFillColor(26, 26, 46) // Dark blue header
    doc.rect(0, 0, pageWidth, 35, 'F')
    
    // Logo/Title
    doc.setTextColor(255, 255, 255)
    doc.setFontSize(24)
    doc.setFont('helvetica', 'bold')
    doc.text('GearCargo', 20, 18)
    
    doc.setFontSize(11)
    doc.setFont('helvetica', 'normal')
    doc.text(t('twoFactor.backupCodesTitle') || 'Two-Factor Authentication Backup Codes', 20, 28)
    
    // User info section
    doc.setTextColor(51, 51, 51)
    doc.setFontSize(14)
    doc.setFont('helvetica', 'bold')
    doc.text(t('twoFactor.accountInfo') || 'Account Information', 20, 50)
    
    doc.setFontSize(10)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(102, 102, 102)
    const userEmail = localStorage.getItem('userEmail') || 'user@example.com'
    doc.text(`${t('common.email') || 'Email'}: ${userEmail}`, 20, 60)
    doc.text(`${t('twoFactor.generatedOn') || 'Generated'}: ${formatDate(new Date())}`, 20, 68)
    
    // Warning box
    doc.setFillColor(255, 243, 205) // Light yellow background
    doc.setDrawColor(255, 193, 7) // Amber border
    doc.setLineWidth(0.5)
    doc.roundedRect(20, 78, pageWidth - 40, 28, 2, 2, 'FD')
    
    doc.setTextColor(133, 100, 4) // Dark amber text
    doc.setFontSize(10)
    doc.setFont('helvetica', 'bold')
    doc.text('⚠ ' + (t('twoFactor.importantWarning') || 'IMPORTANT'), 25, 88)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(9)
    doc.text(t('twoFactor.keepSecure') || 'Keep these codes secure. Each code can only be used once.', 25, 96)
    doc.text(t('twoFactor.lostAccess') || 'If you lose access to your authenticator app, use these codes to login.', 25, 103)
    
    // Backup codes section
    doc.setTextColor(51, 51, 51)
    doc.setFontSize(14)
    doc.setFont('helvetica', 'bold')
    doc.text(t('twoFactor.yourBackupCodes') || 'Your Backup Codes', 20, 125)
    
    // Codes grid
    const codesPerRow = 2
    const codeBoxWidth = 70
    const codeBoxHeight = 12
    const startX = 30
    const startY = 135
    const gapX = 80
    const gapY = 16
    
    doc.setFontSize(12)
    
    backupCodes.forEach((code, index) => {
      const row = Math.floor(index / codesPerRow)
      const col = index % codesPerRow
      const x = startX + col * gapX
      const y = startY + row * gapY
      
      // Code background
      doc.setFillColor(245, 245, 245)
      doc.roundedRect(x - 5, y - 6, codeBoxWidth, codeBoxHeight, 1, 1, 'F')
      
      // Code number
      doc.setTextColor(153, 153, 153)
      doc.setFontSize(8)
      doc.setFont('helvetica', 'normal')
      doc.text(`${index + 1}.`, x - 2, y + 2)
      
      // Code text
      doc.setTextColor(26, 26, 46)
      doc.setFontSize(12)
      doc.setFont('courier', 'bold')
      doc.text(code, x + 8, y + 2)
    })
    
    // Footer instructions
    const footerY = startY + Math.ceil(backupCodes.length / codesPerRow) * gapY + 20
    
    doc.setTextColor(102, 102, 102)
    doc.setFontSize(10)
    doc.setFont('helvetica', 'normal')
    doc.text(t('twoFactor.usageInstructions') || 'How to use:', 20, footerY)
    doc.text('1. ' + (t('twoFactor.instruction1') || 'When prompted for 2FA code, click "Use backup code"'), 20, footerY + 8)
    doc.text('2. ' + (t('twoFactor.instruction2') || 'Enter one of the codes above'), 20, footerY + 16)
    doc.text('3. ' + (t('twoFactor.instruction3') || 'Each code can only be used once - cross it off after use'), 20, footerY + 24)
    
    // Page footer
    doc.setTextColor(153, 153, 153)
    doc.setFontSize(8)
    doc.text('GearCargo - Vehicle Management App', 20, 280)
    doc.text(`${t('twoFactor.documentGenerated') || 'Document generated'}: ${formatDateTime(new Date())}`, 20, 286)
    
    // Save PDF
    const username = localStorage.getItem('username') || 'user'
    doc.save(`GearCargo_${username}_backup_codes.pdf`)
    
    setBackupCodesSaved(true)
  }
  
  const handleComplete = async () => {
    if (!backupCodesSaved) {
      setError(t('twoFactor.pleaseDownload') || 'Please download your backup codes first')
      return
    }
    await refreshUser()
    setStep(4)
    setTimeout(() => {
      onSuccess?.()
      onClose()
    }, 2000)
  }
  
  const handleClose = () => {
    // Reset all states
    setStep(1)
    setQrCode('')
    setSecret('')
    setVerificationCode('')
    setBackupCodes([])
    setError('')
    setShowDisable(false)
    setShowRegenerate(false)
    setDisablePassword('')
    setRegeneratePassword('')
    setBackupCodesSaved(false)
    onClose()
  }
  
  if (!isOpen) return null
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-[var(--color-bg-card)] rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-[var(--color-bg-card)] px-6 py-4 border-b border-[var(--color-border)] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-[var(--color-accent)]/10 flex items-center justify-center text-[var(--color-accent)]">
              {Icons.shield}
            </div>
            <div>
              <h2 className="font-semibold">{t('twoFactor.title') || 'Two-Factor Authentication'}</h2>
              <p className="text-xs text-[var(--color-text-muted)]">
                {isEnabled 
                  ? (t('twoFactor.manage') || 'Manage your 2FA settings') 
                  : (t('twoFactor.setup') || 'Secure your account')}
              </p>
            </div>
          </div>
          <button onClick={handleClose} className="btn-icon">
            {Icons.close}
          </button>
        </div>
        
        {/* Content */}
        <div className="p-6">
          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-500 text-sm flex items-center gap-2">
              {Icons.warning}
              {error}
            </div>
          )}
          
          {/* If 2FA is already enabled - show manage options */}
          {isEnabled && !showDisable && !showRegenerate && backupCodes.length === 0 && (
            <div className="space-y-4">
              <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-xl text-center">
                <div className="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-3">
                  <span className="text-green-500">{Icons.check}</span>
                </div>
                <p className="text-green-500 font-medium">{t('twoFactor.enabled') || '2FA is enabled'}</p>
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  {t('twoFactor.accountProtected') || 'Your account is protected with two-factor authentication'}
                </p>
              </div>
              
              <div className="space-y-3">
                <button
                  onClick={() => setShowRegenerate(true)}
                  className="btn btn-secondary w-full flex items-center justify-center gap-2"
                >
                  {Icons.refresh}
                  {t('twoFactor.regenerateBackup') || 'Regenerate Backup Codes'}
                </button>
                
                <button
                  onClick={() => setShowDisable(true)}
                  className="btn w-full border-red-500 text-red-500 hover:bg-red-500/10 flex items-center justify-center gap-2"
                >
                  {t('twoFactor.disable') || 'Disable 2FA'}
                </button>
              </div>
            </div>
          )}
          
          {/* Disable 2FA form */}
          {showDisable && (
            <form onSubmit={handleDisable} className="space-y-4">
              <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl">
                <p className="text-sm text-red-500 font-medium mb-2">
                  {Icons.warning} {t('twoFactor.disableWarning') || 'Warning'}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('twoFactor.disableDescription') || 'Disabling 2FA will make your account less secure. Enter your password to confirm.'}
                </p>
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">
                  {t('common.password') || 'Password'}
                </label>
                <input
                  type="password"
                  value={disablePassword}
                  onChange={(e) => setDisablePassword(e.target.value)}
                  className="input w-full"
                  placeholder={t('twoFactor.enterPassword') || 'Enter your password'}
                  required
                />
              </div>
              
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => { setShowDisable(false); setDisablePassword(''); setError(''); }}
                  className="btn btn-secondary flex-1"
                >
                  {t('common.cancel') || 'Cancel'}
                </button>
                <button
                  type="submit"
                  disabled={loading || !disablePassword}
                  className="btn bg-red-500 text-white hover:bg-red-600 flex-1"
                >
                  {loading ? (t('common.loading') || 'Loading...') : (t('twoFactor.confirmDisable') || 'Disable 2FA')}
                </button>
              </div>
            </form>
          )}
          
          {/* Regenerate backup codes form */}
          {showRegenerate && backupCodes.length === 0 && (
            <form onSubmit={handleRegenerate} className="space-y-4">
              <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl">
                <p className="text-sm text-amber-500 font-medium mb-2">
                  {Icons.warning} {t('twoFactor.regenerateWarning') || 'Warning'}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('twoFactor.regenerateDescription') || 'This will invalidate all existing backup codes. Make sure to save the new ones.'}
                </p>
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">
                  {t('common.password') || 'Password'}
                </label>
                <input
                  type="password"
                  value={regeneratePassword}
                  onChange={(e) => setRegeneratePassword(e.target.value)}
                  className="input w-full"
                  placeholder={t('twoFactor.enterPassword') || 'Enter your password'}
                  required
                />
              </div>
              
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => { setShowRegenerate(false); setRegeneratePassword(''); setError(''); }}
                  className="btn btn-secondary flex-1"
                >
                  {t('common.cancel') || 'Cancel'}
                </button>
                <button
                  type="submit"
                  disabled={loading || !regeneratePassword}
                  className="btn btn-primary flex-1"
                >
                  {loading ? (t('common.loading') || 'Loading...') : (t('twoFactor.regenerate') || 'Regenerate')}
                </button>
              </div>
            </form>
          )}
          
          {/* Show regenerated backup codes */}
          {isEnabled && backupCodes.length > 0 && (
            <div className="space-y-4">
              <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl">
                <p className="text-sm text-amber-500 font-medium mb-2">
                  {Icons.key} {t('twoFactor.newBackupCodes') || 'New Backup Codes'}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('twoFactor.saveNewCodes') || 'Save these new backup codes. Your old codes are no longer valid.'}
                </p>
              </div>
              
              <div className="grid grid-cols-2 gap-2 p-4 bg-[var(--color-bg-tertiary)] rounded-xl">
                {backupCodes.map((code, index) => (
                  <div key={index} className="font-mono text-sm p-2 bg-[var(--color-bg-secondary)] rounded text-center">
                    {code}
                  </div>
                ))}
              </div>
              
              <div className="flex gap-3">
                <button
                  onClick={copyBackupCodes}
                  className="btn btn-secondary flex-1 flex items-center justify-center gap-2"
                >
                  {Icons.copy}
                  {t('common.copy') || 'Copy'}
                </button>
                <button
                  onClick={downloadBackupCodesPDF}
                  className="btn btn-primary flex-1 flex items-center justify-center gap-2"
                >
                  {Icons.download}
                  {t('twoFactor.downloadPDF') || 'Download'}
                </button>
              </div>
              
              <button
                onClick={() => { setBackupCodes([]); handleClose(); }}
                className="btn btn-ghost w-full"
              >
                {t('common.done') || 'Done'}
              </button>
            </div>
          )}
          
          {/* Setup flow - Step 1: QR Code */}
          {!isEnabled && step === 1 && (
            <div className="space-y-4">
              <StepIndicator currentStep={step} totalSteps={4} t={t} />
              
              <div className="text-center">
                <h3 className="font-medium mb-2">{t('twoFactor.scanQRCode') || 'Scan QR Code'}</h3>
                <p className="text-xs text-[var(--color-text-muted)] mb-4">
                  {t('twoFactor.scanInstructions') || 'Use an authenticator app like Google Authenticator, Authy, or 1Password to scan this QR code'}
                </p>
              </div>
              
              {loading ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin w-8 h-8 border-2 border-[var(--color-accent)] border-t-transparent rounded-full" />
                </div>
              ) : qrCode ? (
                <>
                  <div className="flex justify-center p-4 bg-white rounded-xl">
                    <img src={qrCode} alt="2FA QR Code" className="w-48 h-48" />
                  </div>
                  
                  <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-xl">
                    <p className="text-xs text-[var(--color-text-muted)] mb-2 text-center">
                      {t('twoFactor.cantScan') || "Can't scan? Enter this code manually:"}
                    </p>
                    <div className="flex items-center gap-2 justify-center">
                      <code className="font-mono text-sm bg-[var(--color-bg-secondary)] px-3 py-1 rounded">
                        {secret}
                      </code>
                      <button onClick={copySecret} className="btn-icon text-[var(--color-text-secondary)]">
                        {Icons.copy}
                      </button>
                    </div>
                  </div>
                  
                  <button
                    onClick={() => setStep(2)}
                    className="btn btn-primary w-full flex items-center justify-center gap-2"
                  >
                    {t('common.next') || 'Next'}
                    {Icons.arrowRight}
                  </button>
                </>
              ) : null}
            </div>
          )}
          
          {/* Setup flow - Step 2: Verify */}
          {!isEnabled && step === 2 && (
            <div className="space-y-4">
              <StepIndicator currentStep={step} totalSteps={4} t={t} />
              
              <div className="text-center">
                <h3 className="font-medium mb-2">{t('twoFactor.verifySetup') || 'Verify Setup'}</h3>
                <p className="text-xs text-[var(--color-text-muted)] mb-4">
                  {t('twoFactor.enterCode') || 'Enter the 6-digit code from your authenticator app'}
                </p>
              </div>
              
              <form onSubmit={handleVerify} className="space-y-4">
                <div>
                  <input
                    ref={codeInputRef}
                    type="text"
                    value={verificationCode}
                    onChange={(e) => {
                      const value = e.target.value.replace(/\D/g, '').slice(0, 6)
                      setVerificationCode(value)
                    }}
                    className="input w-full text-center text-2xl tracking-[0.5em] font-mono"
                    placeholder="000000"
                    maxLength={6}
                    autoComplete="one-time-code"
                  />
                </div>
                
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="btn btn-secondary flex-1 flex items-center justify-center gap-2"
                  >
                    {Icons.arrowLeft}
                    {t('common.back') || 'Back'}
                  </button>
                  <button
                    type="submit"
                    disabled={loading || verificationCode.length !== 6}
                    className="btn btn-primary flex-1"
                  >
                    {loading ? (t('common.verifying') || 'Verifying...') : (t('common.verify') || 'Verify')}
                  </button>
                </div>
              </form>
            </div>
          )}
          
          {/* Setup flow - Step 3: Backup Codes */}
          {!isEnabled && step === 3 && (
            <div className="space-y-4">
              <StepIndicator currentStep={step} totalSteps={4} t={t} />
              
              <div className="text-center">
                <h3 className="font-medium mb-2">{t('twoFactor.saveBackupCodes') || 'Save Backup Codes'}</h3>
                <p className="text-xs text-[var(--color-text-muted)] mb-4">
                  {t('twoFactor.backupCodesDescription') || 'Save these codes in a safe place. You can use them to access your account if you lose your phone.'}
                </p>
              </div>
              
              <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl">
                <p className="text-sm text-amber-500 font-medium flex items-center gap-2">
                  {Icons.warning}
                  {t('twoFactor.importantWarning') || 'Important'}
                </p>
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  {t('twoFactor.codesOnlyOnce') || 'These codes will only be shown once. Download them now!'}
                </p>
              </div>
              
              <div className="grid grid-cols-2 gap-2 p-4 bg-[var(--color-bg-tertiary)] rounded-xl">
                {backupCodes.map((code, index) => (
                  <div key={index} className="font-mono text-sm p-2 bg-[var(--color-bg-secondary)] rounded text-center">
                    {code}
                  </div>
                ))}
              </div>
              
              <div className="flex gap-3">
                <button
                  onClick={copyBackupCodes}
                  className="btn btn-secondary flex-1 flex items-center justify-center gap-2"
                >
                  {Icons.copy}
                  {t('common.copy') || 'Copy'}
                </button>
                <button
                  onClick={downloadBackupCodesPDF}
                  className="btn btn-primary flex-1 flex items-center justify-center gap-2"
                >
                  {Icons.download}
                  {t('twoFactor.downloadPDF') || 'Download'}
                </button>
              </div>
              
              {backupCodesSaved && (
                <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-green-500 text-sm flex items-center gap-2">
                  {Icons.check}
                  {t('twoFactor.codesSaved') || 'Backup codes downloaded!'}
                </div>
              )}
              
              <button
                onClick={handleComplete}
                disabled={!backupCodesSaved}
                className={`btn w-full flex items-center justify-center gap-2 ${
                  backupCodesSaved ? 'btn-primary' : 'btn-secondary opacity-50'
                }`}
              >
                {t('twoFactor.complete') || 'Complete Setup'}
                {Icons.arrowRight}
              </button>
            </div>
          )}
          
          {/* Setup flow - Step 4: Complete */}
          {!isEnabled && step === 4 && (
            <div className="space-y-4 text-center py-8">
              <div className="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-4">
                <span className="text-green-500 scale-150">{Icons.check}</span>
              </div>
              <h3 className="font-medium text-lg text-green-500">
                {t('twoFactor.setupComplete') || '2FA Setup Complete!'}
              </h3>
              <p className="text-sm text-[var(--color-text-muted)]">
                {t('twoFactor.accountSecured') || 'Your account is now protected with two-factor authentication'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
