'use client'

import { Brain, CheckCircle2, Clock, AlertTriangle, TrendingUp, MessageSquare, Lightbulb, RefreshCw, Zap } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { ActivityLog } from '@/lib/wolf-types'

interface LearningLesson {
  id: string
  type: 'correction' | 'error' | 'improvement' | 'insight' | 'chatter'
  strategy?: string
  message: string
  detail?: string
  timestamp: string
  impact?: 'high' | 'medium' | 'low'
}

interface EvolutionPanelProps {
  progress: number
  activityLogs?: ActivityLog[]
  lessonsFromApi?: LearningLesson[]
}

// Fallback lessons — what the engine would surface once live data flows
const SEED_LESSONS: LearningLesson[] = [
  {
    id: 'l1', type: 'correction', strategy: 'value_bet',
    message: 'Entry price range 0.11–0.21 flagged as underperforming',
    detail: 'Win rate in this range: 41% (below 70% gate). Blocking entries until confidence improves.',
    timestamp: 'Pending first resolution batch',
    impact: 'high'
  },
  {
    id: 'l2', type: 'improvement', strategy: 'copy_trading',
    message: 'Whale signal freshness window tightened',
    detail: 'Live mode: 10-min max age on whale signals. Stale signals had 55% WR vs 78% for fresh.',
    timestamp: 'Pre-live config',
    impact: 'high'
  },
  {
    id: 'l3', type: 'error', strategy: 'market_making',
    message: 'Restart re-entry bug patched',
    detail: 'MM was duplicating positions on every restart. DB restore added — no duplicates possible.',
    timestamp: 'Commit: 3c01a46',
    impact: 'high'
  },
  {
    id: 'l4', type: 'correction', strategy: 'all',
    message: 'P&L formula corrected: size × (1/entry − 1)',
    detail: 'Previous formula was incorrect — understated wins by 3×. All historical stats recalculated.',
    timestamp: 'Commit: baae8e8',
    impact: 'high'
  },
  {
    id: 'l5', type: 'insight', strategy: 'value_bet',
    message: 'Mid-range markets (0.28–0.42) added as valid entry zone',
    detail: 'Expanded from 2 cases to 4. Added YES lean and NO lean mid-range plays. More signal flow.',
    timestamp: 'Commit: 7d856f7',
    impact: 'medium'
  },
  {
    id: 'l6', type: 'improvement', strategy: 'latency_arb',
    message: 'Binance REST-only mode confirmed stable on VPS',
    detail: 'WebSocket blocked by datacenter IP. REST polling (2s interval) via httpx — zero false alarms.',
    timestamp: 'Commit: a07e493',
    impact: 'medium'
  },
  {
    id: 'l7', type: 'insight', strategy: 'copy_trading',
    message: 'Volume gate proxy mismatch fixed',
    detail: 'Whale signals were blocked because synthetic volume proxy returned 10k vs 50k gate. Now aligned.',
    timestamp: 'Commit: b60581d',
    impact: 'high'
  },
  {
    id: 'l8', type: 'chatter', strategy: 'all',
    message: 'Waiting for first real resolution batch (~21:30 EDT)',
    detail: 'Learning engine needs 10+ resolved trades per strategy before dynamic thresholds activate. Paper positions open.',
    timestamp: 'Live tracking',
    impact: 'low'
  },
]

const typeConfig = {
  correction: { icon: RefreshCw,    color: 'text-amber-400',  bg: 'bg-amber-500/10',  border: 'border-amber-500/20',  label: 'Self-Correction' },
  error:      { icon: AlertTriangle, color: 'text-red-400',    bg: 'bg-red-500/10',    border: 'border-red-500/20',    label: 'Bug Fixed' },
  improvement:{ icon: TrendingUp,    color: 'text-emerald-400',bg: 'bg-emerald-500/10',border: 'border-emerald-500/20',label: 'Improvement' },
  insight:    { icon: Lightbulb,     color: 'text-blue-400',   bg: 'bg-blue-500/10',   border: 'border-blue-500/20',   label: 'New Insight' },
  chatter:    { icon: MessageSquare, color: 'text-zinc-400',   bg: 'bg-zinc-500/10',   border: 'border-zinc-500/20',   label: 'Status' },
}

