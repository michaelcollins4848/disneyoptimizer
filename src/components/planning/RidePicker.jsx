import { useState, useMemo } from 'react'

const TIERS = [
  { key: 'must',  label: 'Must',  color: 'tier-must' },
  { key: 'want',  label: 'Want',  color: 'tier-want' },
  { key: 'avoid', label: 'Avoid', color: 'tier-avoid' },
]

export default function RidePicker({ rides, rideTiers, onSetTier }) {
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return rides.filter(r => r.name.toLowerCase().includes(q))
  }, [rides, search])

  return (
    <section className="setup-section">
      <label className="setup-label">Choose your rides</label>
      <p className="setup-hint">
        Anything you don't mark will be treated as optional and used to fill gaps.
      </p>

      <input
        type="text"
        className="ride-search"
        placeholder="Search rides…"
        value={search}
        onChange={e => setSearch(e.target.value)}
      />

      <div className="ride-picker-list">
        {filtered.map(ride => {
          const tier = rideTiers[ride.id]
          return (
            <div key={ride.id} className={`ride-picker-row ${tier ? 'has-tier' : ''}`}>
              <div className="ride-picker-info">
                <span className="ride-picker-name">{ride.name}</span>
                {ride.duration_minutes != null && (
                  <span className="ride-picker-duration">{ride.duration_minutes} min</span>
                )}
              </div>
              <div className="tier-buttons">
                {TIERS.map(t => (
                  <button
                    key={t.key}
                    className={`tier-btn ${t.color} ${tier === t.key ? 'active' : ''}`}
                    onClick={() => onSetTier(ride.id, t.key)}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
