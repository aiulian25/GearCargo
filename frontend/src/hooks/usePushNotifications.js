/**
 * GearCargo - Push Notifications Hook
 * Manages push notification subscription and permissions
 */

import { useState, useEffect, useCallback } from 'react'
import { pushApi } from '../services/api'

/**
 * Convert a base64 string to Uint8Array for VAPID key
 */
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/')

  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

/**
 * Get device information for subscription
 */
function getDeviceInfo() {
  const userAgent = navigator.userAgent
  let deviceType = 'desktop'
  let deviceName = 'Unknown Device'

  if (/Mobile|Android|iPhone|iPad/.test(userAgent)) {
    deviceType = /iPad/.test(userAgent) ? 'tablet' : 'mobile'
  }

  if (/Chrome/.test(userAgent)) {
    deviceName = 'Chrome'
  } else if (/Firefox/.test(userAgent)) {
    deviceName = 'Firefox'
  } else if (/Safari/.test(userAgent)) {
    deviceName = 'Safari'
  } else if (/Edge/.test(userAgent)) {
    deviceName = 'Edge'
  }

  return {
    device_type: deviceType,
    device_name: `${deviceName} on ${navigator.platform}`,
  }
}

export function usePushNotifications() {
  const [isSupported, setIsSupported] = useState(false)
  const [permission, setPermission] = useState('default')
  const [isSubscribed, setIsSubscribed] = useState(false)
  const [subscription, setSubscription] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Check if push notifications are supported
  useEffect(() => {
    const supported = 
      'Notification' in window &&
      'serviceWorker' in navigator &&
      'PushManager' in window

    setIsSupported(supported)

    if (supported) {
      setPermission(Notification.permission)
    }
  }, [])

  // Check current subscription status
  useEffect(() => {
    async function checkSubscription() {
      if (!isSupported) {
        setLoading(false)
        return
      }

      try {
        const registration = await navigator.serviceWorker.ready
        const existingSub = await registration.pushManager.getSubscription()
        
        setSubscription(existingSub)
        setIsSubscribed(!!existingSub)
      } catch (err) {
        console.error('Failed to check push subscription:', err)
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    checkSubscription()
  }, [isSupported])

  /**
   * Request notification permission
   */
  const requestPermission = useCallback(async () => {
    if (!isSupported) {
      setError('Push notifications are not supported')
      return false
    }

    try {
      const result = await Notification.requestPermission()
      setPermission(result)
      return result === 'granted'
    } catch (err) {
      setError(err.message)
      return false
    }
  }, [isSupported])

  /**
   * Subscribe to push notifications
   */
  const subscribe = useCallback(async () => {
    if (!isSupported) {
      setError('Push notifications are not supported')
      return false
    }

    setLoading(true)
    setError(null)

    try {
      // First, ensure we have permission
      if (Notification.permission !== 'granted') {
        const granted = await requestPermission()
        if (!granted) {
          setError('Notification permission denied')
          return false
        }
      }

      // Get the VAPID public key from server
      const vapidResponse = await pushApi.getVapidKey()
      const vapidPublicKey = vapidResponse.data.public_key

      if (!vapidPublicKey) {
        setError('Push notifications not configured on server')
        return false
      }

      // Get service worker registration
      const registration = await navigator.serviceWorker.ready

      // Subscribe to push
      const pushSubscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
      })

      // Send subscription to server
      const deviceInfo = getDeviceInfo()
      await pushApi.subscribe(pushSubscription.toJSON(), deviceInfo)

      setSubscription(pushSubscription)
      setIsSubscribed(true)
      
      console.log('[Push] Successfully subscribed to push notifications')
      return true
    } catch (err) {
      console.error('[Push] Failed to subscribe:', err)
      setError(err.message)
      return false
    } finally {
      setLoading(false)
    }
  }, [isSupported, requestPermission])

  /**
   * Unsubscribe from push notifications
   */
  const unsubscribe = useCallback(async () => {
    if (!subscription) {
      return true
    }

    setLoading(true)
    setError(null)

    try {
      // Unsubscribe from browser
      await subscription.unsubscribe()

      // Notify server
      await pushApi.unsubscribe(subscription.endpoint)

      setSubscription(null)
      setIsSubscribed(false)
      
      console.log('[Push] Successfully unsubscribed from push notifications')
      return true
    } catch (err) {
      console.error('[Push] Failed to unsubscribe:', err)
      setError(err.message)
      return false
    } finally {
      setLoading(false)
    }
  }, [subscription])

  /**
   * Re-subscribe — force a fresh subscription. Used to recover from a stale or
   * expired endpoint (the toggle still shows "on" but delivery is broken).
   * Tears down the old browser + server subscription, then subscribes anew.
   */
  const resubscribe = useCallback(async () => {
    if (!isSupported) {
      setError('Push notifications are not supported')
      return false
    }

    setLoading(true)
    setError(null)

    try {
      const registration = await navigator.serviceWorker.ready
      const existing = await registration.pushManager.getSubscription()

      if (existing) {
        // Best-effort server cleanup first so we don't orphan the old record.
        try {
          await pushApi.unsubscribe(existing.endpoint)
        } catch (cleanupErr) {
          console.warn('[Push] Old subscription server cleanup failed:', cleanupErr)
        }
        await existing.unsubscribe()
      }

      setSubscription(null)
      setIsSubscribed(false)
    } catch (err) {
      console.error('[Push] Re-subscribe teardown failed:', err)
      // Continue to subscribe() anyway — a fresh subscribe may still succeed.
    } finally {
      setLoading(false)
    }

    return subscribe()
  }, [isSupported, subscribe])

  /**
   * Toggle subscription
   */
  const toggle = useCallback(async () => {
    if (isSubscribed) {
      return unsubscribe()
    } else {
      return subscribe()
    }
  }, [isSubscribed, subscribe, unsubscribe])

  /**
   * Send a test notification
   */
  const sendTestNotification = useCallback(async () => {
    if (!isSubscribed) {
      setError('Not subscribed to push notifications')
      return false
    }

    try {
      await pushApi.test()
      return true
    } catch (err) {
      setError(err.message)
      return false
    }
  }, [isSubscribed])

  /**
   * Show a local notification (for testing)
   */
  const showLocalNotification = useCallback(async (title, options = {}) => {
    if (Notification.permission !== 'granted') {
      return false
    }

    try {
      const registration = await navigator.serviceWorker.ready
      await registration.showNotification(title, {
        icon: '/icons/logo-192.png',
        badge: '/icons/logo-72.png',
        vibrate: [100, 50, 100],
        ...options,
      })
      return true
    } catch (err) {
      console.error('[Push] Failed to show notification:', err)
      return false
    }
  }, [])

  return {
    // State
    isSupported,
    permission,
    isSubscribed,
    subscription,
    loading,
    error,
    
    // Permission states
    isGranted: permission === 'granted',
    isDenied: permission === 'denied',
    isDefault: permission === 'default',
    
    // Actions
    requestPermission,
    subscribe,
    unsubscribe,
    resubscribe,
    toggle,
    sendTestNotification,
    showLocalNotification,
  }
}

export default usePushNotifications