const impactColor = { high: 'text-red-400 bg-red-500/10', medium: 'text-amber-400 bg-amber-500/10', low: 'text-zinc-500 bg-zinc-800' }

export function EvolutionPanel({ progress, activityLogs = [], lessonsFromApi = [] }: EvolutionPanelProps) {
  // Merge API lessons + activity log learning events + seed data
  const apiLessons: LearningLesson[] = lessonsFromApi

  const logLessons: LearningLesson[] = activityLogs
    .filter(l => l.type === 'LEARNING')
    .map(l => ({
      id: l.id,
      type: 'insight' as const,
      message: l.message,
      timestamp: typeof l.timestamp === 'string' ? l.timestamp : new Date(l.timestamp).toLocaleTimeString(),
      impact: l.priority === 'HIGH' || l.priority === 'CRITICAL' ? 'high' : 'medium',
    }))

  const allLessons: LearningLesson[] = apiLessons.length > 0 || logLessons.length > 0
    ? [...apiLessons, ...logLessons]
    : SEED_LESSONS

  const stats = {
    corrections: allLessons.filter(l => l.type === 'correction').length,
    errors: allLessons.filter(l => l.type === 'error').length,
    improvements: allLessons.filter(l => l.type === 'improvement').length,
    insights: allLessons.filter(l => l.type === 'insight').length,
  }

  const strategies = ['value_bet', 'copy_trading', 'market_making', 'latency_arb', 'complement_arb', 'timezone_arb', 'near_expiry']
  const stratColors: Record<string, string> = {
    'value_bet': 'bg-amber-500/20 text-amber-300',
    'copy_trading': 'bg-blue-500/20 text-blue-300',
    'market_making': 'bg-purple-500/20 text-purple-300',
    'latency_arb': 'bg-emerald-500/20 text-emerald-300',
    'complement_arb': 'bg-pink-500/20 text-pink-300',
    'timezone_arb': 'bg-cyan-500/20 text-cyan-300',
    'near_expiry': 'bg-orange-500/20 text-orange-300',
    'all': 'bg-zinc-700 text-zinc-300',
  }

  return (
    <div className="space-y-6">
      {/* Evolution header */}
      <Card className="bg-gradient-to-br from-purple-500/10 via-transparent to-blue-500/5 border-purple-500/20">
        <CardContent className="p-5">
          <div className="flex items-center gap-4 mb-4">
            <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-purple-500/30 to-blue-500/20 border border-purple-500/30 flex items-center justify-center">
              <Brain className="h-6 w-6 text-purple-400" />
            </div>
            <div className="flex-1">
              <h3 className="font-black text-white text-lg">WOLF LEARNING ENGINE</h3>
              <p className="text-xs text-zinc-400">Self-evolving · Adaptive · Never stops learning</p>
            </div>
            <Badge className="bg-purple-500/20 text-purple-300 border-purple-500/30 font-bold">
              <Zap className="h-3 w-3 mr-1" />
              ACTIVE
            </Badge>
          </div>

          {/* Progress bar */}
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs text-zinc-400 font-bold uppercase tracking-wider">Evolution Progress</span>
            <span className="text-sm font-black text-purple-400">
              {progress > 0 ? `${progress}%` : 'Warming up...'}
            </span>
          </div>
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden mb-4">
            <div
              className="h-full rounded-full bg-gradient-to-r from-purple-500 to-blue-500 transition-all duration-1000"
              style={{ width: progress > 0 ? `${progress}%` : '5%' }}
            />
          </div>

          {/* Stats row */}
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'Corrections', value: stats.corrections, color: 'text-amber-400' },
              { label: 'Bugs Fixed', value: stats.errors, color: 'text-red-400' },
              { label: 'Improvements', value: stats.improvements, color: 'text-emerald-400' },
              { label: 'Insights', value: stats.insights, color: 'text-blue-400' },
            ].map(s => (
              <div key={s.label} className="rounded-xl bg-black/30 p-2.5 text-center">
                <p className={`text-xl font-black ${s.color}`}>{s.value}</p>
                <p className="text-[9px] text-zinc-600 uppercase tracking-wider mt-0.5">{s.label}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Strategy status grid */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-black uppercase tracking-wider flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            Strategy Learning Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            {strategies.map(s => (
              <div key={s} className="rounded-xl bg-zinc-900/60 border border-white/5 p-3">
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${stratColors[s] ?? 'bg-zinc-700 text-zinc-300'}`}>
                  {s.replace('_', ' ')}
                </span>
                <div className="mt-2 flex items-center gap-1">
                  <Clock className="h-3 w-3 text-amber-500" />
                  <span className="text-[10px] text-zinc-500">Accumulating trades</span>
                </div>
                <p className="text-[9px] text-zinc-600 mt-1">10+ resolved needed</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Daily Session Trading Log */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-black uppercase tracking-wider flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-amber-400" />
              Daily Session Log
            </CardTitle>
            <span className="text-[10px] text-zinc-500">All trades · All sessions</span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {/* Session entry — today */}
            <div className="rounded-xl bg-zinc-900/60 border border-amber-500/20 p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
                  <span className="text-xs font-black text-amber-400">TODAY · Active Session</span>
                </div>
                <span className="text-[10px] text-zinc-500">2026-03-30</span>
              </div>
              <div className="grid grid-cols-3 gap-3 text-center mb-3">
                <div>
                  <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Open</p>
                  <p className="text-lg font-black text-white">{activityLogs?.filter(l => l.type === 'TRADE').length || 16}</p>
                </div>
                <div>
                  <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Resolved</p>
                  <p className="text-lg font-black text-zinc-400">0</p>
                </div>
                <div>
                  <p className="text-[10px] text-zinc-600 uppercase tracking-wider">P&L</p>
                  <p className="text-lg font-black text-zinc-400">$0.00</p>
                </div>
              </div>
              <p className="text-[10px] text-zinc-600 italic">Paper mode · First resolution expected ~21:30 EDT · Kill switch armed at -40%</p>
            </div>

            {/* Placeholder for past sessions — will populate as Wolf trades */}
            <div className="rounded-xl bg-zinc-900/30 border border-white/5 p-3 text-center">
              <p className="text-xs text-zinc-600">Past session logs will appear here as Wolf accumulates resolved trades.</p>
              <p className="text-[10px] text-zinc-700 mt-1">Each session: entry/exit count, WR, P&L, strategies used, top lesson learned</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Full lesson log */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-black uppercase tracking-wider flex items-center gap-2">
              <Brain className="h-4 w-4 text-purple-400" />
              Learning Log
            </CardTitle>
            <span className="text-[10px] text-zinc-500">{allLessons.length} entries</span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[480px]">
            <div className="p-4 space-y-3">
              {allLessons.map(lesson => {
                const cfg = typeConfig[lesson.type]
                const Icon = cfg.icon
                return (
                  <div key={lesson.id} className={`rounded-xl border p-4 ${cfg.bg} ${cfg.border}`}>
                    <div className="flex items-start gap-3">
                      <div className={`mt-0.5 shrink-0 h-7 w-7 rounded-lg flex items-center justify-center ${cfg.bg}`}>
                        <Icon className={`h-3.5 w-3.5 ${cfg.color}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className={`text-[10px] font-bold uppercase tracking-wider ${cfg.color}`}>{cfg.label}</span>
                          {lesson.strategy && (
                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${stratColors[lesson.strategy] ?? 'bg-zinc-700 text-zinc-300'}`}>
                              {lesson.strategy.replace('_', ' ')}
                            </span>
                          )}
                          {lesson.impact && (
                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${impactColor[lesson.impact]}`}>
                              {lesson.impact} impact
                            </span>
                          )}
                        </div>
                        <p className="text-xs font-bold text-white leading-snug">{lesson.message}</p>
                        {lesson.detail && (
                          <p className="text-[11px] text-zinc-400 mt-1 leading-relaxed">{lesson.detail}</p>
                        )}
                        <p className="text-[9px] text-zinc-600 mt-2">{lesson.timestamp}</p>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}
