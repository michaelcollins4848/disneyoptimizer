import { useState } from 'react'

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit', hour12: true,
  })
}

function waitColor(mins) {
  if (mins == null) return ''
  if (mins < 20) return 'c-green'
  if (mins < 45) return 'c-amber'
  return 'c-red'
}

function gapAfter(gaps, itemName) {
  return gaps.find(g => g.after === itemName)
}

export default function PlanTimeline({ plan, onReset, onReplan, replanning }) {
  const { plan: items, gaps = [], total_wait, total_rides, feasible } = plan

  const [completed, setCompleted] = useState(new Set())

  const totalWaitHours = Math.floor(total_wait / 60)
  const totalWaitMins  = total_wait % 60
  const waitLabel = totalWaitHours > 0
    ? `${totalWaitHours}h ${totalWaitMins}m`
    : `${totalWaitMins}m`

  const toggleDone = (rideId) => {
    setCompleted(prev => {
      const next = new Set(prev)
      next.has(rideId) ? next.delete(rideId) : next.add(rideId)
      return next
    })
  }

  const lastCompletedItem = [...items]
    .filter(i => i.type === 'ride' && i.ride_id && completed.has(i.ride_id))
    .sort((a, b) => new Date(b.start_at) - new Date(a.start_at))[0]

  const handleReplan = () => {
    if (!lastCompletedItem) return
    onReplan({
      completedRideIds: [...completed],
      startLat: lastCompletedItem.latitude,
      startLng: lastCompletedItem.longitude,
    })
  }

  return (
    <div className="plan-result">
      <div className="plan-header">
        <h2 className="planning-title">Your Optimized Day</h2>
        <div className="plan-stats">
          <div className="plan-stat">
            <span className="plan-stat-value">{total_rides}</span>
            <span className="plan-stat-label">rides</span>
          </div>
          <div className="plan-stat">
            <span className="plan-stat-value">{waitLabel}</span>
            <span className="plan-stat-label">total wait</span>
          </div>
          <div className="plan-stat">
            <span className="plan-stat-value">
              {items.filter(i => i.type === 'show').length}
            </span>
            <span className="plan-stat-label">shows</span>
          </div>
        </div>
        {!feasible && (
          <div className="plan-warning">
            &#9888; Not all must-do rides could fit. Consider arriving earlier or removing some.
          </div>
        )}
        <p className="plan-subhint">
          Tap the circle on each ride as you finish it. If your day drifts off
          schedule, use <strong>Re-plan from here</strong> to rebuild the rest of
          your day from your current spot and time.
        </p>
      </div>

      {completed.size > 0 && (
        <div className="replan-bar">
          <div className="replan-text">
            <span className="replan-info">
              {completed.size} ride{completed.size !== 1 ? 's' : ''} done
              {lastCompletedItem && ` \u00b7 last: ${lastCompletedItem.name}`}
            </span>
            <span className="replan-why">
              Re-optimizes your remaining rides from {lastCompletedItem ? lastCompletedItem.name : 'your last ride'} using the current time and live wait times.
            </span>
          </div>
          <button
            className="replan-btn"
            onClick={handleReplan}
            disabled={replanning || !lastCompletedItem}
          >
            {replanning ? 'Re-planning\u2026' : '\u21bb Re-plan from here'}
          </button>
        </div>
      )}

      <div className="timeline">
        {items.map((item, i) => {
          const gap    = gapAfter(gaps, item.name)
          const isRide = item.type === 'ride'
          const isDone = isRide && item.ride_id && completed.has(item.ride_id)
          return (
            <div key={i}>
              <TimelineCard
                item={item}
                isDone={isDone}
                onToggleDone={isRide && item.ride_id ? () => toggleDone(item.ride_id) : null}
              />
              {i < items.length - 1 && item.walk_minutes != null && item.walk_minutes > 0 && !gap && (
                <div className="walk-connector">
                  <span className="walk-line" />
                  <span className="walk-label">&#128694; {item.walk_minutes} min walk</span>
                </div>
              )}
              {gap && <GapCard gap={gap} />}
            </div>
          )
        })}
      </div>

      <button className="build-btn secondary" onClick={onReset}>
        &#8592; Start Over
      </button>
    </div>
  )
}

function TimelineCard({ item, isDone, onToggleDone }) {
  const isShow = item.type === 'show'

  return (
    <div className={`timeline-card ${isShow ? 'is-show' : 'is-ride'} ${isDone ? 'is-done' : ''}`}>
      <div className="timeline-time">
        <span className="timeline-time-value">{formatTime(item.start_at)}</span>
        {item.walk_minutes != null && item.walk_minutes > 0 && (
          <span className="timeline-arrive">arrive {formatTime(item.arrive_at)}</span>
        )}
      </div>

      <div className="timeline-content">
        <div className="timeline-name-row">
          {isShow && <span className="show-tag">SHOW</span>}
          <span className="timeline-name">{item.name}</span>
        </div>
        <div className="timeline-meta">
          {item.predicted_wait != null && (
            <span className={`timeline-wait ${waitColor(item.predicted_wait)}`}>
              ~{item.predicted_wait} min wait
            </span>
          )}
          {item.duration_minutes != null && (
            <span className="timeline-duration">
              {item.duration_minutes} min {isShow ? 'show' : 'ride'}
            </span>
          )}
        </div>
      </div>

      {onToggleDone && (
        <button
          className={`done-btn ${isDone ? 'done-active' : ''}`}
          onClick={onToggleDone}
          title={isDone ? 'Mark as not done' : 'Mark as done'}
        >
          {isDone ? '\u2713' : '\u25cb'}
        </button>
      )}
    </div>
  )
}

function GapCard({ gap }) {
  const icon = gap.type === 'fill_ride' ? '\ud83c\udfa2'
             : gap.type === 'break'     ? '\ud83c\udf7f'
             : '\u2728'
  return (
    <div className="gap-card">
      <span className="gap-icon">{icon}</span>
      <div className="gap-content">
        <span className="gap-time">{gap.gap_minutes} min free</span>
        <span className="gap-message">{gap.message}</span>
      </div>
    </div>
  )
}
