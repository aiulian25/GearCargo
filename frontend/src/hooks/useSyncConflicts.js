/**
 * GearCargo - useSyncConflicts Hook
 * React hook for managing sync conflicts
 */

import { useState, useEffect, useCallback } from 'react'
import { useLiveQuery } from 'dexie-react-hooks'
import db from '../db/database'
import { 
  getUnresolvedConflicts, 
  getConflictCount,
  resolveConflict,
  resolveAllConflicts,
  ConflictStrategy,
} from '../db/conflictManager'

export function useSyncConflicts() {
  const [loading, setLoading] = useState(true)
  const [resolving, setResolving] = useState(false)

  // Use Dexie live query for reactive updates
  const conflicts = useLiveQuery(
    () => db.syncConflicts.where('resolved').equals(0).toArray(),
    [],
    []
  )

  const conflictCount = useLiveQuery(
    () => db.syncConflicts.where('resolved').equals(0).count(),
    [],
    0
  )

  useEffect(() => {
    if (conflicts !== undefined) {
      setLoading(false)
    }
  }, [conflicts])

  const resolve = useCallback(async (conflictId, strategy, mergedData = null) => {
    setResolving(true)
    try {
      return await resolveConflict(conflictId, strategy, mergedData)
    } finally {
      setResolving(false)
    }
  }, [])

  const resolveAll = useCallback(async (strategy) => {
    setResolving(true)
    try {
      return await resolveAllConflicts(strategy)
    } finally {
      setResolving(false)
    }
  }, [])

  const keepLocal = useCallback(async (conflictId) => {
    return resolve(conflictId, ConflictStrategy.KEEP_LOCAL)
  }, [resolve])

  const keepServer = useCallback(async (conflictId) => {
    return resolve(conflictId, ConflictStrategy.KEEP_SERVER)
  }, [resolve])

  const keepAllLocal = useCallback(async () => {
    return resolveAll(ConflictStrategy.KEEP_LOCAL)
  }, [resolveAll])

  const keepAllServer = useCallback(async () => {
    return resolveAll(ConflictStrategy.KEEP_SERVER)
  }, [resolveAll])

  return {
    conflicts: conflicts || [],
    conflictCount: conflictCount || 0,
    hasConflicts: (conflictCount || 0) > 0,
    loading,
    resolving,
    resolve,
    resolveAll,
    keepLocal,
    keepServer,
    keepAllLocal,
    keepAllServer,
    ConflictStrategy,
  }
}

export default useSyncConflicts
