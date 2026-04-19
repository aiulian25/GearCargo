import { useState, useRef, useCallback, useEffect } from 'react'

const THRESHOLD = 70
const MAX_PULL = 120

export default function PullToRefresh() {
  const [pullDistance, setPullDistance] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const startY = useRef(0)
  const isPulling = useRef(false)

  const handleRefresh = useCallback(async () => {
    setRefreshing(true)

    try {
      const registration = await navigator.serviceWorker?.getRegistration()
      if (registration) {
        await registration.update()
        // If a new SW is waiting, let UpdatePrompt handle it
        if (registration.waiting) {
          setRefreshing(false)
          setPullDistance(0)
          return
        }
      }
    } catch (e) {
      // Ignore SW errors
    }

    // No SW update pending — reload for fresh data
    window.location.reload()
  }, [])

  const handleTouchStart = useCallback((e) => {
    if (refreshing) return
    // Only activate when scrolled to the very top
    if (window.scrollY > 0 || document.documentElement.scrollTop > 0) return

    startY.current = e.touches[0].clientY
    isPulling.current = true
  }, [refreshing])

  const handleTouchMove = useCallback((e) => {
    if (!isPulling.current || refreshing) return

    const delta = e.touches[0].clientY - startY.current

    if (delta > 0) {
      // Apply resistance so it feels natural
      const distance = Math.min(delta * 0.5, MAX_PULL)
      setPullDistance(distance)
    } else {
      isPulling.current = false
      setPullDistance(0)
    }
  }, [refreshing])

  const handleTouchEnd = useCallback(() => {
    if (!isPulling.current) return
    isPulling.current = false

    if (pullDistance >= THRESHOLD) {
      handleRefresh()
    } else {
      setPullDistance(0)
    }
  }, [pullDistance, handleRefresh])

  useEffect(() => {
    document.addEventListener('touchstart', handleTouchStart, { passive: true })
    document.addEventListener('touchmove', handleTouchMove, { passive: true })
    document.addEventListener('touchend', handleTouchEnd)

    return () => {
      document.removeEventListener('touchstart', handleTouchStart)
      document.removeEventListener('touchmove', handleTouchMove)
      document.removeEventListener('touchend', handleTouchEnd)
    }
  }, [handleTouchStart, handleTouchMove, handleTouchEnd])

  if (pullDistance <= 0 && !refreshing) return null

  const progress = Math.min(pullDistance / THRESHOLD, 1)
  const rotation = refreshing ? undefined : progress * 360

  return (
    <div
      className="fixed top-0 left-0 right-0 z-[100] flex justify-center pointer-events-none"
      style={{ transform: `translateY(${Math.max(pullDistance - 40, 0)}px)`, transition: refreshing ? 'none' : pullDistance === 0 ? 'transform 0.2s ease-out' : 'none' }}
    >
      <div
        className={`w-10 h-10 rounded-full bg-[var(--color-bg-card)] shadow-lg flex items-center justify-center border border-[var(--color-border)] ${refreshing ? 'animate-spin' : ''}`}
        style={{ opacity: refreshing ? 1 : progress }}
      >
        <svg
          width="20" height="20" viewBox="0 0 24 24" fill="none"
          stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          style={rotation !== undefined ? { transform: `rotate(${rotation}deg)` } : undefined}
        >
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
      </div>
    </div>
  )
}
