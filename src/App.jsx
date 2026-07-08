import { useState, useEffect, useCallback, useMemo } from 'react'
import StarField from './components/StarField'
import WaitTimesTab from './components/WaitTimesTab'
import ShowtimesTab from './components/ShowtimesTab'
import PlanningTab from './components/PlanningTab'

//refreshes every 10 minutes
const REFRESH_SECONDS = 600 

function formatCountdown(sec) {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit', hour12: true,
  })
}

export default function App() {
  const [rides, setRides]           = useState([])
  const [lastUpdated, setLastUpdated] = useState(null)
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)
  const [tab, setTab]               = useState('waittimes')
  const [countdown, setCountdown]   = useState(REFRESH_SECONDS)

  const fetchRides = useCallback(async () => {
    try {
      const resp = await fetch('/api/rides/live')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      setRides(data.rides ?? [])
      setLastUpdated(data.last_updated)
      setCountdown(REFRESH_SECONDS)
      setError(null)
    } catch (e) {
      setError('Unable to reach the API. Is the FastAPI server running?')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchRides()
    const interval = setInterval(fetchRides, REFRESH_SECONDS * 1000)
    return () => clearInterval(interval)
  }, [fetchRides])

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown(c => (c > 0 ? c - 1 : REFRESH_SECONDS))
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="app">
      <StarField />

      <div className="content-layer">
        {/* Header */}
        <header className="header">
          <div className="logo">
            <span className="logo-star">✦</span>
            <h1>DisneyLined</h1>
            <span className="logo-star">✦</span>
          </div>
          <p className="header-subtitle">Disneyland Park · Live Wait Times</p>

          <div className="refresh-bar">
            {lastUpdated && (
              <span>Updated at {formatTime(lastUpdated)}</span>
            )}
            <span className="live-dot">
              <span className="live-dot-circle" />
              Live
            </span>
            <span>Refreshes in {formatCountdown(countdown)}</span>
          </div>
        </header>

        {/* Tab bar */}
        <nav className="tabs">
          <button
            className={`tab-btn ${tab === 'waittimes' ? 'active' : ''}`}
            onClick={() => setTab('waittimes')}
          >
            Wait Times
          </button>
          <button
            className={`tab-btn ${tab === 'showtimes' ? 'active' : ''}`}
            onClick={() => setTab('showtimes')}
          >
            Showtimes
          </button>
          <button
            className={`tab-btn ${tab === 'planning' ? 'active' : ''}`}
            onClick={() => setTab('planning')}
          >
            Plan My Day
            <span className="new-badge">New</span>
          </button>
        </nav>

        {/* Content */}
        <main className="main">
          {tab === 'waittimes' && (
            <WaitTimesTab rides={rides} loading={loading} error={error} />
          )}
          {tab === 'showtimes' && <ShowtimesTab />}
          {tab === 'planning' && <PlanningTab />}
        </main>
      </div>
    </div>
  )
}
