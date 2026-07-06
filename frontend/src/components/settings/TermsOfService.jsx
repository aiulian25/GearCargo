/**
 * GearCargo - Terms of Service Component
 * Displays comprehensive terms and conditions in a modal
 */

import { useTranslation } from '../../contexts/LanguageContext'

// Icons
const Icons = {
  close: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  gavel: (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v17.25m0 0c-1.472 0-2.882.265-4.185.75M12 20.25c1.472 0 2.882.265 4.185.75M18.75 4.97A48.416 48.416 0 0012 4.5c-2.291 0-4.545.16-6.75.47m13.5 0c1.01.143 2.01.317 3 .52m-3-.52l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.988 5.988 0 01-2.031.352 5.988 5.988 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L18.75 4.971zm-16.5.52c.99-.203 1.99-.377 3-.52m0 0l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.989 5.989 0 01-2.031.352 5.989 5.989 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L5.25 4.971z"/>
    </svg>
  ),
  alertTriangle: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  shield: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  ban: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>
    </svg>
  ),
  lock: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  ),
  fileText: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
    </svg>
  ),
  dollarSign: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
    </svg>
  ),
  check: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  x: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
}

// Section component for consistent styling
const TermsSection = ({ icon, title, children, variant = 'default' }) => (
  <div className="mb-6">
    <div className="flex items-center gap-3 mb-3">
      <span className={variant === 'warning' ? 'text-amber-500' : variant === 'danger' ? 'text-red-500' : 'text-[var(--color-accent)]'}>
        {icon}
      </span>
      <h3 className="text-lg font-semibold text-[var(--color-text)]">{title}</h3>
    </div>
    <div className="pl-8 text-[var(--color-text-secondary)] leading-relaxed">
      {children}
    </div>
  </div>
)

// Bullet point component
const BulletPoint = ({ children, variant = 'default' }) => (
  <div className="flex items-start gap-2 mb-2">
    <span className={`mt-1 flex-shrink-0 ${variant === 'warning' ? 'text-amber-500' : variant === 'danger' ? 'text-red-500' : 'text-green-500'}`}>
      {variant === 'danger' ? Icons.x : Icons.check}
    </span>
    <span>{children}</span>
  </div>
)

