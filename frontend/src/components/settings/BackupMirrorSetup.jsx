import { useTranslation } from '../../contexts/LanguageContext'
import { BACKUP_MIRROR_GUIDE_URL } from '../../config/brand'

const MARKER_FILE = '.gearcargo-backup-mirror'
const SERVICE_USER_ID = 1000
const OVERRIDE_FILE = 'docker-compose.override.yml'
const START_COMMAND = 'docker compose up -d'
const OVERRIDE_CONTENT = `services:
  gearcargo:
    environment:
      - BACKUP_MIRROR_FOLDER=/mnt/backup-mirror
    volumes:
      - type: bind
        source: /mnt/gearcargo-backups
        target: /mnt/backup-mirror
        bind:
          propagation: rslave`

/** How an administrator turns on the second copy of the backups. Shown only while none is configured. */
export default function BackupMirrorSetup({ icon, chevron }) {
  const { t } = useTranslation()
  return (
    <details className="group bg-(--color-bg-tertiary) rounded-xl">
      <summary className="flex items-center justify-between p-4 cursor-pointer list-none [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-3">
          <span className="text-(--color-text-muted)">{icon}</span>
          <span className="text-left">
            <span className="block text-sm font-medium">{t('backup.mirror.setup.title')}</span>
            <span className="block text-2xs text-(--color-text-muted)">{t('backup.mirror.setup.state')}</span>
          </span>
        </span>
        <span className="text-(--color-text-muted) transition-transform group-open:rotate-180">{chevron}</span>
      </summary>
      <div className="px-4 pb-4 pt-4 space-y-3 border-t border-(--color-border) text-sm">
        <ol className="list-decimal pl-5 space-y-2">
          <li>{t('backup.mirror.setup.storage', { marker: MARKER_FILE })}</li>
          <li>{t('backup.mirror.setup.mount', { id: SERVICE_USER_ID })}</li>
          <li>
            {t('backup.mirror.setup.compose', { file: OVERRIDE_FILE })}
            <pre className="mt-2 p-3 rounded-lg bg-(--color-bg-secondary) text-xs overflow-x-auto select-all"><code>{OVERRIDE_CONTENT}</code></pre>
          </li>
          <li>{t('backup.mirror.setup.start', { command: START_COMMAND })}</li>
        </ol>
        <a href={BACKUP_MIRROR_GUIDE_URL} target="_blank" rel="noopener noreferrer" className="inline-block text-(--color-accent)">
          {t('backup.mirror.setup.guide')}
        </a>
      </div>
    </details>
  )
}
