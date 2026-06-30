function waitColor(mins) {
  if (mins == null) return 'c-muted'
  if (mins < 20)   return 'c-green'
  if (mins < 45)   return 'c-amber'
  return 'c-red'
}

function chipClass(status) {
  if (status === 'OPERATING')     return 'status-chip chip-open'
  if (status === 'DOWN')          return 'status-chip chip-down'
  return 'status-chip chip-closed'
}

function chipLabel(status) {
  if (status === 'OPERATING') return 'Open'
  if (status === 'DOWN')      return 'Down'
  return 'Closed'
}

export default function RideCard({ ride }) {
  const isClosed = ride.status !== 'OPERATING' || ride.wait_minutes == null

  return (
    <div className={`ride-card ${isClosed ? 'is-closed' : ''}`}>
      <p className="card-name">{ride.name}</p>

      <div className="card-wait">
        {ride.wait_minutes != null ? (
          <>
            <span className={`wait-number ${waitColor(ride.wait_minutes)}`}>
              {ride.wait_minutes}
            </span>
            <span className="wait-unit">min wait</span>
          </>
        ) : (
          <span className="wait-number c-muted" style={{ fontSize: '1.3rem' }}>
            —
          </span>
        )}
      </div>

      {ride.duration_minutes != null && (
        <p className="card-duration">
          🎢 {ride.duration_minutes} min ride
        </p>
      )}

      <span className={chipClass(ride.status)}>
        {chipLabel(ride.status)}
      </span>
    </div>
  )
}
