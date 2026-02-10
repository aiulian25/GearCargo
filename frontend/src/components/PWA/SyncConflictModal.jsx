/**
 * GearCargo - Sync Conflict Modal
 * UI for resolving data sync conflicts
 */

import React, { useState, useEffect, useCallback } from 'react'
import { useLanguage } from '../../contexts/LanguageContext'
import { 
  getUnresolvedConflicts, 
  resolveConflict, 
  dismissConflict,
  findDifferences,
  ConflictStrategy,
} from '../../db/conflictManager'

const translations = {
  en: {
    title: 'Sync Conflicts',
    subtitle: 'The following items were modified both locally and on the server',
    noConflicts: 'No conflicts to resolve',
    keepLocal: 'Keep My Changes',
    keepServer: 'Use Server Version',
    merge: 'Merge',
    resolveAll: 'Resolve All',
    dismiss: 'Dismiss',
    localVersion: 'Your Changes (Offline)',
    serverVersion: 'Server Version',
    field: 'Field',
    differences: 'Differences',
    resolving: 'Resolving...',
    resolved: 'Resolved!',
    conflict: 'conflict',
    conflicts: 'conflicts',
    vehicle: 'Vehicle',
    fuel: 'Fuel Entry',
    service: 'Service',
    repair: 'Repair',
    reminder: 'Reminder',
    tax: 'Tax',
    insurance: 'Insurance',
  },
  ro: {
    title: 'Conflicte de Sincronizare',
    subtitle: 'Următoarele elemente au fost modificate atât local cât și pe server',
    noConflicts: 'Nu există conflicte',
    keepLocal: 'Păstrează Modificările Mele',
    keepServer: 'Folosește Versiunea Server',
    merge: 'Îmbină',
    resolveAll: 'Rezolvă Toate',
    dismiss: 'Respinge',
    localVersion: 'Modificările Tale (Offline)',
    serverVersion: 'Versiunea Server',
    field: 'Câmp',
    differences: 'Diferențe',
    resolving: 'Se rezolvă...',
    resolved: 'Rezolvat!',
    conflict: 'conflict',
    conflicts: 'conflicte',
    vehicle: 'Vehicul',
    fuel: 'Înregistrare Combustibil',
    service: 'Service',
    repair: 'Reparație',
    reminder: 'Memento',
    tax: 'Taxă',
    insurance: 'Asigurare',
  },
  es: {
    title: 'Conflictos de Sincronización',
    subtitle: 'Los siguientes elementos fueron modificados tanto localmente como en el servidor',
    noConflicts: 'No hay conflictos',
    keepLocal: 'Mantener Mis Cambios',
    keepServer: 'Usar Versión del Servidor',
    merge: 'Combinar',
    resolveAll: 'Resolver Todos',
    dismiss: 'Descartar',
    localVersion: 'Tus Cambios (Sin Conexión)',
    serverVersion: 'Versión del Servidor',
    field: 'Campo',
    differences: 'Diferencias',
    resolving: 'Resolviendo...',
    resolved: '¡Resuelto!',
    conflict: 'conflicto',
    conflicts: 'conflictos',
    vehicle: 'Vehículo',
    fuel: 'Registro de Combustible',
    service: 'Servicio',
    repair: 'Reparación',
    reminder: 'Recordatorio',
    tax: 'Impuesto',
    insurance: 'Seguro',
  },
}

