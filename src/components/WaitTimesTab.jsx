import { useMemo } from 'react'
import QuickLook  from './QuickLook'
import SortedList from './SortedList'
import RideCard   from './RideCard'

export default function WaitTimesTab({ rides, loading, error }) {
  const operating = useMemo(
    () => rides.filter(r => r.status === 'OPERATING' && r.wait_minutes != null)
              .sort((a, b) => b.wait_minutes - a.wait_minutes),
    [rides]
  )

  if (loading) {
    return (
      <div className="center-state">
        <div className="spinner" />
        <p>Loading wait times…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="center-state">
        <p style={{ color: 'var(--red)', marginBottom: '0.5rem' }}>⚠ {error}</p>
        <p style={{ fontSize: '0.8rem' }}>Make sure <code>uvicorn api.main:app --reload</code> is running.</p>
      </div>
    )
  }

  if (rides.length === 0) {
    return (
      <div className="center-state">
        <p>No ride data yet — the park may be closed or data is still coming in.</p>
      </div>
    )
  }

  return (
    <>
      <QuickLook rides={operating} />
      <SortedList rides={operating} />

      <section className="cards-section">
        <p className="section-label">All Attractions</p>
        <div className="card-grid">
          {rides.map(ride => (
            <RideCard key={ride.id} ride={ride} />
          ))}
        </div>
      </section>
    </>
  )
}
