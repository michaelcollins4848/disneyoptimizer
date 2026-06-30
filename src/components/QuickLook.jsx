function waitColor(mins) {
  if (mins == null) return 'c-muted'
  if (mins < 20)   return 'c-green'
  if (mins < 45)   return 'c-amber'
  return 'c-red'
}

export default function QuickLook({ rides }) {
  const under20 = [...rides]
    .sort((a, b) => a.wait_minutes - b.wait_minutes)
    .filter(r => r.wait_minutes < 20)

  if (under20.length === 0) return (
    <section className="quick-look">
      <p className="section-label">Shortest Waits Right Now</p>
      <p style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>
        No rides under 20 minutes right now.
      </p>
    </section>
  )

  return (
    <section className="quick-look">
      <p className="section-label">Shortest Waits Right Now</p>
      <div className="quick-pills">
        {under20.map((ride, i) => (
          <div key={ride.id} className="quick-pill">
            <span className="quick-pill-rank">{i + 1}</span>
            <span className="quick-pill-name">{ride.name}</span>
            <span className={`quick-pill-time ${waitColor(ride.wait_minutes)}`}>
              {ride.wait_minutes} min
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
