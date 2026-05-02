'use client'

import { useState, useEffect } from 'react'
import { TickerBanner } from '@/components/wolf/ticker-banner'
import { Bell, Settings, RefreshCw, Wifi, WifiOff, TrendingUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import type { WolfStatus } from '@/lib/wolf-types'

interface HeaderProps {
  wolfStatus: WolfStatus
  onRefresh: () => void
  isConnected: boolean
}

export function Header({ wolfStatus, onRefresh, isConnected }: HeaderProps) {
  const [nyseTime, setNyseTime] = useState<string | null>(null)
  const [marketOpen, setMarketOpen] = useState(false)

  useEffect(() => {
    const updateTime = () => {
      const now = new Date()
      setNyseTime(now.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit' }))
      // NYSE: Mon–Fri 9:30–16:00 ET
      const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
      const day = et.getDay()
      const h = et.getHours(), m = et.getMinutes()
      const mins = h * 60 + m
      setMarketOpen(day >= 1 && day <= 5 && mins >= 570 && mins < 960)
    }
    updateTime()
    const interval = setInterval(updateTime, 1000)
    return () => clearInterval(interval)
  }, [])


  const getStatusColor = (status: WolfStatus['status']) => {
    switch (status) {
      case 'ACTIVE': return 'bg-emerald-500'
      case 'LEARNING': return 'bg-amber-500'
      case 'IDLE': return 'bg-slate-400'
      case 'ERROR': return 'bg-red-500'
      default: return 'bg-slate-400'
    }
  }

  const getStatusMessage = (status: WolfStatus['status']) => {
    switch (status) {
      case 'ACTIVE': return 'Predator mode — scanning markets'
      case 'LEARNING': return 'Sharpening the edge...'
      case 'IDLE': return 'Biding time...'
      case 'ERROR': return '⚠️ Wolf needs attention'
      default: return ''
    }
  }

  return (
    <div className="flex flex-col border-b border-border">
      {/* Scrolling ticker — always visible, full width */}
      <TickerBanner />

      {/* Main header */}
      <header className="bg-card px-4 lg:px-6 py-2.5 lg:py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="relative flex h-9 w-9 lg:h-12 lg:w-12 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500/20 to-amber-600/20 border border-amber-500/30">
                <span className="text-2xl lg:text-3xl">🐺</span>
                <span className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-card ${getStatusColor(wolfStatus.status)} ${wolfStatus.status === 'ACTIVE' ? 'animate-pulse' : ''}`} />
              </div>
              <div className="hidden sm:block">
                <h1 className="text-base lg:text-lg font-black text-foreground tracking-tight">
                  WOLF <span className="text-amber-500">OF ALL STREETS</span>
                </h1>
                <p className="text-[10px] text-muted-foreground italic">{getStatusMessage(wolfStatus.status)}</p>
              </div>
            </div>

            {/* Connection */}
            <div className="hidden sm:flex ml-2 items-center gap-2 rounded-full bg-secondary px-3 py-1">
              {isConnected ? (
                <>
                  <Wifi className="h-3 w-3 text-emerald-500 animate-pulse" />
                  <span className="text-xs text-emerald-500 font-bold tracking-wide">LIVE FEED</span>
                </>
              ) : (
                <>
                  <WifiOff className="h-3 w-3 text-red-500" />
                  <span className="text-xs text-red-400 font-bold tracking-wide">WOLF OFFLINE</span>
                </>
              )}
            </div>

            {/* NYSE Clock */}
            <div className="hidden md:flex items-center gap-2 rounded-full bg-secondary px-3 py-1">
              <span className="text-[10px] text-muted-foreground font-bold">NYSE</span>
              <span className="text-xs font-mono text-foreground">{nyseTime ?? '--:--:--'}</span>
            </div>
          </div>

          {/* Right side */}
          <div className="flex items-center gap-2">
            {/* Balance */}
            <div className="hidden sm:flex items-center gap-2 rounded-lg bg-secondary px-3 py-2 border border-amber-500/20">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Balance</span>
              <span className="font-mono text-sm font-black text-amber-400">
                ${(wolfStatus.balance ?? 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${wolfStatus.paperMode !== false ? 'bg-zinc-700 text-zinc-400' : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 animate-pulse'}`}>
                {wolfStatus.paperMode !== false ? 'PAPER' : 'LIVE'}
              </span>
            </div>

            {/* Win Rate */}
            <div className="hidden sm:flex items-center gap-2 rounded-lg bg-secondary px-3 py-2">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Win Rate</span>
              <Badge
                className={`font-mono text-sm font-bold ${wolfStatus.winRate >= 72
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50'
                  : 'bg-amber-500/20 text-amber-400 border border-amber-500/50'}`}
              >
                {wolfStatus.winRate.toFixed(1)}%
              </Badge>
              {wolfStatus.winRate >= 72 && (
                <span className="text-[10px] text-emerald-500 font-bold animate-pulse">🎯 TARGET</span>
              )}
            </div>

            {/* P&L */}
            <div className="hidden lg:flex items-center gap-2 rounded-lg bg-secondary px-3 py-2">
              <TrendingUp className={`h-3 w-3 ${wolfStatus.dailyPnL >= 0 ? 'text-emerald-500' : 'text-red-500'}`} />
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Today</span>
              <span className={`font-mono text-sm font-bold ${wolfStatus.dailyPnL >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {wolfStatus.dailyPnL >= 0 ? '+' : ''}${wolfStatus.dailyPnL.toFixed(2)}
              </span>
            </div>

            {/* Open Positions */}
            <div className="flex items-center gap-1.5 rounded-lg bg-secondary px-2.5 py-1.5 lg:px-3 lg:py-2">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Open</span>
              <Badge variant="outline" className="font-mono font-bold">{wolfStatus.openPositions}</Badge>
            </div>



            {/* Refresh */}
            <Button variant="ghost" size="icon" onClick={onRefresh} className="text-muted-foreground hover:text-amber-500">
              <RefreshCw className="h-4 w-4" />
            </Button>

            {/* Alerts */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="relative text-muted-foreground hover:text-foreground">
                  <Bell className="h-4 w-4" />
                  {wolfStatus.openPositions > 0 && (
                    <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-amber-500 text-[10px] font-black text-black">
                      {wolfStatus.openPositions}
                    </span>
                  )}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-80">
                <DropdownMenuItem className="flex flex-col items-start gap-1 py-3">
                  <div className="flex w-full items-center justify-between">
                    <span className="text-sm font-bold">🐺 Wolf Status</span>
                    <Badge className="bg-emerald-500/20 text-emerald-400 text-[10px]">{wolfStatus.status}</Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">{wolfStatus.openPositions} active positions · Paper mode</span>
                </DropdownMenuItem>
                <DropdownMenuItem className="flex flex-col items-start gap-1 py-3">
                  <div className="flex w-full items-center justify-between">
                    <span className="text-sm font-bold">📊 Performance</span>
                    <Badge className="bg-blue-500/20 text-blue-400 text-[10px]">Live</Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    WR: {wolfStatus.winRate.toFixed(1)}% · {wolfStatus.totalTrades} trades · Daily: ${wolfStatus.dailyPnL.toFixed(2)}
                  </span>
                </DropdownMenuItem>
                <DropdownMenuItem className="flex flex-col items-start gap-1 py-3">
                  <span className="text-sm font-bold">🎯 Target</span>
                  <span className="text-xs text-muted-foreground">72% win rate gate before live deployment</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-foreground">
              <Settings className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>
    </div>
  )
}
