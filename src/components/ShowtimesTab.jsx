import { useState, useEffect } from 'react'

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit', hour12: true,
  })
}

function isUpcoming(iso) {
  return new Date(iso).getTime() > Date.now()
}

export default function ShowtimesTab() {
  const [shows, setShows]     = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  useEffect(() => {
    fetch('/api/shows/today')
      .then(r => r.json())
      .then(data => {
        setShows(data.shows ?? [])
        setLoading(false)
      })
      .catch(() => {
        setError('Unable to load showtimes.')
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="center-state">
        <div className="spinner" />
        <p>Loading showtimes…</p>
      </div>
    )
  }

  if (error) {
    return <div className="center-state"><p style={{ color: 'var(--red)' }}>⚠ {error}</p></div>
  }

  if (shows.length === 0) {
    return (
      <div className="center-state">
        <p style={{ fontSize: '1.8rem', marginTop: '0.5rem' }}>
          Showtimes refresh daily at 12:15 am PST.
          Please wait and check back soon!
        </p>
      </div>
    )
  }

  return (
    <section className="showtimes-list">
      <p className="section-label">Today's Performances</p>

      {shows.map(show => (
        <div key={show.id} className="show-row">
          <span className="show-name">{show.name}</span>
          <div className="show-times">
            {show.times.map((t, i) => (
              <span
                key={i}
                className={`show-time-chip ${isUpcoming(t) ? '' : 'show-time-past'}`}
              >
                {formatTime(t)}
              </span>
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}
