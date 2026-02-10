import { Outlet } from 'react-router-dom'

export default function AuthLayout({ children }) {
  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      {/* Left Side - Logo/Branding (hidden on mobile, visible on desktop) */}
      <div 
        className="hidden lg:flex lg:w-1/2 items-center justify-center"
        style={{
          backgroundImage: 'url(/icons/logo.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat'
        }}
      >
      </div>
      
      {/* Right Side - Form */}
      <div className="flex-1 flex flex-col bg-white min-h-screen lg:min-h-0">
        {/* Mobile Logo (visible only on mobile) */}
        <div 
          className="lg:hidden w-full h-64"
          style={{
            backgroundImage: 'url(/icons/logo.png)',
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            backgroundRepeat: 'no-repeat'
          }}
        >
        </div>
        
        {/* Content */}
        <div className="flex-1 flex items-center justify-center px-6 py-8 lg:px-12">
          <div className="w-full max-w-md">
            {children || <Outlet />}
          </div>
        </div>
      </div>
    </div>
  )
}
