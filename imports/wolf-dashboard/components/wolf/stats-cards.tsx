'use client'

import { useState } from 'react'
import { TrendingUp, TrendingDown, Activity, Target, Brain, DollarSign, Briefcase, Zap } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import type { WolfStatus } from '@/lib/wolf-types'

interface StatsCardsProps {
  wolfStatus: WolfStatus
}

const getPerformanceLabel = (value: number) => {
  if (value >= 5000) return '🛥️ Yacht money!'
  if (value >= 2000) return '💰 Stratton approved'
  if (value >= 1000) return '📈 Money never sleeps'
  if (value >= 500) return '🐺 The hunt pays off'
  if (value >= 100) return '✅ Staying sharp'
  if (value > 0) return '👍 In the green'
  if (value === 0) return '⏳ Waiting to resolve'
  if (value >= -200) return '📉 Temporary setback'
  return '🔄 Recalibrating...'
}

const getWinRateLabel = (rate: number) => {
  if (rate >= 80) return '🦅 Elite Predator'
  if (rate >= 72) return '🎯 Gate Broken'
  if (rate >= 65) return '🐺 Pack Leader'
  if (rate >= 50) return '🔪 Lone Wolf'
  if (rate === 0) return '⏳ First hunt pending'
  return '📚 Pup in Training'
}

const getRiskLabel = (risk: WolfStatus['riskLevel']) => {
  switch (risk) {
    case 'LOW': return '🛡️ Playing it safe'
    case 'MEDIUM': return '⚡ Calculated risk'
    case 'HIGH': return '🔥 Fortune favors bold'
    default: return ''
  }
}

const getRiskColor = (risk: WolfStatus['riskLevel']) => {
  switch (risk) {
    case 'LOW': return 'text-emerald-400'
    case 'MEDIUM': return 'text-amber-400'
    case 'HIGH': return 'text-red-400'
    default: return 'text-muted-foreground'
  }
}

