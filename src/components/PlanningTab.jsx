import { useState, useEffect, useMemo } from 'react'
import RidePicker    from './planning/RidePicker'
import ShowPicker    from './planning/ShowPicker'
import PlanTimeline  from './planning/PlanTimeline'
import PlanLoading   from './planning/PlanLoading'
// Steps in the planning flow
const STEP = {
  SETUP:   'setup',    // pick arrival time + rides + shows
  LOADING: 'loading',  // optimizer running
  RESULT:  'result',   // show the plan
}

export default function PlanningTab() {
  const [step, setStep] = useState(STEP.SETUP)

  // Setup state
  const [arrivalTime, setArrivalTime]     = useState('09:00')
  const [departureTime, setDepartureTime] = useState('23:00')
  const [rides, setRides]             = useState([])
  const [shows, setShows]             = useState([])
  const [loadingData, setLoadingData] = useState(true)

  // User selections — rideId → tier ('must' | 'want' | 'avoid')
  const [rideTiers, setRideTiers]   = useState({})
  const [selectedShows, setSelectedShows] = useState(new Set())

  // Result
  const [plan, setPlan]   = useState(null)
  const [baseRequest, setBaseRequest] = useState(null)
  const [replanning, setReplanning]   = useState(false)
  const [error, setError] = useState(null)

  // Load rides + shows on mount
  useEffect(() => {
    Promise.all([
      fetch('/api/plans/rides').then(r => r.json()),
      fetch('/api/plans/shows').then(r => r.json()),
    ])
      .then(([rideData, showData]) => {
        setRides(rideData.rides ?? [])
        setShows(showData.shows ?? [])
        setLoadingData(false)
      })
      .catch(() => {
        setError('Could not load rides and shows.')
        setLoadingData(false)
      })
  }, [])

  const setTier = (rideId, tier) => {
    setRideTiers(prev => {
      const next = { ...prev }
      if (next[rideId] === tier) {
        delete next[rideId]   // clicking active tier again clears it
      } else {
        next[rideId] = tier
      }
      return next
    })
  }

  const toggleShow = (showId) => {
    setSelectedShows(prev => {
      const next = new Set(prev)
      next.has(showId) ? next.delete(showId) : next.add(showId)
      return next
    })
  }

  const mustCount = useMemo(
    () => Object.values(rideTiers).filter(t => t === 'must').length,
    [rideTiers]
  )

  const buildPlan = async () => {
    setStep(STEP.LOADING)
    setError(null)

    // Partition rides by tier
    const must_rides = []
    const want_rides = []
    const avoid_rides = []
    for (const [rideId, tier] of Object.entries(rideTiers)) {
      if (tier === 'must')  must_rides.push(rideId)
      if (tier === 'want')  want_rides.push(rideId)
      if (tier === 'avoid') avoid_rides.push(rideId)
    }

    // Everything not tiered and not avoided → optional
    const tiered = new Set(Object.keys(rideTiers))
    const optional_rides = rides
      .filter(r => !tiered.has(r.id))
      .map(r => r.id)

    // Shows — send just the ID, let the solver pick the time
    const show_events = [...selectedShows].map(show_id => ({ show_id }))

    // Pacific date — the park's local date.
    const pacificDate = new Date().toLocaleDateString('en-CA', {
      timeZone: 'America/Los_Angeles',
    })

    // Save the base request so re-planning can reuse the same selections
    const payload = {
      date: pacificDate,
      arrival_time: arrivalTime,
      departure_time: departureTime,
      must_rides,
      want_rides,
      optional_rides,
      avoid_rides,
      show_events,
      use_cp_sat: true,
    }
    setBaseRequest(payload)

    try {
      const resp = await fetch('/api/plans', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!resp.ok) {
        const err = await resp.json()
        throw new Error(err.detail || 'Optimizer failed')
      }

      const data = await resp.json()
      setPlan(data)
      setStep(STEP.RESULT)
    } catch (e) {
      setError(e.message)
      setStep(STEP.SETUP)
    }
  }

  // Re-plan the remaining day from the user's current position and time.
  const replan = async ({ completedRideIds, startLat, startLng }) => {
    if (!baseRequest) return
    setReplanning(true)

    // Current Pacific time as HH:MM for the start_time field
    const nowPacific = new Date().toLocaleTimeString('en-GB', {
      timeZone: 'America/Los_Angeles',
      hour: '2-digit', minute: '2-digit',
    })  // en-GB gives 24h HH:MM

    try {
      const resp = await fetch('/api/plans', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...baseRequest,
          completed_rides: completedRideIds,
          start_lat: startLat,
          start_lng: startLng,
          start_time: nowPacific,
        }),
      })

      if (!resp.ok) {
        const err = await resp.json()
        throw new Error(err.detail || 'Re-planning failed')
      }

      const data = await resp.json()
      setPlan(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setReplanning(false)
    }
  }

  const reset = () => {
    setPlan(null)
    setStep(STEP.SETUP)
  }

  // ── Render ────────────────────────────────────────────────────────────
  if (step === STEP.LOADING) {
    return <PlanLoading />
  }

  if (step === STEP.RESULT && plan) {
    return (
      <PlanTimeline
        plan={plan}
        onReset={reset}
        onReplan={replan}
        replanning={replanning}
      />
    )
  }

  // SETUP step
  if (loadingData) {
    return (
      <div className="center-state">
        <div className="spinner" />
        <p>Loading rides and shows…</p>
      </div>
    )
  }

  return (
    <div className="planning-setup">
      <div className="planning-intro">
        <h2 className="planning-title">Plan Your Day</h2>
        <p className="planning-body">
          Mark the rides you can't miss, the ones you'd like to do, and any you
          want to skip. Pick your shows, and we'll build your optimal route.
        </p>
      </div>

      {error && (
        <div className="planning-error">⚠ {error}</div>
      )}

      {/* Arrival + departure times */}
      <section className="setup-section">
        <div className="time-row">
          <div className="time-field">
            <label className="setup-label">Arrival time</label>
            <input
              type="time"
              className="time-input"
              value={arrivalTime}
              onChange={e => setArrivalTime(e.target.value)}
            />
          </div>
          <div className="time-field">
            <label className="setup-label">Departure time</label>
            <input
              type="time"
              className="time-input"
              value={departureTime}
              onChange={e => setDepartureTime(e.target.value)}
            />
          </div>
        </div>
      </section>

      {/* Ride picker */}
      <RidePicker rides={rides} rideTiers={rideTiers} onSetTier={setTier} />

      {/* Show picker */}
      <ShowPicker shows={shows} selected={selectedShows} onToggle={toggleShow} />

      {/* Build button */}
      <div className="build-bar">
        <div className="build-summary">
          {mustCount > 0 && <span>{mustCount} must-ride{mustCount !== 1 ? 's' : ''}</span>}
          {selectedShows.size > 0 && <span>{selectedShows.size} show{selectedShows.size !== 1 ? 's' : ''}</span>}
        </div>
        <button className="build-btn" onClick={buildPlan}>
          Build My Plan ✦
        </button>
      </div>
    </div>
  )
}
