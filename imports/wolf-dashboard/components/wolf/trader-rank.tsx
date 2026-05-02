'use client'

import { Crown, Star, TrendingUp, ChevronUp, Briefcase, Building2, Ship, Sparkles } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'

interface TraderRankProps {
  totalProfit: number
  totalTrades: number
  winRate: number
}

type RankTier = {
  name: string
  icon: React.ReactNode
  minProfit: number
  color: string
  bgColor: string
  borderColor: string
  title: string
  wolfQuote: string
}

const RANK_TIERS: RankTier[] = [
  {
    name: 'Street Hustler',
    icon: <Briefcase className="h-5 w-5" />,
    minProfit: 0,
    color: 'text-slate-400',
    bgColor: 'bg-slate-500/20',
    borderColor: 'border-slate-500/50',
    title: 'Just getting started',
    wolfQuote: '"Every master was once a disaster."'
  },
  {
    name: 'Junior Broker',
    icon: <TrendingUp className="h-5 w-5" />,
    minProfit: 1000,
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/20',
    borderColor: 'border-emerald-500/50',
    title: 'Making moves',
    wolfQuote: '"The money is just a gateway to a new life."'
  },
  {
    name: 'Senior Broker',
    icon: <Star className="h-5 w-5" />,
    minProfit: 5000,
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/20',
    borderColor: 'border-blue-500/50',
    title: 'Climbing the ladder',
    wolfQuote: '"Winners use words that say must and will."'
  },
  {
    name: 'Vice President',
    icon: <Building2 className="h-5 w-5" />,
    minProfit: 10000,
    color: 'text-purple-400',
    bgColor: 'bg-purple-500/20',
    borderColor: 'border-purple-500/50',
    title: 'Corner office secured',
    wolfQuote: '"Act as if you\'re a wealthy man already."'
  },
  {
    name: 'Managing Partner',
    icon: <Crown className="h-5 w-5" />,
    minProfit: 25000,
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/20',
    borderColor: 'border-amber-500/50',
    title: 'Stratton Oakmont Elite',
    wolfQuote: '"I want you to deal with your problems by becoming rich."'
  },
  {
    name: 'Wolf of All Streets',
    icon: <Ship className="h-5 w-5" />,
    minProfit: 100000,
    color: 'text-amber-300',
    bgColor: 'bg-gradient-to-r from-amber-500/20 to-yellow-500/20',
    borderColor: 'border-amber-400',
    title: 'Legend Status Achieved',
    wolfQuote: '"I\'ve been a poor man, and I\'ve been a rich man. I choose rich every f***ing time."'
  },
]

export function TraderRank({ totalProfit, totalTrades, winRate }: TraderRankProps) {
  const getCurrentRank = () => {
    for (let i = RANK_TIERS.length - 1; i >= 0; i--) {
      if (totalProfit >= RANK_TIERS[i].minProfit) {
        return { rank: RANK_TIERS[i], index: i }
      }
    }
    return { rank: RANK_TIERS[0], index: 0 }
  }

  const { rank: currentRank, index: rankIndex } = getCurrentRank()
  const nextRank = RANK_TIERS[rankIndex + 1]
  
  const progressToNext = nextRank
    ? ((totalProfit - currentRank.minProfit) / (nextRank.minProfit - currentRank.minProfit)) * 100
    : 100

  const isMaxRank = !nextRank

  return (
    <Card className={`bg-card border-2 ${currentRank.borderColor} ${isMaxRank ? 'relative overflow-hidden' : ''}`}>
      {/* Legendary glow effect for max rank */}
      {isMaxRank && (
        <div className="absolute inset-0 bg-gradient-to-r from-amber-500/5 via-yellow-500/10 to-amber-500/5 animate-pulse" />
      )}
      
      <CardHeader className="pb-3 relative">
        <CardTitle className="flex items-center justify-between text-base font-medium">
          <span className="flex items-center gap-2">
            <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${currentRank.bgColor} border ${currentRank.borderColor}`}>
              <span className={currentRank.color}>{currentRank.icon}</span>
            </div>
            <div>
              <span className="block">Trader Rank</span>
              <span className="text-[10px] text-muted-foreground font-normal">Stratton Oakmont Career Ladder</span>
            </div>
          </span>
          <Badge className={`${currentRank.bgColor} ${currentRank.color} border-0 flex items-center gap-1`}>
            {isMaxRank && <Sparkles className="h-3 w-3" />}
            Level {rankIndex + 1}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 relative">
        <div className="text-center py-2">
          <h3 className={`text-2xl font-bold ${currentRank.color} ${isMaxRank ? 'gold-shimmer' : ''}`}>
            {currentRank.name}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">{currentRank.title}</p>
          <p className="text-[10px] text-amber-400/70 italic mt-2 px-4">
            {currentRank.wolfQuote}
          </p>
        </div>

        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="rounded-lg bg-secondary p-2.5 border border-border/50">
            <p className="text-lg font-bold text-foreground">${(totalProfit / 1000).toFixed(1)}k</p>
            <p className="text-[10px] text-muted-foreground">Total Profit</p>
          </div>
          <div className="rounded-lg bg-secondary p-2.5 border border-border/50">
            <p className="text-lg font-bold text-foreground">{totalTrades}</p>
            <p className="text-[10px] text-muted-foreground">Trades</p>
          </div>
          <div className="rounded-lg bg-secondary p-2.5 border border-border/50">
            <p className={`text-lg font-bold ${winRate >= 72 ? 'text-emerald-400' : 'text-amber-400'}`}>
              {winRate.toFixed(1)}%
            </p>
            <p className="text-[10px] text-muted-foreground">Win Rate</p>
          </div>
        </div>

        {nextRank && (
          <div className="space-y-2 bg-secondary/30 rounded-lg p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground flex items-center gap-1">
                Next: <span className={nextRank.color}>{nextRank.name}</span>
              </span>
              <span className={nextRank.color}>
                ${(nextRank.minProfit - totalProfit).toLocaleString()} to go
              </span>
            </div>
            <div className="relative">
              <Progress value={progressToNext} className="h-2.5" />
              <ChevronUp 
                className={`absolute -top-1 h-4 w-4 ${nextRank.color} transition-all drop-shadow-lg`}
                style={{ left: `${Math.min(progressToNext, 95)}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>{currentRank.name}</span>
              <span>{nextRank.name}</span>
            </div>
          </div>
        )}

        {isMaxRank && (
          <div className="rounded-lg border border-amber-500/30 bg-gradient-to-r from-amber-500/10 to-yellow-500/10 p-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <Sparkles className="h-4 w-4 text-amber-400" />
              <p className="text-sm font-bold text-amber-400">Maximum Rank Achieved!</p>
              <Sparkles className="h-4 w-4 text-amber-400" />
            </div>
            <p className="text-xs text-muted-foreground">You are the Wolf of All Streets</p>
            <p className="text-[10px] text-amber-400/60 italic mt-2">
              &quot;There&apos;s no nobility in poverty. I&apos;ve been a rich man and I&apos;ve been a poor man. And I choose rich every f***ing time.&quot;
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