export function StatsCards({ wolfStatus }: StatsCardsProps) {
  const [hoveredCard, setHoveredCard] = useState<string | null>(null)

  const formatCurrency = (value: number) => {
    const sign = value >= 0 ? '+' : ''
    return `${sign}$${Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">

      {/* Daily P&L */}
      <Card
        className="rounded-2xl bg-[#161624] border border-white/5 transition-all hover:border-amber-500/20 hover:shadow-lg hover:shadow-amber-500/5 cursor-default"
        onMouseEnter={() => setHoveredCard('daily')}
        onMouseLeave={() => setHoveredCard(null)}
      >
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Daily P&L</span>
            {wolfStatus.dailyPnL >= 0
              ? <TrendingUp className="h-4 w-4 text-emerald-500" />
              : <TrendingDown className="h-4 w-4 text-red-500" />}
          </div>
          <p className={`mt-2 text-xl font-black font-mono ${wolfStatus.dailyPnL >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatCurrency(wolfStatus.dailyPnL)}
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground italic h-4">
            {hoveredCard === 'daily' ? getPerformanceLabel(wolfStatus.dailyPnL) : 'Today'}
          </p>
        </CardContent>
      </Card>

      {/* Weekly P&L */}
      <Card
        className="rounded-2xl bg-[#161624] border border-white/5 transition-all hover:border-amber-500/20 hover:shadow-lg hover:shadow-amber-500/5 cursor-default"
        onMouseEnter={() => setHoveredCard('weekly')}
        onMouseLeave={() => setHoveredCard(null)}
      >
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Weekly P&L</span>
            {wolfStatus.weeklyPnL >= 0
              ? <TrendingUp className="h-4 w-4 text-emerald-500" />
              : <TrendingDown className="h-4 w-4 text-red-500" />}
          </div>
          <p className={`mt-2 text-xl font-black font-mono ${wolfStatus.weeklyPnL >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatCurrency(wolfStatus.weeklyPnL)}
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground italic h-4">
            {hoveredCard === 'weekly' ? getPerformanceLabel(wolfStatus.weeklyPnL) : 'This Week'}
          </p>
        </CardContent>
      </Card>

      {/* Monthly P&L */}
      <Card
        className="rounded-2xl bg-[#161624] border border-white/5 transition-all hover:border-amber-500/20 hover:shadow-lg hover:shadow-amber-500/5 cursor-default"
        onMouseEnter={() => setHoveredCard('monthly')}
        onMouseLeave={() => setHoveredCard(null)}
      >
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Monthly P&L</span>
            {wolfStatus.monthlyPnL >= 0
              ? <DollarSign className="h-4 w-4 text-emerald-500" />
              : <TrendingDown className="h-4 w-4 text-red-500" />}
          </div>
          <p className={`mt-2 text-xl font-black font-mono ${wolfStatus.monthlyPnL >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatCurrency(wolfStatus.monthlyPnL)}
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground italic h-4">
            {hoveredCard === 'monthly' ? getPerformanceLabel(wolfStatus.monthlyPnL) : 'This Month'}
          </p>
        </CardContent>
      </Card>

      {/* Total Trades */}
      <Card
        className="rounded-2xl bg-[#161624] border border-white/5 transition-all hover:border-amber-500/20 hover:shadow-lg hover:shadow-amber-500/5 cursor-default"
        onMouseEnter={() => setHoveredCard('trades')}
        onMouseLeave={() => setHoveredCard(null)}
      >
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Trades</span>
            <Briefcase className="h-4 w-4 text-amber-400" />
          </div>
          <p className="mt-2 text-xl font-black font-mono text-foreground">{wolfStatus.totalTrades}</p>
          <p className="mt-1 text-[10px] text-muted-foreground italic h-4">
            {hoveredCard === 'trades'
              ? wolfStatus.totalTrades >= 100 ? '🖊️ Sell me this pen!' : wolfStatus.totalTrades === 0 ? '⏳ First kill incoming' : '🏗️ Building the empire'
              : 'Lifetime'}
          </p>
        </CardContent>
      </Card>

      {/* Win Rate */}
      <Card
        className={`bg-card border-border transition-all hover:border-amber-500/30 hover:shadow-lg hover:shadow-amber-500/5 cursor-default ${wolfStatus.winRate >= 72 ? 'ring-1 ring-emerald-500/40' : ''}`}
        onMouseEnter={() => setHoveredCard('winrate')}
        onMouseLeave={() => setHoveredCard(null)}
      >
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Win Rate</span>
            <Target className={`h-4 w-4 ${wolfStatus.winRate >= 72 ? 'text-emerald-500' : 'text-amber-400'}`} />
          </div>
          <p className={`mt-2 text-xl font-black font-mono ${wolfStatus.winRate >= 72 ? 'text-emerald-400' : wolfStatus.winRate === 0 ? 'text-muted-foreground' : 'text-amber-400'}`}>
            {wolfStatus.winRate === 0 ? '—' : `${wolfStatus.winRate.toFixed(1)}%`}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <Progress value={wolfStatus.winRate} className="h-1.5 flex-1" />
            <span className="text-[10px] text-muted-foreground shrink-0">72%</span>
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground italic h-4">
            {hoveredCard === 'winrate' ? getWinRateLabel(wolfStatus.winRate) : 'Target: 72%'}
          </p>
        </CardContent>
      </Card>

      {/* Balance — the money that matters */}
      <Card
        className={`rounded-2xl border transition-all hover:shadow-lg cursor-default ${
          (wolfStatus.balance ?? 100) >= 100
            ? 'bg-[#0d1a12] border-emerald-500/20 hover:border-emerald-500/40 hover:shadow-emerald-500/10'
            : 'bg-[#1a0d0d] border-red-500/20 hover:border-red-500/40 hover:shadow-red-500/10'
        }`}
        onMouseEnter={() => setHoveredCard('balance')}
        onMouseLeave={() => setHoveredCard(null)}
      >
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Balance</span>
            <DollarSign className={`h-4 w-4 ${(wolfStatus.balance ?? 100) >= 100 ? 'text-emerald-400' : 'text-red-400'}`} />
          </div>
          <p className={`mt-2 text-xl font-black font-mono ${(wolfStatus.balance ?? 100) >= 100 ? 'text-emerald-300' : 'text-red-400'}`}>
            ${(wolfStatus.balance ?? 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <div className="mt-2 flex items-center gap-1">
            <Activity className={`h-3 w-3 ${wolfStatus.openPositions > 0 ? 'text-amber-400 animate-pulse' : 'text-muted-foreground'}`} />
            <span className="text-[10px] text-muted-foreground">
              {wolfStatus.openPositions} open · {wolfStatus.paperMode !== false ? 'PAPER' : 'LIVE'}
            </span>
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground italic h-4">
            {hoveredCard === 'balance'
              ? ((wolfStatus.balance ?? 100) >= 100 ? '💰 In the green' : '📉 Recalibrating...')
              : `Started $100`}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
