import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.js',
      registerType: 'prompt',
      includeAssets: ['favicon.ico', 'logo.png', 'icons/*.png'],
      manifest: {
        name: 'GearCargo - Vehicle Management',
        short_name: 'GearCargo',
        description: 'Track fuel, services, repairs, and more for your vehicles',
        theme_color: '#1e293b',
        background_color: '#0f172a',
        display: 'standalone',
        orientation: 'portrait-primary',
        scope: '/',
        start_url: '/',
        icons: [
          {
            src: '/icons/logo-72.png',
            sizes: '72x72',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/icons/logo-96.png',
            sizes: '96x96',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/icons/logo-128.png',
            sizes: '128x128',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/icons/logo-144.png',
            sizes: '144x144',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/icons/logo-152.png',
            sizes: '152x152',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/icons/logo-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any maskable'
          },
          {
            src: '/icons/logo-384.png',
            sizes: '384x384',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/icons/logo-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable'
          }
        ],
        categories: ['utilities', 'productivity'],
        shortcuts: [
          {
            name: 'Add Fuel',
            short_name: 'Fuel',
            description: 'Add a new fuel entry',
            url: '/fuel/add',
            icons: [{ src: '/icons/fuel-96.png', sizes: '96x96' }]
          },
          {
            name: 'Add Expense',
            short_name: 'Expense',
            description: 'Log a service or expense',
            url: '/services/add'
          },
          {
            name: 'My Vehicles',
            short_name: 'Vehicles',
            description: 'View your vehicles',
            url: '/vehicles',
            icons: [{ src: '/icons/vehicle-96.png', sizes: '96x96' }]
          }
        ],
        // Web Share Target — lets the OS share sheet send a receipt image
        // straight into the OCR upload flow. The SW intercepts this POST,
        // stashes the file and redirects into the SPA (see src/sw.js).
        share_target: {
          action: '/share-target',
          method: 'POST',
          enctype: 'multipart/form-data',
          params: {
            title: 'title',
            text: 'text',
            url: 'url',
            files: [
              {
                name: 'receipt',
                accept: ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/*']
              }
            ]
          }
        }
      },
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // UX-01: PWA manifest screenshots are fetched on-demand by the browser's
        // install UI, never by the app at runtime — keep them OUT of the SW
        // precache so they don't bloat the offline bundle.
        globIgnores: ['**/screenshots/**'],
      }
    })
  ],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts']
        }
      }
    }
  }
})
