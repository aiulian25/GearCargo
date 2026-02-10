/**
 * GearCargo - Privacy Policy Component
 * Displays comprehensive privacy policy information in a modal
 */

import { useTranslation } from '../../contexts/LanguageContext'

// Icons
const Icons = {
  close: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  shield: (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  lock: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  ),
  database: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
    </svg>
  ),
  userX: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="18" y1="8" x2="23" y2="13"/><line x1="23" y1="8" x2="18" y2="13"/>
    </svg>
  ),
  eye: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
    </svg>
  ),
  trash: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </svg>
  ),
  check: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
}

// Section component for consistent styling
const PolicySection = ({ icon, title, children }) => (
  <div className="mb-6">
    <div className="flex items-center gap-3 mb-3">
      <span className="text-[var(--color-accent)]">{icon}</span>
      <h3 className="text-lg font-semibold text-[var(--color-text)]">{title}</h3>
    </div>
    <div className="pl-8 text-[var(--color-text-secondary)] leading-relaxed">
      {children}
    </div>
  </div>
)

// Bullet point component
const BulletPoint = ({ children }) => (
  <div className="flex items-start gap-2 mb-2">
    <span className="text-green-500 mt-1 flex-shrink-0">{Icons.check}</span>
    <span>{children}</span>
  </div>
)

export default function PrivacyPolicy({ isOpen, onClose }) {
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
            <span className="text-[var(--color-accent)]">{Icons.shield}</span>
            <div>
              <h2 className="text-xl font-bold text-[var(--color-text)]">
                {t('privacy.title')}
              </h2>
              <p className="text-sm text-[var(--color-text-muted)]">
                {t('privacy.lastUpdated')}: February 2026
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
          {/* Introduction */}
          <div className="mb-6 p-4 bg-[var(--color-accent)]/10 rounded-xl border border-[var(--color-accent)]/20">
            <p className="text-[var(--color-text)] leading-relaxed">
              {t('privacy.intro')}
            </p>
          </div>

          {/* Data Collection */}
          <PolicySection icon={Icons.database} title={t('privacy.dataCollectionTitle')}>
            <p className="mb-3">{t('privacy.dataCollectionDesc')}</p>
            <BulletPoint>{t('privacy.dataCollectionItem1')}</BulletPoint>
            <BulletPoint>{t('privacy.dataCollectionItem2')}</BulletPoint>
            <BulletPoint>{t('privacy.dataCollectionItem3')}</BulletPoint>
            <BulletPoint>{t('privacy.dataCollectionItem4')}</BulletPoint>
          </PolicySection>

          {/* Data Security */}
          <PolicySection icon={Icons.lock} title={t('privacy.dataSecurityTitle')}>
            <p className="mb-3">{t('privacy.dataSecurityDesc')}</p>
            <BulletPoint>{t('privacy.dataSecurityItem1')}</BulletPoint>
            <BulletPoint>{t('privacy.dataSecurityItem2')}</BulletPoint>
            <BulletPoint>{t('privacy.dataSecurityItem3')}</BulletPoint>
            <BulletPoint>{t('privacy.dataSecurityItem4')}</BulletPoint>
          </PolicySection>

          {/* No Third-Party Sharing */}
          <PolicySection icon={Icons.userX} title={t('privacy.noThirdPartyTitle')}>
            <div className="p-4 bg-green-500/10 rounded-lg border border-green-500/20 mb-3">
              <p className="text-green-400 font-medium">{t('privacy.noThirdPartyHighlight')}</p>
            </div>
            <p className="mb-3">{t('privacy.noThirdPartyDesc')}</p>
            <BulletPoint>{t('privacy.noThirdPartyItem1')}</BulletPoint>
            <BulletPoint>{t('privacy.noThirdPartyItem2')}</BulletPoint>
            <BulletPoint>{t('privacy.noThirdPartyItem3')}</BulletPoint>
          </PolicySection>

          {/* Data Access */}
          <PolicySection icon={Icons.eye} title={t('privacy.dataAccessTitle')}>
            <p className="mb-3">{t('privacy.dataAccessDesc')}</p>
            <BulletPoint>{t('privacy.dataAccessItem1')}</BulletPoint>
            <BulletPoint>{t('privacy.dataAccessItem2')}</BulletPoint>
            <BulletPoint>{t('privacy.dataAccessItem3')}</BulletPoint>
          </PolicySection>

          {/* Data Deletion */}
          <PolicySection icon={Icons.trash} title={t('privacy.dataDeletionTitle')}>
            <p className="mb-3">{t('privacy.dataDeletionDesc')}</p>
            <BulletPoint>{t('privacy.dataDeletionItem1')}</BulletPoint>
            <BulletPoint>{t('privacy.dataDeletionItem2')}</BulletPoint>
            <BulletPoint>{t('privacy.dataDeletionItem3')}</BulletPoint>
          </PolicySection>

          {/* Contact */}
          <div className="mt-8 p-4 bg-[var(--color-bg-tertiary)] rounded-xl">
            <h3 className="font-semibold text-[var(--color-text)] mb-2">
              {t('privacy.contactTitle')}
            </h3>
            <p className="text-[var(--color-text-secondary)] text-sm">
              {t('privacy.contactDesc')}
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
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  )
}
