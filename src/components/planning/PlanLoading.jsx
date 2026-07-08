import { useState, useEffect } from 'react'

const MESSAGES = [
  'Predicting wait times across the day…',
  'Finding the shortest lines…',
  'Fitting your shows into the schedule…',
  'Calculating walking routes…',
  'Optimizing your route…',
  'Almost there…',
]

export default function PlanLoading() {
  const [msgIndex, setMsgIndex] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setMsgIndex(i => Math.min(i + 1, MESSAGES.length - 1))
    }, 1600)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="plan-loading">
      <div className="plan-loading-stars">
        <span className="loading-star s1">✦</span>
        <span className="loading-star s2">✦</span>
        <span className="loading-star s3">✦</span>
      </div>
      <p className="plan-loading-msg">{MESSAGES[msgIndex]}</p>
      <p className="plan-loading-sub">Building your optimal day</p>
    </div>
  )
}
