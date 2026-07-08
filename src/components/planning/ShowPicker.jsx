export default function ShowPicker({ shows, selected, onToggle }) {
  if (shows.length === 0) {
    return (
      <section className="setup-section">
        <label className="setup-label">Add shows</label>
        <p className="setup-hint">No showtimes loaded for today.</p>
      </section>
    )
  }

  return (
    <section className="setup-section">
      <label className="setup-label">Add shows (optional)</label>
      <p className="setup-hint">
        We'll pick the showing that fits your day best.
      </p>

      <div className="show-picker-grid">
        {shows.map(show => {
          const isSelected = selected.has(show.id)
          const firstTime  = show.times?.[0]?.time
          const lastTime   = show.times?.[show.times.length - 1]?.time
          const timeRange  = show.times?.length > 1
            ? `${firstTime}–${lastTime} · ${show.times.length} showings`
            : firstTime

          return (
            <button
              key={show.id}
              className={`show-picker-card ${isSelected ? 'selected' : ''}`}
              onClick={() => onToggle(show.id)}
            >
              <span className="show-picker-check">{isSelected ? '✦' : ''}</span>
              <span className="show-picker-name">{show.name}</span>
              <span className="show-picker-times">{timeRange}</span>
              {show.duration_minutes && (
                <span className="show-picker-duration">{show.duration_minutes} min</span>
              )}
            </button>
          )
        })}
      </div>
    </section>
  )
}