// Single conflict item component
function ConflictItem({ conflict, onResolve, t }) {
  const [expanded, setExpanded] = useState(false)
  const [resolving, setResolving] = useState(false)
  
  const differences = findDifferences(conflict.localData, conflict.serverData)
  const entityLabel = t[conflict.entity] || conflict.entity

  const handleResolve = async (strategy) => {
    setResolving(true)
    try {
      await onResolve(conflict.id, strategy)
    } finally {
      setResolving(false)
    }
  }

  return (
    <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-4 mb-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="px-2 py-1 bg-amber-500/20 text-amber-400 text-xs font-medium rounded">
            {entityLabel}
          </span>
          <span className="text-sm text-[var(--color-text-secondary)]">
            ID: {conflict.entityId}
          </span>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
        >
          <svg 
            className={`w-5 h-5 transition-transform ${expanded ? 'rotate-180' : ''}`} 
            fill="none" 
            viewBox="0 0 24 24" 
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {/* Differences summary */}
      <div className="text-sm text-[var(--color-text-secondary)] mb-3">
        {differences.length} {t.differences.toLowerCase()}
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="mb-4 space-y-3">
          {differences.map((diff, idx) => (
            <div key={idx} className="bg-[var(--color-bg-secondary)] rounded p-3">
              <div className="text-xs font-medium text-[var(--color-text-muted)] mb-2 uppercase">
                {diff.field}
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-xs text-blue-400 mb-1">{t.localVersion}</div>
                  <div className="text-[var(--color-text-primary)] bg-blue-500/10 rounded p-2 break-words">
                    {formatValue(diff.localValue)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-green-400 mb-1">{t.serverVersion}</div>
                  <div className="text-[var(--color-text-primary)] bg-green-500/10 rounded p-2 break-words">
                    {formatValue(diff.serverValue)}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => handleResolve(ConflictStrategy.KEEP_LOCAL)}
          disabled={resolving}
          className="flex-1 min-w-[120px] px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-600/50 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {resolving ? t.resolving : t.keepLocal}
        </button>
        <button
          onClick={() => handleResolve(ConflictStrategy.KEEP_SERVER)}
          disabled={resolving}
          className="flex-1 min-w-[120px] px-3 py-2 bg-green-600 hover:bg-green-700 disabled:bg-green-600/50 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {resolving ? t.resolving : t.keepServer}
        </button>
      </div>
    </div>
  )
}

// Format value for display
function formatValue(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

// Main modal component
export function SyncConflictModal({ isOpen, onClose }) {
  const { language } = useLanguage()
  const t = translations[language] || translations.en
  
  const [conflicts, setConflicts] = useState([])
  const [loading, setLoading] = useState(true)
  const [resolvingAll, setResolvingAll] = useState(false)

  const loadConflicts = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getUnresolvedConflicts()
      setConflicts(data)
    } catch (error) {
      console.error('Failed to load conflicts:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isOpen) {
      loadConflicts()
    }
  }, [isOpen, loadConflicts])

  // Listen for conflict events
  useEffect(() => {
    const handleConflictCreated = () => loadConflicts()
    const handleConflictResolved = () => loadConflicts()
    
    window.addEventListener('gearcargo:conflict-created', handleConflictCreated)
    window.addEventListener('gearcargo:conflict-resolved', handleConflictResolved)
    
    return () => {
      window.removeEventListener('gearcargo:conflict-created', handleConflictCreated)
      window.removeEventListener('gearcargo:conflict-resolved', handleConflictResolved)
    }
  }, [loadConflicts])

  const handleResolve = async (conflictId, strategy) => {
    try {
      await resolveConflict(conflictId, strategy)
      await loadConflicts()
      
      // Close modal if no more conflicts
      if (conflicts.length <= 1) {
        onClose?.()
      }
    } catch (error) {
      console.error('Failed to resolve conflict:', error)
    }
  }

  const handleResolveAll = async (strategy) => {
    setResolvingAll(true)
    try {
      for (const conflict of conflicts) {
        await resolveConflict(conflict.id, strategy)
      }
      await loadConflicts()
      onClose?.()
    } catch (error) {
      console.error('Failed to resolve all conflicts:', error)
    } finally {
      setResolvingAll(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[90vh] bg-[var(--color-bg-card)] rounded-2xl shadow-xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-[var(--color-border)] flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
              {t.title}
            </h2>
            <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
              {conflicts.length > 0 
                ? t.subtitle 
                : t.noConflicts}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-[var(--color-bg-tertiary)] transition-colors"
          >
            <svg className="w-5 h-5 text-[var(--color-text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--color-accent)] border-t-transparent" />
            </div>
          ) : conflicts.length === 0 ? (
            <div className="text-center py-12">
              <svg className="w-16 h-16 mx-auto text-green-500 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-[var(--color-text-secondary)]">{t.noConflicts}</p>
            </div>
          ) : (
            <div className="space-y-4">
              {conflicts.map(conflict => (
                <ConflictItem
                  key={conflict.id}
                  conflict={conflict}
                  onResolve={handleResolve}
                  t={t}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer with bulk actions */}
        {conflicts.length > 1 && (
          <div className="px-6 py-4 border-t border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--color-text-muted)]">
                {conflicts.length} {conflicts.length === 1 ? t.conflict : t.conflicts}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => handleResolveAll(ConflictStrategy.KEEP_LOCAL)}
                  disabled={resolvingAll}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-600/50 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  {resolvingAll ? t.resolving : `${t.resolveAll}: ${t.keepLocal}`}
                </button>
                <button
                  onClick={() => handleResolveAll(ConflictStrategy.KEEP_SERVER)}
                  disabled={resolvingAll}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-green-600/50 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  {resolvingAll ? t.resolving : `${t.resolveAll}: ${t.keepServer}`}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default SyncConflictModal
