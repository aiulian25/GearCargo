import { useState, useEffect, useId, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { vehicleApi, externalApi, insuranceApi } from '../services/api'
import { useCurrency, useTranslation } from '../contexts/LanguageContext'
import { useAuth } from '../contexts/AuthContext'
import WeatherAlerts, { WeatherAlertsModal } from '../components/weather/WeatherAlerts'

// Weather Icon Component - Clean SVG icons with unique IDs
function WeatherIcon({ condition, size = 80 }) {
  const id = useId().replace(/:/g, '')
  
  const icons = {
    // Sunny / Clear
    clear_day: (
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <radialGradient id={`sun-${id}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#FFF59D" />
            <stop offset="60%" stopColor="#FFD54F" />
            <stop offset="100%" stopColor="#FF8F00" />
          </radialGradient>
        </defs>
        {/* Sun rays */}
        {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, i) => (
          <line
            key={i}
            x1="50" y1="50"
            x2={50 + 40 * Math.cos(angle * Math.PI / 180)}
            y2={50 + 40 * Math.sin(angle * Math.PI / 180)}
            stroke="#FFD54F"
            strokeWidth="4"
            strokeLinecap="round"
          />
        ))}
        <circle cx="50" cy="50" r="22" fill={`url(#sun-${id})`} />
      </svg>
    ),

    // Partly Cloudy
    partly_cloudy_day: (
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <radialGradient id={`sun2-${id}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#FFF59D" />
            <stop offset="100%" stopColor="#FFB300" />
          </radialGradient>
          <linearGradient id={`cloud1-${id}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#FFFFFF" />
            <stop offset="100%" stopColor="#E0E0E0" />
          </linearGradient>
        </defs>
        {/* Sun behind */}
        <circle cx="70" cy="28" r="16" fill={`url(#sun2-${id})`} />
        {[0, 60, 120, 180, 240, 300].map((angle, i) => (
          <line
            key={i}
            x1="70" y1="28"
            x2={70 + 24 * Math.cos(angle * Math.PI / 180)}
            y2={28 + 24 * Math.sin(angle * Math.PI / 180)}
            stroke="#FFD54F"
            strokeWidth="2"
            strokeLinecap="round"
          />
        ))}
        {/* Cloud */}
        <ellipse cx="35" cy="62" rx="22" ry="16" fill={`url(#cloud1-${id})`} />
        <ellipse cx="52" cy="56" rx="20" ry="18" fill={`url(#cloud1-${id})`} />
        <ellipse cx="68" cy="62" rx="16" ry="14" fill={`url(#cloud1-${id})`} />
        <ellipse cx="50" cy="70" rx="28" ry="12" fill={`url(#cloud1-${id})`} />
      </svg>
    ),

    // Cloudy
    cloud: (
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id={`cloud2-${id}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#ECEFF1" />
            <stop offset="100%" stopColor="#B0BEC5" />
          </linearGradient>
        </defs>
        {/* Back cloud */}
        <g opacity="0.5" transform="translate(-5, -12)">
          <ellipse cx="45" cy="48" rx="18" ry="13" fill="#CFD8DC" />
          <ellipse cx="60" cy="44" rx="16" ry="14" fill="#CFD8DC" />
          <ellipse cx="72" cy="48" rx="14" ry="11" fill="#CFD8DC" />
        </g>
        {/* Front cloud */}
        <ellipse cx="30" cy="58" rx="20" ry="14" fill={`url(#cloud2-${id})`} />
        <ellipse cx="48" cy="52" rx="22" ry="18" fill={`url(#cloud2-${id})`} />
        <ellipse cx="66" cy="58" rx="18" ry="14" fill={`url(#cloud2-${id})`} />
        <ellipse cx="48" cy="66" rx="30" ry="13" fill={`url(#cloud2-${id})`} />
      </svg>
    ),

    // Rainy
    rainy: (
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id={`rcloud-${id}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#90A4AE" />
            <stop offset="100%" stopColor="#546E7A" />
          </linearGradient>
        </defs>
        {/* Rain cloud */}
        <ellipse cx="30" cy="38" rx="18" ry="13" fill={`url(#rcloud-${id})`} />
        <ellipse cx="48" cy="32" rx="20" ry="16" fill={`url(#rcloud-${id})`} />
        <ellipse cx="66" cy="38" rx="16" ry="12" fill={`url(#rcloud-${id})`} />
        <ellipse cx="48" cy="46" rx="28" ry="11" fill={`url(#rcloud-${id})`} />
        {/* Rain drops */}
        {[[28, 60], [40, 66], [52, 62], [64, 68], [36, 76], [56, 80]].map(([x, y], i) => (
          <ellipse key={i} cx={x} cy={y} rx="2" ry="5" fill="#4FC3F7" opacity="0.8" />
        ))}
      </svg>
    ),

    // Thunderstorm
    thunderstorm: (
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id={`scloud-${id}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#616161" />
            <stop offset="100%" stopColor="#37474F" />
          </linearGradient>
        </defs>
        {/* Storm cloud */}
        <ellipse cx="30" cy="32" rx="18" ry="13" fill={`url(#scloud-${id})`} />
        <ellipse cx="48" cy="26" rx="20" ry="16" fill={`url(#scloud-${id})`} />
        <ellipse cx="66" cy="32" rx="16" ry="12" fill={`url(#scloud-${id})`} />
        <ellipse cx="48" cy="40" rx="28" ry="11" fill={`url(#scloud-${id})`} />
        {/* Lightning bolt */}
        <polygon points="54,48 44,62 51,62 40,80 58,58 50,58 60,48" fill="#FFD600" />
        {/* Rain drops */}
        {[[28, 56], [68, 60], [32, 72]].map(([x, y], i) => (
          <ellipse key={i} cx={x} cy={y} rx="2" ry="4" fill="#4FC3F7" opacity="0.6" />
        ))}
      </svg>
    ),

    // Snow
    weather_snowy: (
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id={`sncloud-${id}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#ECEFF1" />
            <stop offset="100%" stopColor="#B0BEC5" />
          </linearGradient>
        </defs>
        {/* Snow cloud */}
        <ellipse cx="30" cy="36" rx="18" ry="13" fill={`url(#sncloud-${id})`} />
        <ellipse cx="48" cy="30" rx="20" ry="16" fill={`url(#sncloud-${id})`} />
        <ellipse cx="66" cy="36" rx="16" ry="12" fill={`url(#sncloud-${id})`} />
        <ellipse cx="48" cy="44" rx="28" ry="11" fill={`url(#sncloud-${id})`} />
        {/* Snowflakes */}
        {[[28, 58], [42, 66], [56, 60], [70, 68], [35, 76], [58, 80], [48, 86]].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="3" fill="white" />
        ))}
      </svg>
    ),

    // Foggy
    foggy: (
      <svg width={size} height={size} viewBox="0 0 100 100">
        {/* Fog lines */}
        <rect x="15" y="32" width="70" height="8" rx="4" fill="#B0BEC5" opacity="0.8" />
        <rect x="20" y="48" width="60" height="8" rx="4" fill="#CFD8DC" opacity="0.7" />
        <rect x="25" y="64" width="50" height="8" rx="4" fill="#E0E0E0" opacity="0.6" />
      </svg>
    ),

    // Drizzle
    drizzle: (
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id={`dcloud-${id}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#B0BEC5" />
            <stop offset="100%" stopColor="#78909C" />
          </linearGradient>
        </defs>
        {/* Light cloud */}
        <ellipse cx="30" cy="38" rx="16" ry="12" fill={`url(#dcloud-${id})`} />
        <ellipse cx="46" cy="33" rx="18" ry="14" fill={`url(#dcloud-${id})`} />
        <ellipse cx="62" cy="38" rx="14" ry="11" fill={`url(#dcloud-${id})`} />
        <ellipse cx="46" cy="45" rx="24" ry="10" fill={`url(#dcloud-${id})`} />
        {/* Light rain */}
        {[[32, 58], [46, 64], [60, 60], [39, 74], [53, 78]].map(([x, y], i) => (
          <line key={i} x1={x} y1={y} x2={x-2} y2={y+8} stroke="#81D4FA" strokeWidth="2" strokeLinecap="round" />
        ))}
      </svg>
    ),
  }
  
  return icons[condition] || icons.cloud
}

// Weather Widget Component - App-like design
function WeatherWidget({ weather, airQuality, weatherTab, setWeatherTab, weatherView, setWeatherView, t, language }) {
  const now = new Date()
  
  // Get day name in current language
  const dayNames = {
    en: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
    ro: ['Duminică', 'Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă'],
    es: ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'],
  }
  
  const shortDayNames = {
    en: ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'],
    ro: ['DUM', 'LUN', 'MAR', 'MIE', 'JOI', 'VIN', 'SÂM'],
    es: ['DOM', 'LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB'],
  }
  
  // Wind directions
  const windDirections = {
    en: { N: 'North', S: 'South', E: 'East', W: 'West', NE: 'NE', NW: 'NW', SE: 'SE', SW: 'SW' },
    ro: { N: 'Nord', S: 'Sud', E: 'Est', W: 'Vest', NE: 'NE', NW: 'NV', SE: 'SE', SW: 'SV' },
    es: { N: 'Norte', S: 'Sur', E: 'Este', W: 'Oeste', NE: 'NE', NW: 'NO', SE: 'SE', SW: 'SO' },
  }
  
  // Weather conditions
  const weatherConditions = {
    en: {
      'Clear': 'Clear', 'Sunny': 'Sunny', 'Partly Cloudy': 'Partly Cloudy', 'Cloudy': 'Cloudy',
      'Overcast': 'Overcast', 'Rain': 'Rain', 'Light Rain': 'Light Rain', 'Heavy Rain': 'Heavy Rain',
      'Showers': 'Showers', 'Light Showers': 'Light Showers', 'Thunderstorm': 'Thunderstorm',
      'Snow': 'Snow', 'Light Snow': 'Light Snow', 'Heavy Snow': 'Heavy Snow', 'Fog': 'Fog',
      'Mist': 'Mist', 'Drizzle': 'Drizzle', 'Hail': 'Hail', 'Sleet': 'Sleet', 'Windy': 'Windy',
    },
    ro: {
      'Clear': 'Senin', 'Sunny': 'Însorit', 'Partly Cloudy': 'Parțial Înnorat', 'Cloudy': 'Înnorat',
      'Overcast': 'Acoperit', 'Rain': 'Ploaie', 'Light Rain': 'Ploaie Ușoară', 'Heavy Rain': 'Ploaie Torențială',
      'Showers': 'Averse', 'Light Showers': 'Averse Ușoare', 'Thunderstorm': 'Furtună',
      'Snow': 'Ninsoare', 'Light Snow': 'Ninsoare Ușoară', 'Heavy Snow': 'Ninsoare Abundentă', 'Fog': 'Ceață',
      'Mist': 'Brumă', 'Drizzle': 'Burniță', 'Hail': 'Grindină', 'Sleet': 'Lapoviță', 'Windy': 'Vânt',
    },
    es: {
      'Clear': 'Despejado', 'Sunny': 'Soleado', 'Partly Cloudy': 'Parcialmente Nublado', 'Cloudy': 'Nublado',
      'Overcast': 'Cubierto', 'Rain': 'Lluvia', 'Light Rain': 'Lluvia Ligera', 'Heavy Rain': 'Lluvia Fuerte',
      'Showers': 'Chubascos', 'Light Showers': 'Chubascos Ligeros', 'Thunderstorm': 'Tormenta',
      'Snow': 'Nieve', 'Light Snow': 'Nieve Ligera', 'Heavy Snow': 'Nieve Fuerte', 'Fog': 'Niebla',
      'Mist': 'Neblina', 'Drizzle': 'Llovizna', 'Hail': 'Granizo', 'Sleet': 'Aguanieve', 'Windy': 'Ventoso',
    },
  }
  
  const dayName = dayNames[language]?.[now.getDay()] || dayNames.en[now.getDay()]
  
  // Function to get translated short day name from API day
  const getTranslatedDay = (apiDay) => {
    if (!apiDay) return '--'
    const dayMap = {
      'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
      'Sun': 0, 'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4, 'Fri': 5, 'Sat': 6,
    }
    const dayIndex = dayMap[apiDay.toUpperCase().slice(0, 3)]
    if (dayIndex !== undefined) {
      return shortDayNames[language]?.[dayIndex] || apiDay
    }
    return apiDay
  }
  
  // Translate wind direction
  const getWindDirection = () => {
    const dir = weather?.current?.wind_direction || 'E'
    return windDirections[language]?.[dir] || windDirections.en[dir] || dir
  }
  
  // Translate weather condition
  const getWeatherCondition = () => {
    const condition = weather?.current?.condition || 'Partly Cloudy'
    return weatherConditions[language]?.[condition] || weatherConditions.en[condition] || condition
  }
  
  // Translate "Feels like" text
  const getFeelsLikeText = () => {
    const feelsLikeTexts = {
      en: 'Feels like',
      ro: 'Se simte ca',
      es: 'Sensación de',
    }
    return feelsLikeTexts[language] || feelsLikeTexts.en
  }
    // Get current condition for background
  const currentCondition = weather?.current?.icon || 'partly_cloudy_day'
  
  return (
    <div className="relative overflow-hidden rounded-2xl h-full min-h-[380px]" style={{
      background: 'linear-gradient(180deg, #1a4a7a 0%, #2d6aa0 30%, #4a90c2 60%, #6ab0e0 100%)'
    }}>
      {/* Ambient glow effect */}
      <div className="absolute top-10 right-10 w-40 h-40 bg-yellow-300/20 rounded-full blur-3xl" />
      <div className="absolute bottom-20 left-10 w-32 h-32 bg-blue-400/20 rounded-full blur-2xl" />
      
      {/* Content */}
      <div className="relative z-10 p-5 h-full flex flex-col">
        {/* Top Section - City & Temperature */}
        <div className="flex justify-between items-start mb-2">
          <div>
            <h2 className="text-2xl font-bold text-white drop-shadow-lg">
              {weather?.location?.split(',')[0] || 'Loading...'}
            </h2>
            <p className="text-white/90 text-lg font-light mt-1">{dayName}</p>
          </div>
          <div className="text-right">
            <span className="text-5xl sm:text-6xl font-extralight text-white drop-shadow-lg">
              {weather?.current?.temperature !== undefined ? Math.round(weather.current.temperature) : '--'}
              <span className="text-3xl align-top ml-1">°C</span>
            </span>
            {weather?.current?.feels_like !== undefined && (
              <p className="text-white/70 text-sm mt-1">
                {getFeelsLikeText()} {Math.round(weather.current.feels_like)}°C
              </p>
            )}
          </div>
        </div>
        
        {/* Weather Stats */}
        <div className="flex items-center gap-4 text-white/80 text-sm mb-4">
          <div className="flex items-center gap-1.5">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
            </svg>
            <span>{weather?.current?.humidity ?? '--'}%</span>
          </div>
          <div className="flex items-center gap-1.5">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M14.5 17c0 1.65-1.35 3-3 3s-3-1.35-3-3c0-1.93 2.5-6 3-7 .5 1 3 5.07 3 7zm-3-14c-3.5 0-8 1.5-8 6.5 0 3.5 2.5 6.5 6 6.5h1c-.3-.6-.5-1.3-.5-2 0-2.5 3-7 3-7s3 4.5 3 7c0 .7-.2 1.4-.5 2h1c3.5 0 6-3 6-6.5C22.5 4.5 18 3 14.5 3h-3z"/>
            </svg>
            <span>{getWindDirection()}, {weather?.current?.wind_speed?.toFixed(0) ?? '--'} km/h</span>
          </div>
          <div className="flex items-center gap-1.5">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
            </svg>
            <span>{getWeatherCondition()}</span>
          </div>
        </div>
        
        {/* Center Weather Icon */}
        <div className="flex-1 flex items-center justify-center -mt-4 -mb-2">
          <div className="transform scale-110 sm:scale-125">
            <WeatherIcon condition={currentCondition} size={120} />
          </div>
        </div>
        
        {/* Bottom Forecast Strip - Skip today, show next 6 days */}
        <div className="mt-auto">
          <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
            {(weather?.forecast || Array(7).fill({})).slice(1, 7).map((day, idx) => {
              return (
                <div 
                  key={idx}
                  className="flex-1 min-w-[52px] py-2.5 px-1 rounded-xl text-center transition-all bg-white/10 backdrop-blur-sm hover:bg-white/20"
                >
                  <p className="text-xs font-semibold text-white/90 mb-1.5">
                    {getTranslatedDay(day.day)}
                  </p>
                  <div className="flex justify-center mb-1.5">
                    <WeatherIcon condition={day.icon} size={28} />
                  </div>
                  <p className="text-sm font-bold text-white">
                    {day.temp_max !== undefined ? Math.round(day.temp_max) : '--'}°C
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

// Fuel Prices Widget
function FuelPricesWidget({ fuelPrices, currency, t, onRefresh, isRefreshing }) {
  // Use currency from fuel prices API (based on detected country) or fallback to user's currency
  const fuelCurrency = fuelPrices?.currency || currency.symbol
  
  // Format last update date
  const formatLastUpdate = (dateStr) => {
    if (!dateStr) return ''
    try {
      const date = new Date(dateStr)
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    } catch {
      return dateStr
    }
  }
  
  return (
    <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] overflow-hidden h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <span className="text-lg">⛽</span>
          <h3 className="text-sm font-semibold">{t('fuelPrices.title')}</h3>
          {fuelPrices?.country && (
            <span className="text-xs px-1.5 py-0.5 bg-[var(--color-bg-tertiary)] rounded text-[var(--color-text-muted)]">
              {fuelPrices.country}
            </span>
          )}
        </div>
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          title="Refresh fuel prices"
          className="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)] transition-colors disabled:opacity-50"
        >
          <svg className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
          </svg>
        </button>
      </div>
      
      <div className="p-4">
        <p className="text-xs text-[var(--color-text-secondary)] mb-4">
          {fuelPrices?.location || 'Loading...'}
        </p>
        
        <div className="space-y-3">
          {[
            { type: 'diesel', labelKey: 'fuelPrices.diesel', color: 'bg-blue-500' },
            { type: 'lpg', labelKey: 'fuelPrices.lpg', color: 'bg-green-500' },
            { type: 'petrol', labelKey: 'fuelPrices.petrol', color: 'bg-yellow-500' },
          ].map((fuel) => (
            <div key={fuel.type} className="flex items-center justify-between group">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${fuel.color}`}></span>
                <span className="text-sm text-[var(--color-text-primary)]">{t(fuel.labelKey)}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-[var(--color-text-primary)]">
                  {fuelCurrency}{fuelPrices?.prices?.[fuel.type]?.toFixed(2) ?? '--'}/L
                </span>
                <span className="text-red-500 text-sm">📈</span>
              </div>
            </div>
          ))}
        </div>
        
        <div className="mt-4 pt-3 border-t border-[var(--color-border)]">
          <p className="text-xs text-[var(--color-text-muted)]">
            {fuelPrices?.source || t('fuelPrices.dataSource')}
            {fuelPrices?.last_update && (
              <span className="ml-1">• {formatLastUpdate(fuelPrices.last_update)}</span>
            )}
          </p>
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { currency } = useCurrency()
  const { t, language } = useTranslation()
  const { user } = useAuth()
  const [vehicles, setVehicles] = useState([])
  const [weather, setWeather] = useState(null)
  const [fuelPrices, setFuelPrices] = useState(null)
  const [isRefreshingFuel, setIsRefreshingFuel] = useState(false)
  const [airQuality, setAirQuality] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [weatherTab, setWeatherTab] = useState('today')
  const [weatherView, setWeatherView] = useState('forecast')
  const [userLocation, setUserLocation] = useState(null)
  const [weatherAlertsModalOpen, setWeatherAlertsModalOpen] = useState(false)
  
  // Drag and drop state
  const [draggedVehicle, setDraggedVehicle] = useState(null)
  const [dragOverVehicle, setDragOverVehicle] = useState(null)
  const [isReorderMode, setIsReorderMode] = useState(false)
  const [isSavingOrder, setIsSavingOrder] = useState(false)
  
  // Insurance state
  const [vehicleInsurance, setVehicleInsurance] = useState({}) // { vehicleId: { active: bool, expiring: policy|null } }
  
  // Get user location - checks user's saved location first, then auto-detect
  useEffect(() => {
    // If user has a manually set location and auto-detect is disabled, use it
    if (user && !user.location_auto_detect && user.location_lat && user.location_lon) {
      setUserLocation({
        lat: user.location_lat,
        lon: user.location_lon,
        name: user.location_name,
        saved: true
      })
      return
    }
    
    // Try to use cached location from localStorage for faster load
    const cachedLocation = localStorage.getItem('gearcargo_user_location')
    if (cachedLocation) {
      try {
        const cached = JSON.parse(cachedLocation)
        // Use cached if less than 10 minutes old
        if (cached.timestamp && Date.now() - cached.timestamp < 600000) {
          setUserLocation({ lat: cached.lat, lon: cached.lon, cached: true })
        }
      } catch (e) {
        localStorage.removeItem('gearcargo_user_location')
      }
    }
    
    // Auto-detect location with high accuracy (uses GPS when available)
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const loc = {
            lat: position.coords.latitude,
            lon: position.coords.longitude,
            accuracy: position.coords.accuracy // meters
          }
          setUserLocation(loc)
          // Cache the location
          localStorage.setItem('gearcargo_user_location', JSON.stringify({
            lat: loc.lat,
            lon: loc.lon,
            timestamp: Date.now()
          }))
        },
        (error) => {
          console.warn('Geolocation error:', error)
          // Default to London center when geolocation unavailable
          setUserLocation({ lat: 51.5074, lon: -0.1278, default: true })
        },
        { 
          enableHighAccuracy: true,  // Use GPS for better accuracy
          timeout: 10000,             // Increase timeout for GPS
          maximumAge: 300000          // 5 minutes cache
        }
      )
    } else {
      // Default to London center when geolocation not supported
      setUserLocation({ lat: 51.5074, lon: -0.1278, default: true })
    }
  }, [user])
  
  // Fetch vehicles
  useEffect(() => {
    const fetchData = async () => {
      try {
        const vehiclesRes = await vehicleApi.getAll()
        setVehicles(vehiclesRes.data.vehicles || [])
      } catch (error) {
        console.error('Failed to fetch vehicles:', error)
      } finally {
        setIsLoading(false)
      }
    }
    fetchData()
  }, [])
  
  // Fetch insurance status for vehicles
  useEffect(() => {
    const fetchInsurance = async () => {
      try {
        const [activeRes, expiringRes] = await Promise.all([
          insuranceApi.getActive(),
          insuranceApi.getExpiring(30)
        ])
        
        const activePolicies = activeRes.data.policies || []
        const expiringPolicies = expiringRes.data.policies || []
        
        // Build a map: vehicleId -> { active, expiring }
        const insuranceMap = {}
        
        // Mark vehicles with active insurance
        activePolicies.forEach(policy => {
          if (policy.vehicle_id) {
            if (!insuranceMap[policy.vehicle_id]) {
              insuranceMap[policy.vehicle_id] = { active: false, expiring: null }
            }
            insuranceMap[policy.vehicle_id].active = true
          }
        })
        
        // Mark vehicles with expiring insurance
        expiringPolicies.forEach(policy => {
          if (policy.vehicle_id) {
            if (!insuranceMap[policy.vehicle_id]) {
              insuranceMap[policy.vehicle_id] = { active: false, expiring: null }
            }
            // Keep the soonest expiring policy
            if (!insuranceMap[policy.vehicle_id].expiring || 
                new Date(policy.end_date) < new Date(insuranceMap[policy.vehicle_id].expiring.end_date)) {
              insuranceMap[policy.vehicle_id].expiring = policy
            }
          }
        })
        
        setVehicleInsurance(insuranceMap)
      } catch (error) {
        console.error('Failed to fetch insurance status:', error)
      }
    }
    fetchInsurance()
  }, [])
  
  // Fetch weather and fuel prices
  useEffect(() => {
    if (!userLocation) return
    
    const fetchExternalData = async () => {
      try {
        let locationName = 'London, United Kingdom'
        let countryCode = 'UK'
        try {
          const geoRes = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${userLocation.lat}&lon=${userLocation.lon}&format=json&addressdetails=1&zoom=18`,
            { headers: { 'User-Agent': 'GearCargo/1.0' } }
          )
          const geoData = await geoRes.json()
          const addr = geoData.address || {}
          // Check address fields from most specific to least specific
          // Nominatim returns different fields based on location type
          locationName = addr.suburb || 
                        addr.hamlet || 
                        addr.village || 
                        addr.town || 
                        addr.city || 
                        addr.municipality ||
                        addr.district ||
                        addr.county ||
                        addr.state ||
                        'Unknown'
          locationName += ', ' + (addr.country || 'Unknown')
          // Get country code for fuel prices (e.g., 'gb', 'de', 'fr')
          countryCode = (addr.country_code || 'uk').toUpperCase()
        } catch (e) {
          console.warn('Geocoding failed:', e)
        }
        
        const [weatherRes, fuelRes, aqRes] = await Promise.all([
          externalApi.getWeather(userLocation.lat, userLocation.lon, locationName),
          externalApi.getFuelPrices(countryCode, locationName, userLocation.lat, userLocation.lon),
          externalApi.getAirQuality(userLocation.lat, userLocation.lon),
        ])
        
        setWeather(weatherRes.data)
        setFuelPrices(fuelRes.data)
        setAirQuality(aqRes.data)
      } catch (error) {
        console.error('Failed to fetch external data:', error)
      }
    }
    
    fetchExternalData()
  }, [userLocation])
  
  // Manual fuel price refresh — force bypasses cache
  const handleRefreshFuelPrices = async () => {
    if (!userLocation || isRefreshingFuel) return
    setIsRefreshingFuel(true)
    try {
      let locationName = fuelPrices?.location || 'London, United Kingdom'
      let countryCode = fuelPrices?.country || 'UK'
      try {
        const geoRes = await fetch(
          `https://nominatim.openstreetmap.org/reverse?lat=${userLocation.lat}&lon=${userLocation.lon}&format=json&addressdetails=1&zoom=18`,
          { headers: { 'User-Agent': 'GearCargo/1.0' } }
        )
        const geoData = await geoRes.json()
        const addr = geoData.address || {}
        locationName = addr.suburb || addr.hamlet || addr.village || addr.town ||
                       addr.city || addr.municipality || addr.district || addr.county ||
                       addr.state || 'Unknown'
        locationName += ', ' + (addr.country || 'Unknown')
        countryCode = (addr.country_code || 'uk').toUpperCase()
      } catch (e) {
        console.warn('Geocoding failed during refresh:', e)
      }
      const fuelRes = await externalApi.getFuelPrices(countryCode, locationName, userLocation.lat, userLocation.lon, true)
      setFuelPrices(fuelRes.data)
    } catch (error) {
      console.error('Failed to refresh fuel prices:', error)
    } finally {
      setIsRefreshingFuel(false)
    }
  }
  
  const handleDeleteVehicle = async (e, vehicleId) => {
    e.preventDefault()
    e.stopPropagation()
    if (!confirm('Permanently delete this vehicle and ALL its data (fuel, services, repairs, taxes, insurance, attachments)? This cannot be undone.')) return
    
    try {
      await vehicleApi.hardDelete(vehicleId)
      setVehicles(vehicles.filter(v => v.id !== vehicleId))
    } catch (error) {
      console.error('Failed to delete vehicle:', error)
    }
  }
  
  const handleEditVehicle = (e, vehicleId) => {
    e.preventDefault()
    e.stopPropagation()
    navigate(`/vehicles/${vehicleId}/edit`)
  }
  
  const handleViewDetails = (e, vehicleId) => {
    e.preventDefault()
    e.stopPropagation()
    navigate(`/vehicles/${vehicleId}`)
  }
  
  // Drag and drop handlers
  const handleDragStart = (e, vehicle) => {
    if (!isReorderMode) return
    setDraggedVehicle(vehicle)
    e.dataTransfer.effectAllowed = 'move'
    // Add a slight delay for visual feedback
    setTimeout(() => {
      e.target.style.opacity = '0.5'
    }, 0)
  }
  
  const handleDragEnd = (e) => {
    e.target.style.opacity = '1'
    setDraggedVehicle(null)
    setDragOverVehicle(null)
  }
  
  const handleDragOver = (e, vehicle) => {
    e.preventDefault()
    if (!draggedVehicle || draggedVehicle.id === vehicle.id) return
    setDragOverVehicle(vehicle)
  }
  
  const handleDragLeave = () => {
    setDragOverVehicle(null)
  }
  
  const handleDrop = async (e, targetVehicle) => {
    e.preventDefault()
    if (!draggedVehicle || draggedVehicle.id === targetVehicle.id) return
    
    // Reorder vehicles in local state
    const newVehicles = [...vehicles]
    const draggedIndex = newVehicles.findIndex(v => v.id === draggedVehicle.id)
    const targetIndex = newVehicles.findIndex(v => v.id === targetVehicle.id)
    
    // Remove dragged item and insert at new position
    const [removed] = newVehicles.splice(draggedIndex, 1)
    newVehicles.splice(targetIndex, 0, removed)
    
    setVehicles(newVehicles)
    setDraggedVehicle(null)
    setDragOverVehicle(null)
  }
  
  // Save the new order to backend
  const saveVehicleOrder = async () => {
    setIsSavingOrder(true)
    try {
      const order = vehicles.map(v => v.id)
      await vehicleApi.reorder(order)
      setIsReorderMode(false)
    } catch (error) {
      console.error('Failed to save vehicle order:', error)
    } finally {
      setIsSavingOrder(false)
    }
  }
  
  // Cancel reorder mode and restore original order
  const cancelReorder = async () => {
    setIsReorderMode(false)
    // Refetch to restore original order
    try {
      const vehiclesRes = await vehicleApi.getAll()
      setVehicles(vehiclesRes.data.vehicles || [])
    } catch (error) {
      console.error('Failed to refresh vehicles:', error)
    }
  }
  
  // Touch support for mobile drag-and-drop with visual feedback
  const [touchStart, setTouchStart] = useState(null)
  const [touchedVehicle, setTouchedVehicle] = useState(null)
  const [dragGhostPosition, setDragGhostPosition] = useState(null)
  const [dragGhostSize, setDragGhostSize] = useState({ width: 0, height: 0 })
  const [isDragActive, setIsDragActive] = useState(false) // Only true after threshold met
  const touchTimerRef = useRef(null)
  
  const TOUCH_HOLD_DELAY = 300 // ms to hold before drag starts
  const TOUCH_MOVE_THRESHOLD = 10 // px movement before drag activates
  
  const handleTouchStart = (e, vehicle) => {
    if (!isReorderMode) return
    
    const touch = e.touches[0]
    const card = e.currentTarget
    const rect = card.getBoundingClientRect()
    
    // Store initial touch position and card info
    setTouchStart({ 
      x: touch.clientX, 
      y: touch.clientY,
      offsetX: touch.clientX - rect.left,
      offsetY: touch.clientY - rect.top
    })
    setTouchedVehicle(vehicle)
    setDragGhostSize({ width: rect.width, height: rect.height })
    setIsDragActive(false)
    
    // Start hold timer - drag only activates after holding
    touchTimerRef.current = setTimeout(() => {
      setIsDragActive(true)
      setDragGhostPosition({ x: touch.clientX, y: touch.clientY })
      // Vibration feedback if available
      if (navigator.vibrate) navigator.vibrate(50)
    }, TOUCH_HOLD_DELAY)
  }
  
  const handleTouchMove = (e, vehicle) => {
    if (!isReorderMode || !touchedVehicle || !touchStart) return
    
    const touch = e.touches[0]
    const dx = Math.abs(touch.clientX - touchStart.x)
    const dy = Math.abs(touch.clientY - touchStart.y)
    
    // If moved before hold timer finished, cancel drag (it was a scroll)
    if (!isDragActive && (dx > TOUCH_MOVE_THRESHOLD || dy > TOUCH_MOVE_THRESHOLD)) {
      clearTimeout(touchTimerRef.current)
      setTouchStart(null)
      setTouchedVehicle(null)
      return
    }
    
    // Only process drag if active
    if (!isDragActive) return
    
    e.preventDefault() // Prevent scrolling only when actually dragging
    
    // Update ghost position to follow finger
    setDragGhostPosition({ x: touch.clientX, y: touch.clientY })
    
    // Hide the ghost temporarily to find element underneath
    const ghostEl = document.getElementById('drag-ghost')
    if (ghostEl) ghostEl.style.display = 'none'
    
    const element = document.elementFromPoint(touch.clientX, touch.clientY)
    
    // Show the ghost again
    if (ghostEl) ghostEl.style.display = 'block'
    
    const vehicleCard = element?.closest('[data-vehicle-id]')
    
    if (vehicleCard) {
      const targetId = parseInt(vehicleCard.dataset.vehicleId)
      const targetVehicle = vehicles.find(v => v.id === targetId)
      if (targetVehicle && targetVehicle.id !== touchedVehicle.id) {
        setDragOverVehicle(targetVehicle)
      }
    } else {
      setDragOverVehicle(null)
    }
  }
  
  const handleTouchEnd = () => {
    // Clear hold timer
    clearTimeout(touchTimerRef.current)
    
    if (isDragActive && touchedVehicle && dragOverVehicle && touchedVehicle.id !== dragOverVehicle.id) {
      // Perform the reorder
      const newVehicles = [...vehicles]
      const draggedIndex = newVehicles.findIndex(v => v.id === touchedVehicle.id)
      const targetIndex = newVehicles.findIndex(v => v.id === dragOverVehicle.id)
      
      const [removed] = newVehicles.splice(draggedIndex, 1)
      newVehicles.splice(targetIndex, 0, removed)
      
      setVehicles(newVehicles)
    }
    
    setTouchStart(null)
    setTouchedVehicle(null)
    setDragOverVehicle(null)
    setDragGhostPosition(null)
    setIsDragActive(false)
  }
  
  if (isLoading) {
    return (
      <div className="p-4 lg:p-6 space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 skeleton h-72 rounded-xl" />
          <div className="skeleton h-72 rounded-xl" />
        </div>
        <div className="skeleton h-8 w-48 rounded-lg" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="skeleton h-64 rounded-xl" />
          ))}
        </div>
      </div>
    )
  }
  
  return (
    <div className="p-4 lg:p-6 pb-24 lg:pb-6">
      {/* Top Widgets Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="lg:col-span-2">
          <WeatherWidget
            weather={weather}
            airQuality={airQuality}
            weatherTab={weatherTab}
            setWeatherTab={setWeatherTab}
            weatherView={weatherView}
            setWeatherView={setWeatherView}
            t={t}
            language={language}
          />
        </div>
        <div>
          <FuelPricesWidget fuelPrices={fuelPrices} currency={currency} t={t} onRefresh={handleRefreshFuelPrices} isRefreshing={isRefreshingFuel} />
        </div>
      </div>
      
      {/* Weather Driving Alerts - only show if we have location */}
      {userLocation && (
        <div className="mb-6">
          <WeatherAlerts 
            userLocation={{
              lat: userLocation.lat,
              lon: userLocation.lon,
              name: weather?.location
            }}
            compact={false}
          />
        </div>
      )}
      
      {/* Weather Alerts Modal for compact view */}
      <WeatherAlertsModal 
        isOpen={weatherAlertsModalOpen}
        onClose={() => setWeatherAlertsModalOpen(false)}
        userLocation={{
          lat: userLocation?.lat,
          lon: userLocation?.lon,
          name: weather?.location
        }}
      />
      
      {/* Your Garage Section */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold">{t('dashboard.yourGarage')}</h2>
          {vehicles.length > 1 && !isReorderMode && (
            <button
              onClick={() => setIsReorderMode(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
              title={t('dashboard.reorderVehicles')}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
              </svg>
              <span className="hidden sm:inline">{t('dashboard.reorder')}</span>
            </button>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {isReorderMode ? (
            <>
              <button
                onClick={cancelReorder}
                className="px-3 py-1.5 text-sm rounded-lg bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] transition-colors"
                disabled={isSavingOrder}
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={saveVehicleOrder}
                className="px-3 py-1.5 text-sm rounded-lg bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white transition-colors flex items-center gap-1.5"
                disabled={isSavingOrder}
              >
                {isSavingOrder ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span>{t('common.saving')}</span>
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    <span>{t('common.save')}</span>
                  </>
                )}
              </button>
            </>
          ) : (
            <Link 
              to="/vehicles/add" 
              className="btn btn-primary flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              {t('dashboard.addVehicle')}
            </Link>
          )}
        </div>
      </div>
      
      {/* Reorder Mode Instructions */}
      {isReorderMode && (
        <div className="mb-4 p-3 rounded-lg bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20">
          <p className="text-sm text-[var(--color-text-secondary)] flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {t('dashboard.reorderInstructions')}
          </p>
        </div>
      )}
      
      {/* Vehicles Grid */}
      {vehicles.length === 0 ? (
        <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] text-center py-16">
          <span className="text-6xl mb-4 block">🚗</span>
          <h3 className="text-lg font-medium mb-2">{t('dashboard.noVehicles')}</h3>
          <p className="text-sm text-[var(--color-text-secondary)] mb-6">
            {t('dashboard.addFirstVehicle')}
          </p>
          <Link to="/vehicles/add" className="btn btn-primary">
            <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            {t('dashboard.addVehicle')}
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {vehicles.map((vehicle, index) => (
            <div
              key={vehicle.id}
              data-vehicle-id={vehicle.id}
              draggable={isReorderMode}
              onDragStart={(e) => handleDragStart(e, vehicle)}
              onDragEnd={handleDragEnd}
              onDragOver={(e) => handleDragOver(e, vehicle)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, vehicle)}
              onTouchStart={(e) => handleTouchStart(e, vehicle)}
              onTouchMove={(e) => handleTouchMove(e, vehicle)}
              onTouchEnd={handleTouchEnd}
              className={`
                group bg-[var(--color-bg-card)] rounded-xl border overflow-hidden transition-all duration-300
                ${isReorderMode 
                  ? 'cursor-grab active:cursor-grabbing border-dashed border-2 border-[var(--color-accent)]/50' 
                  : 'border-[var(--color-border)] hover:border-[var(--color-accent)] hover:shadow-lg hover:shadow-[var(--color-accent)]/10'}
                ${dragOverVehicle?.id === vehicle.id ? 'ring-2 ring-[var(--color-accent)] scale-[1.02]' : ''}
                ${draggedVehicle?.id === vehicle.id ? 'opacity-50' : ''}
                ${touchedVehicle?.id === vehicle.id ? 'ring-2 ring-[var(--color-accent)]' : ''}
              `}
            >
              {/* Drag Handle - only shown in reorder mode */}
              {isReorderMode && (
                <div className="absolute top-2 left-2 z-10 w-8 h-8 rounded-lg bg-[var(--color-accent)] flex items-center justify-center text-white shadow-lg">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 8h16M4 16h16" />
                  </svg>
                </div>
              )}
              
              {/* Order Number Badge - only shown in reorder mode */}
              {isReorderMode && (
                <div className="absolute top-2 right-2 z-10 w-6 h-6 rounded-full bg-[var(--color-bg-card)] border border-[var(--color-border)] flex items-center justify-center text-xs font-bold text-[var(--color-text-secondary)]">
                  {index + 1}
                </div>
              )}
              
              {/* Make the card clickable only when not in reorder mode */}
              {isReorderMode ? (
                <>
                  {/* Vehicle Image */}
                  <div className="relative aspect-[16/10] bg-[var(--color-bg-tertiary)] overflow-hidden">
                    {vehicle.photo_url || vehicle.photo ? (
                      <img 
                        src={vehicle.photo_url || vehicle.photo} 
                        alt={vehicle.name}
                        className="w-full h-full object-cover pointer-events-none"
                        draggable={false}
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-[var(--color-bg-secondary)] to-[var(--color-bg-tertiary)]">
                        <span className="text-6xl opacity-30">🚗</span>
                      </div>
                    )}
                  </div>
                  
                  {/* Vehicle Info */}
                  <div className="p-4">
                    <h3 className="text-base font-bold mb-0.5 text-[var(--color-text-primary)]">{vehicle.name}</h3>
                    <p className="text-sm text-[var(--color-text-secondary)] mb-2">
                      {vehicle.make} {vehicle.model} ({vehicle.year})
                    </p>
                    
                    {vehicle.license_plate && (
                      <span className="inline-block px-2.5 py-1 text-xs font-bold rounded bg-[var(--color-accent)] text-white mb-2">
                        {vehicle.license_plate}
                      </span>
                    )}
                    
                    <p className="text-sm text-[var(--color-text-secondary)]">
                      {t('dashboard.odometer')}: <span className="text-[var(--color-text-primary)] font-semibold">
                        {vehicle.current_mileage?.toLocaleString() || 0} {vehicle.distance_unit || 'km'}
                      </span>
                    </p>
                  </div>
                </>
              ) : (
                <Link 
                  to={`/vehicles/${vehicle.id}`}
                  className="block"
                >
                  {/* Vehicle Image */}
                  <div className="relative aspect-[16/10] bg-[var(--color-bg-tertiary)] overflow-hidden">
                    {vehicle.photo_url || vehicle.photo ? (
                      <img 
                        src={vehicle.photo_url || vehicle.photo} 
                        alt={vehicle.name}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-[var(--color-bg-secondary)] to-[var(--color-bg-tertiary)]">
                        <span className="text-6xl opacity-30">🚗</span>
                      </div>
                    )}
                    
                    {/* Action Buttons Overlay */}
                    <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all duration-300 translate-y-1 group-hover:translate-y-0">
                      <button 
                        onClick={(e) => handleEditVehicle(e, vehicle.id)}
                        className="w-8 h-8 rounded-lg bg-black/60 backdrop-blur-md flex items-center justify-center text-white hover:bg-[var(--color-accent)] transition-colors"
                        title="Edit"
                      >
                        <span className="material-icons-outlined text-sm">edit</span>
                      </button>
                      <button 
                        onClick={(e) => handleViewDetails(e, vehicle.id)}
                        className="w-8 h-8 rounded-lg bg-black/60 backdrop-blur-md flex items-center justify-center text-white hover:bg-[var(--color-accent)] transition-colors"
                        title="Details"
                      >
                        <span className="material-icons-outlined text-sm">list</span>
                      </button>
                      <button 
                        onClick={(e) => handleDeleteVehicle(e, vehicle.id)}
                        className="w-8 h-8 rounded-lg bg-black/60 backdrop-blur-md flex items-center justify-center text-white hover:bg-red-500 transition-colors"
                        title="Delete"
                      >
                        <span className="material-icons-outlined text-sm">delete</span>
                      </button>
                    </div>
                    
                    {/* Insurance Status Badges */}
                    <div className="absolute bottom-2 left-2 flex items-center gap-1">
                      {vehicleInsurance[vehicle.id]?.expiring ? (
                        <div 
                          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-amber-500/90 backdrop-blur-sm text-white text-xs font-medium shadow-lg"
                          title={`${t('dashboard.insuranceExpiring') || 'Insurance expiring'}: ${new Date(vehicleInsurance[vehicle.id].expiring.end_date).toLocaleDateString()}`}
                        >
                          <span className="material-icons-outlined text-sm">warning</span>
                          <span className="hidden sm:inline">{t('dashboard.expiringSoon') || 'Expiring'}</span>
                        </div>
                      ) : vehicleInsurance[vehicle.id]?.active ? (
                        <div 
                          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-green-500/90 backdrop-blur-sm text-white text-xs font-medium shadow-lg"
                          title={t('dashboard.insuranceActive') || 'Insurance active'}
                        >
                          <span className="material-icons-outlined text-sm">verified_user</span>
                          <span className="hidden sm:inline">{t('dashboard.insured') || 'Insured'}</span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                  
                  {/* Vehicle Info */}
                  <div className="p-4">
                    <h3 className="text-base font-bold mb-0.5 text-[var(--color-text-primary)]">{vehicle.name}</h3>
                    <p className="text-sm text-[var(--color-text-secondary)] mb-2">
                      {vehicle.make} {vehicle.model} ({vehicle.year})
                    </p>
                    
                    {vehicle.license_plate && (
                      <span className="inline-block px-2.5 py-1 text-xs font-bold rounded bg-[var(--color-accent)] text-white mb-2">
                        {vehicle.license_plate}
                      </span>
                    )}
                    
                    <p className="text-sm text-[var(--color-text-secondary)]">
                      {t('dashboard.odometer')}: <span className="text-[var(--color-text-primary)] font-semibold">
                        {vehicle.current_mileage?.toLocaleString() || 0} {vehicle.distance_unit || 'km'}
                      </span>
                    </p>
                  </div>
                </Link>
              )}
            </div>
          ))}
        </div>
      )}
      
      {/* Drag Ghost for Touch Devices */}
      {touchedVehicle && dragGhostPosition && (
        <div
          id="drag-ghost"
          className="fixed pointer-events-none z-50 transition-transform duration-75"
          style={{
            left: dragGhostPosition.x - (touchStart?.offsetX || dragGhostSize.width / 2),
            top: dragGhostPosition.y - (touchStart?.offsetY || 40),
            width: dragGhostSize.width,
            transform: 'rotate(-2deg) scale(1.02)',
          }}
        >
          <div className="bg-[var(--color-bg-card)] rounded-xl border-2 border-[var(--color-accent)] shadow-2xl shadow-[var(--color-accent)]/30 overflow-hidden opacity-90">
            {/* Drag indicator */}
            <div className="absolute -top-2 left-1/2 -translate-x-1/2 bg-[var(--color-accent)] text-white text-xs px-3 py-1 rounded-full font-medium shadow-lg flex items-center gap-1">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
              </svg>
              {t('dashboard.dragging') || 'Moving...'}
            </div>
            
            {/* Vehicle Image */}
            <div className="relative aspect-[16/10] bg-[var(--color-bg-tertiary)] overflow-hidden">
              {touchedVehicle.photo_url || touchedVehicle.photo ? (
                <img 
                  src={touchedVehicle.photo_url || touchedVehicle.photo} 
                  alt={touchedVehicle.name}
                  className="w-full h-full object-cover"
                  draggable={false}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-[var(--color-bg-secondary)] to-[var(--color-bg-tertiary)]">
                  <span className="text-5xl opacity-30">🚗</span>
                </div>
              )}
            </div>
            
            {/* Vehicle Info */}
            <div className="p-3">
              <h3 className="text-sm font-bold text-[var(--color-text-primary)]">{touchedVehicle.name}</h3>
              <p className="text-xs text-[var(--color-text-secondary)]">
                {touchedVehicle.make} {touchedVehicle.model}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
