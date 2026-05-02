'use client'

import { Brain, CheckCircle2, Clock, AlertCircle, Sparkles, GraduationCap } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'

interface LearningPanelProps {
  progress: number
}

// Wolf of Wall Street themed module names
const learningModules = [
  { name: 'Predatory Pattern Recognition', status: 'complete', accuracy: 94, quote: 'See the setup before they do' },
  { name: 'Risk Appetite Calibration', status: 'complete', accuracy: 89, quote: 'Fortune favors the prepared' },
  { name: 'Market Sentiment Analysis', status: 'active', accuracy: 78, quote: 'Read the room, own the room' },
  { name: 'Position Sizing Mastery', status: 'pending', accuracy: null, quote: 'Size matters in this game' },
]

// Wolf-themed self-correction messages
const recentLearnings = [
  { 
    text: 'Tightened stop-loss parameters by 2.5%', 
    time: '32m ago',
    wolf: 'The wolf protects the pack\'s capital'
  },
  { 
    text: 'Adjusted momentum threshold for ES futures', 
    time: '1h ago',
    wolf: 'Patience is a predator\'s virtue'
  },
  { 
    text: 'Updated volatility scaling factors', 
    time: '2h ago',
    wolf: 'Adapt or get eaten'
  },
  { 
    text: 'Refined entry signal confidence weighting', 
    time: '4h ago',
    wolf: 'Precision over aggression'
  },
]

export function LearningPanel({ progress }: LearningPanelProps) {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'complete':
        return <CheckCircle2 className="h-4 w-4 text-emerald-400" />
      case 'active':
        return <Clock className="h-4 w-4 text-amber-400 animate-pulse" />
      case 'pending':
        return <AlertCircle className="h-4 w-4 text-slate-400" />
      default:
        return null
    }
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'complete':
        return 'Mastered'
      case 'active':
        return 'In Training'
      case 'pending':
        return 'Queued'
      default:
        return ''
    }
  }

  const getLearningPhrase = () => {
    if (progress >= 90) return '"I\'m not f***ing leaving until I\'m the best."'
    if (progress >= 70) return '"Every day I\'m getting sharper."'
    if (progress >= 50) return '"The grind separates wolves from sheep."'
    return '"Started from the bottom, watch me rise."'
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-purple-500/30">
              <Brain className="h-5 w-5 text-purple-400" />
            </div>
            <div>
              <CardTitle className="text-base font-medium">Wolf Learning Engine</CardTitle>
              <p className="text-[10px] text-muted-foreground italic">Self-evolving intelligence</p>
            </div>
          </div>
          <Badge variant="outline" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
            <Sparkles className="mr-1 h-3 w-3" />
            Active
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Overall Progress */}
        <div className="rounded-lg bg-secondary/50 p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium text-foreground flex items-center gap-2">
              <GraduationCap className="h-4 w-4 text-amber-500" />
              Evolution Progress
            </span>
            <span className="text-lg font-bold text-primary">{progress}%</span>
          </div>
          <Progress value={progress} className="h-2.5" />
          <p className="mt-2 text-[10px] text-muted-foreground italic text-center">
            {getLearningPhrase()}
          </p>
        </div>

        {/* Learning Modules */}
        <div>
          <h4 className="mb-3 text-sm font-medium text-foreground flex items-center gap-2">
            Training Modules
            <Badge variant="outline" className="text-[10px]">
              {learningModules.filter(m => m.status === 'complete').length}/{learningModules.length}
            </Badge>
          </h4>
          <div className="space-y-2">
            {learningModules.map((module, index) => (
              <div
                key={index}
                className="group flex items-center justify-between rounded-lg bg-secondary/50 px-3 py-2.5 transition-all hover:bg-secondary"
              >
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  {getStatusIcon(module.status)}
                  <div className="min-w-0">
                    <span className="text-sm text-foreground block truncate">{module.name}</span>
                    <span className="text-[10px] text-muted-foreground/70 italic hidden group-hover:block">
                      {module.quote}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {module.accuracy !== null && (
                    <span className={`text-xs font-medium ${module.accuracy >= 90 ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {module.accuracy}%
                    </span>
                  )}
                  <Badge variant="secondary" className="text-[9px] px-1.5">
                    {getStatusLabel(module.status)}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Self-Corrections */}
        <div>
          <h4 className="mb-3 text-sm font-medium text-foreground">Self-Correction Log</h4>
          <div className="space-y-2">
            {recentLearnings.map((learning, index) => (
              <div
                key={index}
                className="group relative border-l-2 border-accent/50 pl-3 py-1 hover:border-accent transition-colors"
              >
                <div className="flex items-start justify-between">
                  <span className="text-xs text-foreground/90">{learning.text}</span>
                  <span className="shrink-0 text-[10px] text-muted-foreground/60 ml-2">{learning.time}</span>
                </div>
                <span className="text-[9px] text-amber-400/60 italic opacity-0 group-hover:opacity-100 transition-opacity">
                  {learning.wolf}
                </span>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
