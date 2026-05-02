'use client'

import { useEffect, useState } from 'react'
import { Flame, TrendingUp, Award } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'

interface StreakCounterProps {
  currentStreak: number
  bestStreak: number
  lastTradeWin: boolean
}

export function StreakCounter({ currentStreak, bestStreak, lastTradeWin }: StreakCounterProps) {
  const [isAnimating, setIsAnimating] = useState(false)
  
  useEffect(() => {
    if (currentStreak > 0) {
      setIsAnimating(true)
      const timer = setTimeout(() => setIsAnimating(false), 500)
      return () => clearTimeout(timer)
    }
  }, [currentStreak])

  const getStreakTier = (streak: number) => {
    if (streak >= 15) return { label: 'ON FIRE', color: 'text-red-500', bg: 'bg-red-500/20' }
    if (streak >= 10) return { label: 'UNSTOPPABLE', color: 'text-orange-500', bg: 'bg-orange-500/20' }
    if (streak >= 5) return { label: 'HOT STREAK', color: 'text-amber-500', bg: 'bg-amber-500/20' }
    if (streak >= 3) return { label: 'WARMING UP', color: 'text-yellow-500', bg: 'bg-yellow-500/20' }
    return { label: 'ACTIVE', color: 'text-muted-foreground', bg: 'bg-muted' }
  }

  const tier = getStreakTier(currentStreak)
  const isNewRecord = currentStreak > 0 && currentStreak >= bestStreak

  return (
    <Card className={`bg-card border-border overflow-hidden ${isAnimating ? 'animate-pulse' : ''}`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${tier.bg}`}>
              <Flame className={`h-6 w-6 ${tier.color} ${currentStreak >= 5 ? 'animate-pulse' : ''}`} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold text-foreground">{currentStreak}</span>
                {isNewRecord && currentStreak > 0 && (
                  <span className="animate-bounce rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-500">
                    NEW RECORD!
                  </span>
                )}
              </div>
              <p className={`text-xs font-medium ${tier.color}`}>{tier.label}</p>
            </div>
          </div>
          
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Award className="h-3 w-3" />
              <span>Best: {bestStreak}</span>
            </div>
            <div className={`flex items-center gap-1 text-xs ${lastTradeWin ? 'text-emerald-500' : 'text-red-500'}`}>
              <TrendingUp className="h-3 w-3" />
              <span>Last: {lastTradeWin ? 'WIN' : 'LOSS'}</span>
            </div>
          </div>
        </div>

        {/* Streak visualization */}
        <div className="mt-3 flex gap-1">
          {Array.from({ length: 15 }).map((_, i) => (
            <div
              key={i}
              className={`h-2 flex-1 rounded-full transition-all ${
                i < currentStreak
                  ? i >= 10
                    ? 'bg-red-500'
                    : i >= 5
                      ? 'bg-orange-500'
                      : i >= 3
                        ? 'bg-amber-500'
                        : 'bg-emerald-500'
                  : 'bg-muted'
              }`}
            />
          ))}
        </div>
        <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
          <span>0</span>
          <span>5</span>
          <span>10</span>
          <span>15</span>
        </div>
      </CardContent>
    </Card>
  )
}
