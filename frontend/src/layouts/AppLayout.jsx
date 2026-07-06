import { useState, useRef, useEffect, Suspense } from 'react'
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { useTranslation } from '../contexts/LanguageContext'
import { SyncIndicator } from '../components/PWA/SyncIndicator'
import UpdatePill from '../components/PWA/UpdatePill'
import { useAppUpdate } from '../contexts/UpdateContext'
import GlobalSearch from '../components/ui/GlobalSearch'
import PageLoader from '../components/ui/PageLoader'

// SVG Icons for navigation and menus
const Icons = {
  // Navigation icons
  dashboard: (active) => (
    <svg className={active ? "w-6 h-6" : "w-5 h-5"} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
    </svg>
  ),
  calendar: (active) => (
    <svg className={active ? "w-6 h-6" : "w-5 h-5"} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5m-9-6h.008v.008H12v-.008zM12 15h.008v.008H12V15zm0 2.25h.008v.008H12v-.008zM9.75 15h.008v.008H9.75V15zm0 2.25h.008v.008H9.75v-.008zM7.5 15h.008v.008H7.5V15zm0 2.25h.008v.008H7.5v-.008zm6.75-4.5h.008v.008h-.008v-.008zm0 2.25h.008v.008h-.008V15zm0 2.25h.008v.008h-.008v-.008zm2.25-4.5h.008v.008H16.5v-.008zm0 2.25h.008v.008H16.5V15z" />
    </svg>
  ),
  car: (active) => (
    <svg className={active ? "w-6 h-6" : "w-5 h-5"} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 18.75a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 01-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 00-3.213-9.193 2.056 2.056 0 00-1.58-.86H14.25M16.5 18.75h-2.25m0-11.177v-.958c0-.568-.422-1.048-.987-1.106a48.554 48.554 0 00-10.026 0 1.106 1.106 0 00-.987 1.106v7.635m12-6.677v6.677m0 4.5v-4.5m0 0h-12" />
    </svg>
  ),
  fuel: (active) => (
    <svg className={active ? "w-6 h-6" : "w-5 h-5"} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
    </svg>
  ),
  fuelPump: (active) => (
    <svg className={active ? "w-6 h-6" : "w-5 h-5"} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 21h10.5M5.25 21V6a2.25 2.25 0 012.25-2.25h3a2.25 2.25 0 012.25 2.25v15m-7.5-9h7.5m-7.5 0v4.5m0-4.5V9m7.5 3v4.5m0-4.5V9m4.5-1.5v9a1.5 1.5 0 001.5 1.5h.75a.75.75 0 00.75-.75v-6a.75.75 0 00-.75-.75h-.75m0 0V6.75a.75.75 0 01.75-.75h.75a2.25 2.25 0 012.25 2.25v1.5" />
    </svg>
  ),
  bell: (active) => (
    <svg className={active ? "w-6 h-6" : "w-5 h-5"} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
    </svg>
  ),
  cog: (active) => (
    <svg className={active ? "w-6 h-6" : "w-5 h-5"} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
  sparkle: (active) => (
    <svg className={active ? "w-6 h-6" : "w-5 h-5"} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
    </svg>
  ),
  // User menu icons
  search: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M21 21l-4.35-4.35m0 0A7.5 7.5 0 104.5 4.5a7.5 7.5 0 0012.15 12.15z" />
    </svg>
  ),
  chevronDown: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  ),
  chevronUp: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
    </svg>
  ),
  settings: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
  help: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />
    </svg>
  ),
  logout: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
    </svg>
  ),
}

const navItems = [
  { path: '/', icon: 'dashboard', labelKey: 'nav.home' },
  { path: '/calendar', icon: 'calendar', labelKey: 'nav.calendar' },
  { path: '/recommendations', icon: 'sparkle', labelKey: 'nav.recommendations' },
  { path: '/reminders', icon: 'bell', labelKey: 'nav.alerts' },
  { path: '/settings', icon: 'cog', labelKey: 'nav.settings' },
]

