const COMING_FEATURES = [
  'Set must-ride, want-to-ride, and optional attractions',
  'ML-powered wait time predictions by time of day',
  'Optimal ride order using constraint solving',
  'Live re-planning as waits change throughout your visit',
]

export default function PlanningTab() {
  return (
    <div className="planning-view">
      <div className="planning-glyph">✦ ✦ ✦</div>

      <h2 className="planning-title">Your Day, Optimized</h2>

      <p className="planning-body">
        The planner is being built. Once enough wait time data is collected,
        the ML model will learn each ride's patterns — and hand them to the
        optimizer to build you the perfect itinerary.
      </p>

      <div className="planning-features">
        {COMING_FEATURES.map((f, i) => (
          <div key={i} className="planning-feature">
            <span className="feature-dot" />
            {f}
          </div>
        ))}
      </div>
    </div>
  )
}
