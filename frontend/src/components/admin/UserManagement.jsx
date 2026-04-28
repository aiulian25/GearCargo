import { useState, useEffect } from 'react'
import { adminApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { formatDateShort } from '../../utils/dateFormat'

// Icons
const Icons = {
  search: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
    </svg>
  ),
  user: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
    </svg>
  ),
  users: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
      <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </svg>
  ),
  shield: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
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
  trash: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </svg>
  ),
  edit: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
  ),
  car: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 16H9m10 0h3v-3.15a1 1 0 0 0-.84-.99L16 11l-2.7-3.6a1 1 0 0 0-.8-.4H5.24a2 2 0 0 0-1.8 1.1l-.8 1.63A6 6 0 0 0 2 12.42V16h2"/>
      <circle cx="6.5" cy="16.5" r="2.5"/><circle cx="16.5" cy="16.5" r="2.5"/>
    </svg>
  ),
  list: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
      <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
    </svg>
  ),
  chevronLeft: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6"/>
    </svg>
  ),
  chevronRight: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  ),
  close: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  plus: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  ),
}

export default function UserManagement() {
  const { t } = useTranslation()
  const [users, setUsers] = useState([])
  const [stats, setStats] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [selectedUser, setSelectedUser] = useState(null)
  const [showEditModal, setShowEditModal] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editForm, setEditForm] = useState({ is_admin: false, is_active: true, vehicle_limit: '' })
  const [addForm, setAddForm] = useState({ email: '', username: '', display_name: '', password: '', is_admin: false, is_active: true, vehicle_limit: 10 })
  const [isSaving, setIsSaving] = useState(false)
  
  useEffect(() => {
    fetchStats()
  }, [])
  
  useEffect(() => {
    fetchUsers()
  }, [currentPage, search])
  
  const fetchStats = async () => {
    try {
      const response = await adminApi.getStats()
      setStats(response.data)
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    }
  }
  
  const fetchUsers = async () => {
    setIsLoading(true)
    try {
      const response = await adminApi.getUsers(currentPage, 10, search)
      setUsers(response.data.users)
      setTotalPages(response.data.pages)
    } catch (error) {
      console.error('Failed to fetch users:', error)
    } finally {
      setIsLoading(false)
    }
  }
  
  const handleSearch = (e) => {
    e.preventDefault()
    setCurrentPage(1)
    fetchUsers()
  }
  
  const handleEditUser = (user) => {
    setSelectedUser(user)
    setEditForm({
      is_admin: user.is_admin === true,
      is_active: user.is_active !== false,
      vehicle_limit: user.vehicle_limit || ''
    })
    setShowEditModal(true)
  }
  
  const handleSaveUser = async () => {
    if (!selectedUser) return
    
    setIsSaving(true)
    try {
      await adminApi.updateUser(selectedUser.id, editForm)
      setShowEditModal(false)
      fetchUsers()
      fetchStats()
    } catch (error) {
      console.error('Failed to update user:', error)
      alert(error.response?.data?.error || 'Failed to update user')
    } finally {
      setIsSaving(false)
    }
  }
  
  const handleDeleteUser = async (user) => {
    if (!window.confirm(`${t('admin.deleteUserConfirm') || 'Are you sure you want to delete'} ${user.name || user.email}? ${t('admin.deleteUserWarning') || 'This will delete all their data.'}`)) {
      return
    }
    
    try {
      await adminApi.deleteUser(user.id)
      fetchUsers()
      fetchStats()
    } catch (error) {
      console.error('Failed to delete user:', error)
      alert(error.response?.data?.error || 'Failed to delete user')
    }
  }
  
  const handleCreateUser = async () => {
    if (!addForm.email || !addForm.password) {
      alert(t('admin.emailPasswordRequired') || 'Email and password are required')
      return
    }
    
    setIsSaving(true)
    try {
      await adminApi.createUser(addForm)
      setShowAddModal(false)
      setAddForm({ email: '', username: '', display_name: '', password: '', is_admin: false, is_active: true, vehicle_limit: 10 })
      fetchUsers()
      fetchStats()
    } catch (error) {
      console.error('Failed to create user:', error)
      alert(error.response?.data?.error || 'Failed to create user')
    } finally {
      setIsSaving(false)
    }
  }
  
  const formatDate = (dateStr) => formatDateShort(dateStr)
  
  return (
    <div className="space-y-4">
      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-[var(--color-bg-tertiary)] rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-[var(--color-accent)]">
              {stats.users?.total || 0}
            </div>
            <div className="text-xs text-[var(--color-text-secondary)]">
              {t('admin.totalUsers') || 'Total Users'}
            </div>
          </div>
          <div className="bg-[var(--color-bg-tertiary)] rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-green-500">
              {stats.users?.active || 0}
            </div>
            <div className="text-xs text-[var(--color-text-secondary)]">
              {t('admin.activeUsers') || 'Active'}
            </div>
          </div>
          <div className="bg-[var(--color-bg-tertiary)] rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-amber-500">
              {stats.users?.new_this_week || 0}
            </div>
            <div className="text-xs text-[var(--color-text-secondary)]">
              {t('admin.newThisWeek') || 'New This Week'}
            </div>
          </div>
        </div>
      )}
      
      {/* Search and Add User */}
      <div className="flex gap-2">
        <form onSubmit={handleSearch} className="relative flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]">
            {Icons.search}
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('admin.searchUsers') || 'Search users...'}
            className="w-full pl-10 pr-4 py-3 rounded-xl bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
          />
        </form>
        <button
          onClick={() => setShowAddModal(true)}
          className="px-4 py-3 rounded-xl bg-[var(--color-accent)] text-white font-medium flex items-center gap-2 hover:opacity-90 transition-opacity"
        >
          {Icons.plus}
          <span className="hidden sm:inline">{t('admin.addUser') || 'Add User'}</span>
        </button>
      </div>
      
      {/* Users List */}
      <div className="space-y-2">
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="skeleton h-20 rounded-xl" />
            ))}
          </div>
        ) : users.length === 0 ? (
          <div className="text-center py-8 text-[var(--color-text-secondary)]">
            {t('admin.noUsersFound') || 'No users found'}
          </div>
        ) : (
          users.map(user => (
            <div 
              key={user.id}
              className="bg-[var(--color-bg-secondary)] rounded-xl p-4 border border-[var(--color-border)]"
            >
              <div className="flex items-start gap-3">
                {/* Avatar */}
                <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                  user.is_admin ? 'bg-amber-500/20 text-amber-500' : 'bg-[var(--color-accent)]/20 text-[var(--color-accent)]'
                }`}>
                  <span className="text-sm font-bold">
                    {user.display_name?.charAt(0).toUpperCase() || user.username?.charAt(0).toUpperCase() || user.email?.charAt(0).toUpperCase() || 'U'}
                  </span>
                </div>
                
                {/* User Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium truncate">{user.display_name || user.username || 'Unnamed User'}</h3>
                    {user.is_admin && (
                      <span className="px-1.5 py-0.5 rounded text-2xs font-medium bg-amber-500/20 text-amber-500 flex items-center gap-1">
                        {Icons.shield}
                        Admin
                      </span>
                    )}
                    {!user.is_active && (
                      <span className="px-1.5 py-0.5 rounded text-2xs font-medium bg-red-500/20 text-red-500">
                        {t('admin.inactive') || 'Inactive'}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[var(--color-text-secondary)] truncate">{user.email}</p>
                  <div className="flex items-center gap-4 mt-2 text-xs text-[var(--color-text-muted)]">
                    <span className="flex items-center gap-1">
                      {Icons.car}
                      {user.vehicle_count || 0}{user.vehicle_limit ? `/${user.vehicle_limit}` : ''} {t('admin.vehicles') || 'vehicles'}
                    </span>
                    <span>
                      {t('admin.joined') || 'Joined'} {formatDate(user.created_at)}
                    </span>
                  </div>
                </div>
                
                {/* Actions */}
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleEditUser(user)}
                    className="p-2 rounded-lg hover:bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] transition-colors"
                    title={t('common.edit') || 'Edit'}
                  >
                    {Icons.edit}
                  </button>
                  <button
                    onClick={() => handleDeleteUser(user)}
                    className="p-2 rounded-lg hover:bg-red-500/10 text-[var(--color-text-secondary)] hover:text-red-500 transition-colors"
                    title={t('common.delete') || 'Delete'}
                  >
                    {Icons.trash}
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
      
      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="p-2 rounded-lg hover:bg-[var(--color-bg-tertiary)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {Icons.chevronLeft}
          </button>
          <span className="text-sm text-[var(--color-text-secondary)]">
            {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="p-2 rounded-lg hover:bg-[var(--color-bg-tertiary)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {Icons.chevronRight}
          </button>
        </div>
      )}
      
      {/* Edit User Modal */}
      {showEditModal && selectedUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6 w-full max-w-sm border border-[var(--color-border)]">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">{t('admin.editUser') || 'Edit User'}</h3>
              <button
                onClick={() => setShowEditModal(false)}
                className="p-2 rounded-lg hover:bg-[var(--color-bg-tertiary)]"
              >
                {Icons.close}
              </button>
            </div>
            
            <div className="mb-4">
              <p className="text-sm text-[var(--color-text-secondary)] mb-1">{selectedUser.email}</p>
              <p className="font-medium">{selectedUser.display_name || selectedUser.username || 'Unnamed User'}</p>
            </div>
            
            {/* Role */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">
                {t('admin.role') || 'Role'}
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setEditForm(f => ({ ...f, is_admin: false }))}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                    !editForm.is_admin
                      ? 'bg-[var(--color-accent)] text-white'
                      : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
                  }`}
                >
                  {t('admin.roleUser') || 'User'}
                </button>
                <button
                  type="button"
                  onClick={() => setEditForm(f => ({ ...f, is_admin: true }))}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                    editForm.is_admin
                      ? 'bg-amber-500 text-white'
                      : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
                  }`}
                >
                  {t('admin.roleAdmin') || 'Admin'}
                </button>
              </div>
            </div>
            
            {/* Status */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">
                {t('admin.status') || 'Status'}
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setEditForm(f => ({ ...f, is_active: true }))}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    editForm.is_active
                      ? 'bg-green-500 text-white'
                      : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
                  }`}
                >
                  {Icons.check}
                  {t('admin.active') || 'Active'}
                </button>
                <button
                  type="button"
                  onClick={() => setEditForm(f => ({ ...f, is_active: false }))}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    !editForm.is_active
                      ? 'bg-red-500 text-white'
                      : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
                  }`}
                >
                  {Icons.x}
                  {t('admin.inactive') || 'Inactive'}
                </button>
              </div>
            </div>
            
            {/* Vehicle Limit */}
            <div className="mb-6">
              <label className="block text-sm font-medium mb-2">
                {t('admin.vehicleLimit') || 'Vehicle Limit'}
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="number"
                  min="0"
                  value={editForm.vehicle_limit}
                  onChange={(e) => setEditForm(f => ({ ...f, vehicle_limit: e.target.value }))}
                  placeholder={t('admin.unlimited') || 'Unlimited'}
                  className="flex-1 px-4 py-2 rounded-xl bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
                />
                <span className="text-xs text-[var(--color-text-muted)]">
                  {t('admin.vehicleLimitHelp') || '0 = Unlimited'}
                </span>
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mt-1">
                {t('admin.currentVehicles') || 'Current'}: {selectedUser?.vehicle_count || 0}
              </p>
            </div>
            
            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={() => setShowEditModal(false)}
                className="flex-1 py-3 rounded-xl bg-[var(--color-bg-tertiary)] font-medium"
              >
                {t('common.cancel') || 'Cancel'}
              </button>
              <button
                onClick={handleSaveUser}
                disabled={isSaving}
                className="flex-1 py-3 rounded-xl bg-[var(--color-accent)] text-white font-medium disabled:opacity-50"
              >
                {isSaving ? (t('common.saving') || 'Saving...') : (t('common.save') || 'Save')}
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Add User Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6 w-full max-w-sm border border-[var(--color-border)] max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">{t('admin.addUser') || 'Add User'}</h3>
              <button
                onClick={() => {
                  setShowAddModal(false)
                  setAddForm({ email: '', username: '', display_name: '', password: '', is_admin: false, is_active: true, vehicle_limit: 10 })
                }}
                className="p-2 rounded-lg hover:bg-[var(--color-bg-tertiary)]"
              >
                {Icons.close}
              </button>
            </div>
            
            {/* Email */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">
                {t('common.email') || 'Email'} <span className="text-red-500">*</span>
              </label>
              <input
                type="email"
                value={addForm.email}
                onChange={(e) => setAddForm(f => ({ ...f, email: e.target.value }))}
                placeholder="user@example.com"
                autoComplete="off"
                className="w-full px-4 py-3 rounded-xl bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
                required
              />
            </div>
            
            {/* Username */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">
                {t('common.username') || 'Username'}
              </label>
              <input
                type="text"
                value={addForm.username}
                onChange={(e) => setAddForm(f => ({ ...f, username: e.target.value }))}
                placeholder={t('admin.optionalUsername') || 'Optional username'}
                autoComplete="off"
                className="w-full px-4 py-3 rounded-xl bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
              />
            </div>
            
            {/* Display Name */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">
                {t('common.displayName') || 'Display Name'}
              </label>
              <input
                type="text"
                value={addForm.display_name}
                onChange={(e) => setAddForm(f => ({ ...f, display_name: e.target.value }))}
                placeholder={t('admin.optionalDisplayName') || 'Optional display name'}
                autoComplete="off"
                className="w-full px-4 py-3 rounded-xl bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
              />
            </div>
            
            {/* Password */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">
                {t('common.password') || 'Password'} <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                value={addForm.password}
                onChange={(e) => setAddForm(f => ({ ...f, password: e.target.value }))}
                placeholder="••••••••"
                autoComplete="new-password"
                className="w-full px-4 py-3 rounded-xl bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
                required
              />
            </div>
            
            {/* Role */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">
                {t('admin.role') || 'Role'}
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setAddForm(f => ({ ...f, is_admin: false }))}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                    !addForm.is_admin
                      ? 'bg-[var(--color-accent)] text-white'
                      : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
                  }`}
                >
                  {t('admin.roleUser') || 'User'}
                </button>
                <button
                  type="button"
                  onClick={() => setAddForm(f => ({ ...f, is_admin: true }))}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                    addForm.is_admin
                      ? 'bg-amber-500 text-white'
                      : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
                  }`}
                >
                  {t('admin.roleAdmin') || 'Admin'}
                </button>
              </div>
            </div>
            
            {/* Status */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">
                {t('admin.status') || 'Status'}
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setAddForm(f => ({ ...f, is_active: true }))}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    addForm.is_active
                      ? 'bg-green-500 text-white'
                      : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
                  }`}
                >
                  {Icons.check}
                  {t('admin.active') || 'Active'}
                </button>
                <button
                  type="button"
                  onClick={() => setAddForm(f => ({ ...f, is_active: false }))}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    !addForm.is_active
                      ? 'bg-red-500 text-white'
                      : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
                  }`}
                >
                  {Icons.x}
                  {t('admin.inactive') || 'Inactive'}
                </button>
              </div>
            </div>
            
            {/* Vehicle Limit */}
            <div className="mb-6">
              <label className="block text-sm font-medium mb-2">
                {t('admin.vehicleLimit') || 'Vehicle Limit'}
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="number"
                  min="0"
                  value={addForm.vehicle_limit}
                  onChange={(e) => setAddForm(f => ({ ...f, vehicle_limit: e.target.value }))}
                  placeholder={t('admin.unlimited') || 'Unlimited'}
                  className="flex-1 px-4 py-2 rounded-xl bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
                />
                <span className="text-xs text-[var(--color-text-muted)]">
                  {t('admin.vehicleLimitHelp') || '0 = Unlimited'}
                </span>
              </div>
            </div>
            
            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowAddModal(false)
                  setAddForm({ email: '', username: '', display_name: '', password: '', is_admin: false, is_active: true, vehicle_limit: 10 })
                }}
                className="flex-1 py-3 rounded-xl bg-[var(--color-bg-tertiary)] font-medium"
              >
                {t('common.cancel') || 'Cancel'}
              </button>
              <button
                onClick={handleCreateUser}
                disabled={isSaving || !addForm.email || !addForm.password}
                className="flex-1 py-3 rounded-xl bg-[var(--color-accent)] text-white font-medium disabled:opacity-50"
              >
                {isSaving ? (t('common.creating') || 'Creating...') : (t('common.create') || 'Create')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
