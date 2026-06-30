import { useMemo } from 'react'

export default function StarField() {
  const stars = useMemo(() =>
    Array.from({ length: 130 }, (_, i) => ({
      id: i,
      x:        Math.random() * 100,
      y:        Math.random() * 100,
      size:     Math.random() * 1.6 + 0.4,
      opacity:  Math.random() * 0.55 + 0.1,
      duration: (Math.random() * 3 + 2).toFixed(2),
      delay:    (Math.random() * 5).toFixed(2),
    })), []
  )

  return (
    <div className="starfield" aria-hidden="true">
      {stars.map(s => (
        <div
          key={s.id}
          className="star"
          style={{
            left:              `${s.x}%`,
            top:               `${s.y}%`,
            width:             `${s.size}px`,
            height:            `${s.size}px`,
            opacity:           s.opacity,
            animationDuration: `${s.duration}s`,
            animationDelay:    `${s.delay}s`,
          }}
        />
      ))}
    </div>
  )
}
