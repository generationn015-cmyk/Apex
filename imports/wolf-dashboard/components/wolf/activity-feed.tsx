'use client'

import { Activity, TrendingUp, Brain, AlertTriangle, Server, Sparkles } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import type { ActivityLog } from '@/lib/wolf-types'

interface ActivityFeedProps {
  logs: ActivityLog[]
}

// Wolf of Wall Street themed messages based on log type
const getThemedSubtext = (log: ActivityLog) => {
  if (log.type === 'TRADE' && log.message.toLowerCase().includes('win')) {
    return '"The only thing standing between you and your goal is the story you keep telling yourself."'
  }
  if (log.type === 'TRADE' && log.message.toLowerCase().includes('loss')) {
    return '"Fall down seven times, stand up eight."'
  }
  if (log.type === 'LEARNING') {
    return '"Winners use words that say must and will. Losers use words that say should and try."'
  }
  if (log.type === 'ALERT') {
    return '"Act as if! Act as if you\'re a wealthy man already."'
  }
  if (log.priority === 'CRITICAL') {
    return '"I\'m not f***ing leaving!"'
  }
  return null
}

export function ActivityFeed({ logs }: ActivityFeedProps) {
  const getIcon = (type: ActivityLog['type']) => {
    switch (type) {
      case 'TRADE':
        return <TrendingUp className="h-4 w-4" />
      case 'ANALYSIS':
        return <Activity className="h-4 w-4" />
      case 'LEARNING':
        return <Brain className="h-4 w-4" />
      case 'ALERT':
        return <AlertTriangle className="h-4 w-4" />
      case 'SYSTEM':
        return <Server className="h-4 w-4" />
      default:
        return <Activity className="h-4 w-4" />
    }
  }

  const getIconColor = (type: ActivityLog['type']) => {
    switch (type) {
      case 'TRADE':
        return 'text-emerald-400 bg-emerald-500/10'
      case 'ANALYSIS':
        return 'text-blue-400 bg-blue-500/10'
      case 'LEARNING':
        return 'text-purple-400 bg-purple-500/10'
      case 'ALERT':
        return 'text-amber-400 bg-amber-500/10'
      case 'SYSTEM':
        return 'text-slate-400 bg-slate-500/10'
      default:
        return 'text-muted-foreground bg-muted'
    }
  }

  const getPriorityIndicator = (priority: ActivityLog['priority']) => {
    switch (priority) {
      case 'CRITICAL':
        return 'border-l-red-500'
      case 'HIGH':
        return 'border-l-amber-500'
      case 'MEDIUM':
        return 'border-l-blue-500'
      case 'LOW':
        return 'border-l-slate-500'
      default:
        return 'border-l-slate-500'
    }
  }

  const getPriorityBadge = (priority: ActivityLog['priority']) => {
    switch (priority) {
      case 'CRITICAL':
        return <Badge className="ml-2 bg-red-500/20 text-red-400 text-[9px] px-1.5 py-0">URGENT</Badge>
      case 'HIGH':
        return <Badge className="ml-2 bg-amber-500/20 text-amber-400 text-[9px] px-1.5 py-0">HOT</Badge>
      default:
        return null
    }
  }

  const formatTime = (date: Date | string) => {
    if (typeof date === 'string') { const d = new Date(date); if (!isNaN(d.getTime())) date = d; else return 'just now' }
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / (1000 * 60))
    const hours = Math.floor(minutes / 60)
    
    if (hours > 0) {
      return `${hours}h ago`
    }
    if (minutes > 0) {
      return `${minutes}m ago`
    }
    return 'Just now'
  }

  return (
    <Card className="bg-card border-border h-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-medium flex items-center gap-2">
            The Trading Floor
            <Sparkles className="h-4 w-4 text-amber-500" />
          </CardTitle>
          <div className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500 status-pulse" />
            <span className="text-xs text-muted-foreground">Live from Wall St</span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[350px] px-4">
          <div className="space-y-3 py-2">
            {logs.map((log) => {
              const themedSubtext = getThemedSubtext(log)
              return (
                <div
                  key={log.id}
                  className={`flex items-start gap-3 rounded-lg border-l-2 bg-secondary/30 p-3 transition-all hover:bg-secondary/50 ${getPriorityIndicator(log.priority)}`}
                >
                  <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${getIconColor(log.type)}`}>
                    {getIcon(log.type)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium uppercase text-muted-foreground flex items-center">
                        {log.type}
                        {getPriorityBadge(log.priority)}
                      </span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {formatTime(log.timestamp)}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-foreground">{log.message}</p>
                    {themedSubtext && (
                      <p className="mt-1 text-[10px] text-muted-foreground/70 italic">
                        {themedSubtext}
                      </p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
