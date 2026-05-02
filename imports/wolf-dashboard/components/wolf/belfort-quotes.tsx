'use client'

import { useState, useEffect, useCallback } from 'react'
import { Quote, RefreshCw, Volume2, VolumeX, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface BelfortQuotesProps {
  dailyPnL?: number
  winRate?: number
  winStreak?: number
}

// Categorized quotes for context-aware display
const WOLF_QUOTES = {
  general: [
    {
      quote: "The only thing standing between you and your goal is the story you keep telling yourself.",
      context: "Stay focused on the charts"
    },
    {
      quote: "Winners use words that say 'must' and 'will'.",
      context: "72% win rate incoming"
    },
    {
      quote: "Act as if! Act as if you're a wealthy man, rich already.",
      context: "Trade with confidence"
    },
    {
      quote: "Without action, the best intentions in the world are nothing more than that: intentions.",
      context: "Execute the trades"
    },
    {
      quote: "Sell me this pen.",
      context: "Classic negotiation"
    },
    {
      quote: "The wolf of Wall Street? No, I'm the Wolf of ALL Streets.",
      context: "We trade everything"
    },
  ],
  winning: [
    {
      quote: "I've been a poor man, and I've been a rich man. And I choose rich every f***ing time.",
      context: "Keep stacking those profits"
    },
    {
      quote: "There is no nobility in poverty.",
      context: "Let Wolf hunt for gains"
    },
    {
      quote: "The easiest way to make money is to create something of such value that everybody wants.",
      context: "The strategy is working"
    },
    {
      quote: "My name is Jordan Belfort. The year I turned 26, I made 49 million dollars.",
      context: "Numbers don't lie"
    },
    {
      quote: "Money is the oxygen of capitalism and I wanna breathe more than any man alive.",
      context: "Keep the momentum going"
    },
    {
      quote: "Stratton Oakmont is America. We're not going anywhere!",
      context: "Dominating the market"
    },
  ],
  losing: [
    {
      quote: "I'm not f***ing leaving! The show goes on!",
      context: "Diamond hands activated"
    },
    {
      quote: "Every person around here works their f***ing ass off to get here.",
      context: "Temporary setback"
    },
    {
      quote: "The only way you can achieve something is by being completely devoted to it.",
      context: "Trust the process"
    },
    {
      quote: "Fall down seven times, stand up eight.",
      context: "Recalibrating strategy"
    },
    {
      quote: "I want you to deal with your problems by becoming rich!",
      context: "Turn it around"
    },
  ],
  streaking: [
    {
      quote: "Was all this legal? Absolutely f***ing not. But we were making too much money to care.",
      context: "Unstoppable streak"
    },
    {
      quote: "I am not gonna die sober! And neither is this win streak!",
      context: "On fire right now"
    },
    {
      quote: "The only limit is the one you set yourself.",
      context: "Keep the streak alive"
    },
    {
      quote: "Risk is what separates the good from the great.",
      context: "Calculated aggression"
    },
  ]
}

const ALL_QUOTES = [
  ...WOLF_QUOTES.general,
  ...WOLF_QUOTES.winning,
  ...WOLF_QUOTES.losing,
  ...WOLF_QUOTES.streaking,
]

export function BelfortQuotes({ dailyPnL = 0, winRate = 0, winStreak = 0 }: BelfortQuotesProps) {
  const [currentQuote, setCurrentQuote] = useState(WOLF_QUOTES.general[0])
  const [isChanging, setIsChanging] = useState(false)
  const [mounted, setMounted] = useState(false)

  const getContextualQuote = useCallback(() => {
    let pool = WOLF_QUOTES.general
    
    if (winStreak >= 5) {
      pool = WOLF_QUOTES.streaking
    } else if (dailyPnL >= 500) {
      pool = WOLF_QUOTES.winning
    } else if (dailyPnL < -200) {
      pool = WOLF_QUOTES.losing
    } else {
      // Mix of all quotes
      pool = ALL_QUOTES
    }
    
    return pool[Math.floor(Math.random() * pool.length)]
  }, [dailyPnL, winStreak])

  const getRandomQuote = useCallback(() => {
    setIsChanging(true)
    setTimeout(() => {
      setCurrentQuote(getContextualQuote())
      setIsChanging(false)
    }, 300)
  }, [getContextualQuote])

  useEffect(() => {
    setMounted(true)
    setCurrentQuote(getContextualQuote())
  }, [getContextualQuote])

  useEffect(() => {
    if (!mounted) return
    const interval = setInterval(getRandomQuote, 30000)
    return () => clearInterval(interval)
  }, [mounted, getRandomQuote])

  const isOnFire = winStreak >= 5 || dailyPnL >= 1000

  return (
    <div className={`relative overflow-hidden rounded-lg border ${isOnFire ? 'border-amber-500/40' : 'border-amber-500/20'} bg-gradient-to-r from-amber-500/5 via-transparent to-amber-500/5 p-4`}>
      {/* Decorative elements */}
      <div className="absolute -right-4 -top-4 text-amber-500/10">
        <Quote className="h-24 w-24 rotate-180" />
      </div>
      
      {/* Fire effect for hot streaks */}
      {isOnFire && (
        <div className="absolute top-2 right-2">
          <Sparkles className="h-4 w-4 text-amber-400 animate-pulse" />
        </div>
      )}
      
      <div className={`transition-all duration-300 ${isChanging ? 'opacity-0 translate-y-2' : 'opacity-100 translate-y-0'}`}>
        <p className="relative z-10 text-sm font-medium italic text-foreground leading-relaxed">
          &quot;{currentQuote.quote}&quot;
        </p>
        <div className="mt-3 flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-amber-500 flex items-center gap-1">
              {isOnFire && <Sparkles className="h-3 w-3" />}
              Wolf of All Streets
            </p>
            <p className="text-[10px] text-muted-foreground">{currentQuote.context}</p>
          </div>
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={getRandomQuote}
            className="h-7 w-7 text-muted-foreground hover:text-amber-500 hover:bg-amber-500/10"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      
      {/* NYC Skyline silhouette */}
      <div className="absolute bottom-0 left-0 right-0 h-8 opacity-5 overflow-hidden">
        <div className="flex items-end justify-center h-full gap-1">
          {[4, 8, 6, 12, 5, 9, 7, 14, 6, 10, 5, 8, 11, 4, 7, 9, 6].map((h, i) => (
            <div key={i} className="bg-foreground" style={{ width: '6px', height: `${h * 2}px` }} />
          ))}
        </div>
      </div>
    </div>
  )
}
