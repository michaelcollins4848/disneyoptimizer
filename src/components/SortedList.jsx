function barColor(mins) {
  if (mins < 20) return 'bg-green'
  if (mins < 45) return 'bg-amber'
  return 'bg-red'
}

function textColor(mins) {
  if (mins < 20) return 'c-green'
  if (mins < 45) return 'c-amber'
  return 'c-red'
}

export default function SortedList({ rides }) {
  if (rides.length === 0) return null

  const maxWait = Math.max(...rides.map(r => r.wait_minutes), 1)

  return (
    <section className="sorted-list">
      <p className="section-label">All Wait Times</p>

      {rides.map((ride, i) => {
        const pct = Math.round((ride.wait_minutes / maxWait) * 100)
        return (
          <div key={ride.id} className="sorted-row">
            <span className="sorted-rank">{i + 1}</span>
            <span className="sorted-name" title={ride.name}>{ride.name}</span>
            <div className="bar-track">
              <div
                className={`bar-fill ${barColor(ride.wait_minutes)}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className={`sorted-time ${textColor(ride.wait_minutes)}`}>
              {ride.wait_minutes} min
            </span>
          </div>
        )
      })}
    </section>
  )
}