// User Menu Dropdown
function UserMenu({ user, onLogout }) {
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef(null)
  const { t } = useTranslation()
  
  // Close menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])
  
  const userInitial = user?.name?.charAt(0).toUpperCase() || 'U'
  const userAvatar = user?.avatar_url || user?.avatar
  
  return (
    <div className="relative" ref={menuRef}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-[var(--color-bg-tertiary)] transition-colors"
      >
        <span className="text-xs text-[var(--color-text-secondary)] hidden sm:block max-w-[100px] truncate">
          {user?.name}
        </span>
        {userAvatar ? (
          <img 
            src={userAvatar} 
            alt={user?.name} 
            className="w-8 h-8 rounded-full object-cover ring-2 ring-[var(--color-border)]"
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--color-accent)] to-blue-700 flex items-center justify-center ring-2 ring-[var(--color-border)]">
            <span className="text-sm font-semibold text-white">
              {userInitial}
            </span>
          </div>
        )}
        <span className="text-[var(--color-text-muted)]">
          {isOpen ? Icons.chevronUp : Icons.chevronDown}
        </span>
      </button>
      
      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-56 bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] shadow-xl shadow-black/20 overflow-hidden z-50">
          {/* User Info */}
          <div className="p-4 border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
            <div className="flex items-center gap-3">
              {userAvatar ? (
                <img 
                  src={userAvatar} 
                  alt={user?.name} 
                  className="w-10 h-10 rounded-full object-cover"
                />
              ) : (
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[var(--color-accent)] to-blue-700 flex items-center justify-center">
                  <span className="text-lg font-semibold text-white">
                    {userInitial}
                  </span>
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-[var(--color-text-primary)] truncate">
                  {user?.name}
                </p>
                <p className="text-xs text-[var(--color-text-muted)] truncate">
                  {user?.email}
                </p>
              </div>
            </div>
          </div>
          
          {/* Menu Items */}
          <div className="py-2">
            <NavLink
              to="/settings"
              onClick={() => setIsOpen(false)}
              className="flex items-center gap-3 px-4 py-2.5 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              {Icons.settings}
              {t('userMenu.settings')}
            </NavLink>
            <NavLink
              to="/settings"
              onClick={() => setIsOpen(false)}
              className="flex items-center gap-3 px-4 py-2.5 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              {Icons.help}
              {t('userMenu.helpSupport')}
            </NavLink>
          </div>
          
          {/* Logout */}
          <div className="border-t border-[var(--color-border)] py-2">
            <button
              onClick={() => {
                setIsOpen(false)
                onLogout()
              }}
              className="flex items-center gap-3 px-4 py-2.5 w-full text-sm text-red-400 hover:bg-red-500/10 transition-colors"
            >
              {Icons.logout}
              {t('userMenu.signOut')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function AppLayout() {
  const { user, logout } = useAuth()
  const { available: updateAvailable } = useAppUpdate()
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const [searchOpen, setSearchOpen] = useState(false)

  // Ctrl+K / Cmd+K — open search modal
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }
  
  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-bg-primary)]">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-[var(--color-bg-secondary)] border-b border-[var(--color-border)] safe-top">
        <div className="flex items-center justify-between px-4 h-14">
          {/* Logo */}
          <NavLink to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
            <img 
              src="/icons/logo.png" 
              alt="GearCargo" 
              className="w-8 h-8 rounded-lg object-contain"
            />
            <span className="font-bold text-base text-[var(--color-text-primary)]">
              GearCargo
            </span>
          </NavLink>
          
          {/* Sync Status, Search, and User Menu */}
          <div className="flex items-center gap-2">
            {updateAvailable ? <UpdatePill /> : <SyncIndicator variant="badge" />}
            {/* Search button */}
            <button
              onClick={() => setSearchOpen(true)}
              className="p-2 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-hover,rgba(255,255,255,0.06))] transition-colors"
              aria-label={t('search.title') || 'Search'}
              title={`${t('search.title') || 'Search'} (Ctrl+K)`}
            >
              {Icons.search}
            </button>
            <UserMenu user={user} onLogout={handleLogout} />
          </div>
        </div>
      </header>

      {/* Global Search Modal */}
      <GlobalSearch isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
      
      {/* Main Content */}
      <main className="flex-1 pb-16">
        <div className="w-full max-w-2xl lg:max-w-screen-2xl 2xl:max-w-[1800px] mx-auto">
          {/* Suspense boundary for lazily-loaded route chunks (§2 code splitting).
              Placed inside the layout so the header + bottom nav stay visible
              while the next page's chunk loads — only the content area shows the
              loader. */}
          <Suspense fallback={<PageLoader />}>
            <Outlet />
          </Suspense>
        </div>
      </main>
      
      {/* Bottom Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 bg-[var(--color-bg-secondary)] border-t border-[var(--color-border)] bottom-nav">
        <div className="flex items-center justify-around h-14 max-w-lg mx-auto">
          {navItems.map((item) => {
            const isActive = item.path === '/' 
              ? location.pathname === '/'
              : location.pathname.startsWith(item.path)
            
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={`flex flex-col items-center justify-center w-16 h-full touch-manipulation ${
                  isActive 
                    ? 'text-[var(--color-accent)]' 
                    : 'text-[var(--color-text-muted)]'
                }`}
              >
                {Icons[item.icon](isActive)}
                <span className="text-2xs mt-0.5">{t(item.labelKey)}</span>
              </NavLink>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
