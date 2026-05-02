'use client'

import { useEffect, useState, useCallback, useRef } from 'react'

interface Particle {
  id: number
  x: number
  y: number
  rotation: number
  color: string
  size: number
  animationDelay: number
  animationDuration: number
}

interface ConfettiProps {
  active: boolean
  duration?: number
}

const COLORS = ['#10B981', '#F59E0B', '#EF4444', '#3B82F6', '#8B5CF6', '#EC4899']

// Seeded random for consistent values
function seededRandom(seed: number) {
  const x = Math.sin(seed) * 10000
  return x - Math.floor(x)
}

export function Confetti({ active, duration = 3000 }: ConfettiProps) {
  const [particles, setParticles] = useState<Particle[]>([])
  const [isVisible, setIsVisible] = useState(false)
  const seedRef = useRef(0)

  const createParticles = useCallback(() => {
    // Use a new seed each time confetti is triggered
    const baseSeed = seedRef.current++
    const newParticles: Particle[] = []
    for (let i = 0; i < 100; i++) {
      const seed = baseSeed * 100 + i
      newParticles.push({
        id: i,
        x: seededRandom(seed) * 100,
        y: -10 - seededRandom(seed + 1) * 20,
        rotation: seededRandom(seed + 2) * 360,
        color: COLORS[Math.floor(seededRandom(seed + 3) * COLORS.length)],
        size: 4 + seededRandom(seed + 4) * 6,
        animationDelay: seededRandom(seed + 5) * 500,
        animationDuration: 2000 + seededRandom(seed + 6) * 1000,
      })
    }
    return newParticles
  }, [])

  useEffect(() => {
    if (active) {
      setIsVisible(true)
      setParticles(createParticles())
      
      const hideTimer = setTimeout(() => {
        setIsVisible(false)
        setParticles([])
      }, duration)

      return () => clearTimeout(hideTimer)
    }
  }, [active, duration, createParticles])

  if (!isVisible) return null

  return (
    <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden">
      {particles.map((particle) => (
        <div
          key={particle.id}
          className="absolute animate-confetti"
          style={{
            left: `${particle.x}%`,
            top: `${particle.y}%`,
            width: particle.size,
            height: particle.size,
            backgroundColor: particle.color,
            transform: `rotate(${particle.rotation}deg)`,
            animationDelay: `${particle.animationDelay}ms`,
            animationDuration: `${particle.animationDuration}ms`,
          }}
        />
      ))}
    </div>
  )
}