export default function TermsOfService({ isOpen, onClose }) {
  const { t } = useTranslation()

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-[var(--color-bg-secondary)] rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-3">
            <span className="text-[var(--color-accent)]">{Icons.gavel}</span>
            <div>
              <h2 className="text-xl font-bold text-[var(--color-text)]">
                {t('terms.title')}
              </h2>
              <p className="text-sm text-[var(--color-text-muted)]">
                {t('terms.lastUpdated')}: July 2026
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-[var(--color-bg-tertiary)] transition-colors text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
          >
            {Icons.close}
          </button>
        </div>
        
        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Important Notice */}
          <div className="mb-6 p-4 bg-amber-500/10 rounded-xl border border-amber-500/20">
            <div className="flex items-start gap-3">
              <span className="text-amber-500 mt-0.5">{Icons.alertTriangle}</span>
              <div>
                <p className="text-amber-400 font-semibold mb-1">{t('terms.importantNotice')}</p>
                <p className="text-[var(--color-text-secondary)] text-sm">
                  {t('terms.importantNoticeDesc')}
                </p>
              </div>
            </div>
          </div>

          {/* Introduction */}
          <div className="mb-6 p-4 bg-[var(--color-accent)]/10 rounded-xl border border-[var(--color-accent)]/20">
            <p className="text-[var(--color-text)] leading-relaxed">
              {t('terms.intro')}
            </p>
          </div>

          {/* Acceptance of Terms */}
          <TermsSection icon={Icons.fileText} title={t('terms.acceptanceTitle')}>
            <p className="mb-3">{t('terms.acceptanceDesc')}</p>
            <BulletPoint>{t('terms.acceptanceItem1')}</BulletPoint>
            <BulletPoint>{t('terms.acceptanceItem2')}</BulletPoint>
            <BulletPoint>{t('terms.acceptanceItem3')}</BulletPoint>
          </TermsSection>

          {/* License (MIT) */}
          <TermsSection icon={Icons.lock} title={t('terms.licenseTitle')}>
            <div className="p-4 bg-[var(--color-bg-tertiary)] rounded-lg border border-[var(--color-border)] mb-3">
              <p className="text-[var(--color-text)] font-medium">{t('terms.licenseHighlight')}</p>
            </div>
            <p className="mb-3">{t('terms.licenseDesc')}</p>
            <BulletPoint>{t('terms.licenseItem1')}</BulletPoint>
            <BulletPoint>{t('terms.licenseItem2')}</BulletPoint>
            <BulletPoint>{t('terms.licenseItem3')}</BulletPoint>
            <BulletPoint>{t('terms.licenseItem4')}</BulletPoint>
          </TermsSection>

          {/* User Obligations - Security */}
          <TermsSection icon={Icons.shield} title={t('terms.securityTitle')} variant="warning">
            <p className="mb-3">{t('terms.securityDesc')}</p>
            <BulletPoint>{t('terms.securityItem1')}</BulletPoint>
            <BulletPoint>{t('terms.securityItem2')}</BulletPoint>
            <BulletPoint>{t('terms.securityItem3')}</BulletPoint>
            <BulletPoint>{t('terms.securityItem4')}</BulletPoint>
          </TermsSection>

          {/* Prohibited Activities */}
          <TermsSection icon={Icons.ban} title={t('terms.prohibitedTitle')} variant="danger">
            <p className="mb-3">{t('terms.prohibitedDesc')}</p>
            <BulletPoint variant="danger">{t('terms.prohibitedItem1')}</BulletPoint>
            <BulletPoint variant="danger">{t('terms.prohibitedItem2')}</BulletPoint>
            <BulletPoint variant="danger">{t('terms.prohibitedItem3')}</BulletPoint>
            <BulletPoint variant="danger">{t('terms.prohibitedItem4')}</BulletPoint>
            <BulletPoint variant="danger">{t('terms.prohibitedItem5')}</BulletPoint>
          </TermsSection>

          {/* Account Termination */}
          <TermsSection icon={Icons.alertTriangle} title={t('terms.terminationTitle')} variant="warning">
            <div className="p-4 bg-red-500/10 rounded-lg border border-red-500/20 mb-3">
              <p className="text-red-400 font-medium">{t('terms.terminationWarning')}</p>
            </div>
            <p className="mb-3">{t('terms.terminationDesc')}</p>
            <BulletPoint variant="warning">{t('terms.terminationItem1')}</BulletPoint>
            <BulletPoint variant="warning">{t('terms.terminationItem2')}</BulletPoint>
            <BulletPoint variant="warning">{t('terms.terminationItem3')}</BulletPoint>
            <BulletPoint variant="warning">{t('terms.terminationItem4')}</BulletPoint>
          </TermsSection>

          {/* Monetization */}
          <TermsSection icon={Icons.dollarSign} title={t('terms.monetizationTitle')}>
            <p className="mb-3">{t('terms.monetizationDesc')}</p>
            <BulletPoint>{t('terms.monetizationItem1')}</BulletPoint>
            <BulletPoint>{t('terms.monetizationItem2')}</BulletPoint>
            <BulletPoint>{t('terms.monetizationItem3')}</BulletPoint>
          </TermsSection>

          {/* Disclaimer of Liability */}
          <div className="mb-6 p-4 bg-red-500/10 rounded-xl border border-red-500/20">
            <div className="flex items-center gap-3 mb-3">
              <span className="text-red-500">{Icons.alertTriangle}</span>
              <h3 className="text-lg font-semibold text-red-400">{t('terms.disclaimerTitle')}</h3>
            </div>
            <div className="text-[var(--color-text-secondary)] leading-relaxed space-y-3">
              <p className="font-semibold text-red-400 uppercase text-sm">{t('terms.disclaimerHighlight')}</p>
              <p>{t('terms.disclaimerDesc1')}</p>
              <p>{t('terms.disclaimerDesc2')}</p>
              <p>{t('terms.disclaimerDesc3')}</p>
            </div>
          </div>

          {/* Limitation of Liability */}
          <TermsSection icon={Icons.fileText} title={t('terms.limitationTitle')}>
            <p className="mb-3">{t('terms.limitationDesc')}</p>
            <BulletPoint>{t('terms.limitationItem1')}</BulletPoint>
            <BulletPoint>{t('terms.limitationItem2')}</BulletPoint>
            <BulletPoint>{t('terms.limitationItem3')}</BulletPoint>
          </TermsSection>

          {/* Agreement */}
          <div className="mt-8 p-4 bg-[var(--color-bg-tertiary)] rounded-xl">
            <h3 className="font-semibold text-[var(--color-text)] mb-2">
              {t('terms.agreementTitle')}
            </h3>
            <p className="text-[var(--color-text-secondary)] text-sm">
              {t('terms.agreementDesc')}
            </p>
          </div>

          {/* Contact */}
          <div className="mt-4 p-4 bg-[var(--color-bg-tertiary)] rounded-xl">
            <h3 className="font-semibold text-[var(--color-text)] mb-2">
              {t('terms.contactTitle')}
            </h3>
            <p className="text-[var(--color-text-secondary)] text-sm">
              {t('terms.contactDesc')}
            </p>
            <a 
              href="mailto:gearcargo.team@gmail.com" 
              className="inline-block mt-2 text-[var(--color-accent)] hover:underline text-sm font-medium"
            >
              gearcargo.team@gmail.com
            </a>
          </div>
        </div>
        
        {/* Footer */}
        <div className="p-6 border-t border-[var(--color-border)]">
          <button
            onClick={onClose}
            className="w-full py-3 px-4 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-lg font-medium transition-colors"
          >
            {t('terms.understood')}
          </button>
        </div>
      </div>
    </div>
  )
}
