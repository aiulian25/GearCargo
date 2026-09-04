/**
 * Routing contract tests.
 *
 * Written before the react-router v6 -> v7 major upgrade and run against BOTH,
 * so they prove the upgrade preserved behaviour rather than documenting
 * whatever the new version happens to do.
 *
 * They mirror the shape of src/App.jsx rather than importing it: a pathless
 * layout route with an <Outlet/> and relative children, an index route, params,
 * search params, programmatic navigation, a replace-redirect and a catch-all.
 * Importing App would drag in every context, lazy chunk and the API client —
 * that tests the app, not the router.
 */
import { describe, it, expect } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import {
  Link,
  MemoryRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom'

function AppLayout() {
  const navigate = useNavigate()
  return (
    <div>
      <nav>
        <Link to="/vehicles">Vehicles</Link>
        <button onClick={() => navigate(-1)}>Back</button>
      </nav>
      <main><Outlet /></main>
    </div>
  )
}

function Dashboard() {
  const navigate = useNavigate()
  return (
    <div>
      <h1>Dashboard</h1>
      <button onClick={() => navigate('/vehicles/7')}>Open vehicle 7</button>
    </div>
  )
}

function VehicleDetail() {
  const { id } = useParams()
  return <h1>Vehicle {id}</h1>
}

function Vehicles() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filter = searchParams.get('filter') || 'all'
  return (
    <div>
      <h1>Vehicles</h1>
      <p>filter: {filter}</p>
      <button onClick={() => setSearchParams({ filter: 'archived' })}>Archive filter</button>
    </div>
  )
}

function TestApp({ initialEntries = ['/'] }) {
  return (
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/login" element={<h1>Login</h1>} />
        <Route path="/shared/report/:token" element={<SharedReport />} />
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="vehicles" element={<Vehicles />} />
          <Route path="vehicles/:id" element={<VehicleDetail />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </MemoryRouter>
  )
}

function SharedReport() {
  const { token } = useParams()
  return <h1>Report {token}</h1>
}

describe('route resolution', () => {
  it('renders the index route inside the layout', () => {
    render(<TestApp />)

    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Vehicles' })).toBeTruthy()   // layout rendered
  })

  it('resolves a relative child path under a pathless layout route', () => {
    render(<TestApp initialEntries={['/vehicles']} />)

    expect(screen.getByRole('heading', { name: 'Vehicles' })).toBeTruthy()
  })

  it('passes URL params through useParams', () => {
    render(<TestApp initialEntries={['/vehicles/42']} />)

    expect(screen.getByRole('heading', { name: 'Vehicle 42' })).toBeTruthy()
  })

  it('handles a token param on a public route', () => {
    render(<TestApp initialEntries={['/shared/report/abc123']} />)

    expect(screen.getByRole('heading', { name: 'Report abc123' })).toBeTruthy()
  })

  it('redirects an unknown path to the index via the catch-all', () => {
    render(<TestApp initialEntries={['/no/such/page']} />)

    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeTruthy()
  })

  it('reads a search param from the URL', () => {
    render(<TestApp initialEntries={['/vehicles?filter=archived']} />)

    expect(screen.getByText('filter: archived')).toBeTruthy()
  })
})

describe('navigation', () => {
  it('follows a <Link>', async () => {
    render(<TestApp />)

    fireEvent.click(screen.getByRole('link', { name: 'Vehicles' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Vehicles' })).toBeTruthy())
  })

  it('navigates programmatically with useNavigate', async () => {
    render(<TestApp />)

    fireEvent.click(screen.getByRole('button', { name: 'Open vehicle 7' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Vehicle 7' })).toBeTruthy())
  })

  it('goes back through the history stack with navigate(-1)', async () => {
    render(<TestApp initialEntries={['/', '/vehicles']} />)
    expect(screen.getByRole('heading', { name: 'Vehicles' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Back' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeTruthy())
  })

  it('updates search params without leaving the route', async () => {
    render(<TestApp initialEntries={['/vehicles']} />)
    expect(screen.getByText('filter: all')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Archive filter' }))

    await waitFor(() => expect(screen.getByText('filter: archived')).toBeTruthy())
  })
})

describe('open redirect (the advisory this upgrade closes)', () => {
  // GHSA "Open redirect via backslash in <Link> and useNavigate"
  // (CVE-2025-68470 bypass). A browser reads a backslash in a URL as a forward
  // slash, so "\\evil.com" becomes the protocol-relative "//evil.com" — a
  // target that looks internal to the app but leaves the origin.
  //
  // The fix lives at NAVIGATION time, not in the rendered href: react-router
  // 7.18 refuses the navigation outright ("External navigation is not
  // allowed"). So the property to assert is the resulting location, which is
  // what an attacker actually cares about.
  const HOSTILE = ['\\\\evil.com', '\\/evil.com', '/\\evil.com', '//evil.com']

  function CurrentPath() {
    const location = useLocation()
    return <span data-testid="path">{location.pathname}</span>
  }

  function NavigateButton({ to }) {
    const navigate = useNavigate()
    return <button onClick={() => navigate(to)}>navigate</button>
  }

  function renderHostile(to) {
    return render(
      <MemoryRouter>
        <NavigateButton to={to} />
        <Link to={to}>hostile link</Link>
        <CurrentPath />
      </MemoryRouter>
    )
  }

  const escapesOrigin = (path) => /^\s*(\/\\|\\\/|\/\/|\\\\)/.test(path || '')

  it.each(HOSTILE)('useNavigate(%j) cannot leave the origin', (to) => {
    renderHostile(to)

    // The router may refuse outright — that is the fix, and a refusal is a pass.
    try {
      fireEvent.click(screen.getByRole('button', { name: 'navigate' }))
    } catch {
      /* refused */
    }

    const path = screen.getByTestId('path').textContent
    expect(escapesOrigin(path), `landed on ${JSON.stringify(path)}`).toBe(false)
  })

  it.each(HOSTILE)('clicking a <Link to=%j> cannot leave the origin', (to) => {
    renderHostile(to)

    try {
      fireEvent.click(screen.getByRole('link', { name: 'hostile link' }))
    } catch {
      /* refused */
    }

    const path = screen.getByTestId('path').textContent
    expect(escapesOrigin(path), `landed on ${JSON.stringify(path)}`).toBe(false)
  })
})
