'use client'

import { Trophy, Star, Flame, Target, Crown, Zap, TrendingUp, Award, Lock, Ship, Building2, Sparkles } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

interface Achievement {
  id: string
  title: string
  description: string
  icon: React.ReactNode
  unlocked: boolean
  progress?: number
  maxProgress?: number
  rarity: 'common' | 'rare' | 'epic' | 'legendary'
  unlockedAt?: Date
  wolfQuote?: string
}

interface AchievementsProps {
  winStreak: number
  totalProfit: number
  winRate: number
}

export function Achievements({ winStreak, totalProfit, winRate }: AchievementsProps) {
  const achievements: Achievement[] = [
    {
      id: 'first-blood',
      title: 'First Blood',
      description: 'Close your first winning trade',
      icon: <Target className="h-5 w-5" />,
      unlocked: true,
      rarity: 'common',
      unlockedAt: new Date('2024-01-15'),
      wolfQuote: '"Everybody wants to be a winner... now you are one."'
    },
    {
      id: 'wolf-pup',
      title: 'Wolf Pup',
      description: 'Achieve 5 consecutive winning trades',
      icon: <Flame className="h-5 w-5" />,
      unlocked: winStreak >= 5,
      progress: Math.min(winStreak, 5),
      maxProgress: 5,
      rarity: 'common',
      wolfQuote: '"The little wolf is learning to hunt."'
    },
    {
      id: 'sell-me-this-pen',
      title: 'Sell Me This Pen',
      description: 'Execute 100 total trades',
      icon: <Zap className="h-5 w-5" />,
      unlocked: true,
      rarity: 'rare',
      unlockedAt: new Date('2024-02-20'),
      wolfQuote: '"You create urgency. You create scarcity."'
    },
    {
      id: 'money-never-sleeps',
      title: 'Money Never Sleeps',
      description: 'Trade during pre-market hours',
      icon: <Star className="h-5 w-5" />,
      unlocked: true,
      rarity: 'rare',
      wolfQuote: '"While they sleep, we hunt."'
    },
    {
      id: 'stratton-oakmont',
      title: 'Stratton Oakmont',
      description: 'Achieve $10,000 in total profits',
      icon: <Building2 className="h-5 w-5" />,
      unlocked: totalProfit >= 10000,
      progress: Math.min(totalProfit, 10000),
      maxProgress: 10000,
      rarity: 'epic',
      wolfQuote: '"We\'re not going anywhere! We\'re here to stay!"'
    },
    {
      id: 'im-not-leaving',
      title: "I'm Not F***ing Leaving!",
      description: 'Maintain 72%+ win rate for 30 days',
      icon: <Award className="h-5 w-5" />,
      unlocked: winRate >= 72,
      progress: winRate >= 72 ? 30 : 18,
      maxProgress: 30,
      rarity: 'epic',
      wolfQuote: '"The show goes on. The wolf survives."'
    },
    {
      id: 'wolf-of-all-streets',
      title: 'Wolf of All Streets',
      description: 'Achieve 15 consecutive winning trades',
      icon: <Crown className="h-5 w-5" />,
      unlocked: winStreak >= 15,
      progress: Math.min(winStreak, 15),
      maxProgress: 15,
      rarity: 'legendary',
      wolfQuote: '"I\'ve been a poor man, and I\'ve been a rich man. I choose rich every f***ing time."'
    },
    {
      id: 'yacht-money',
      title: 'Yacht Money',
      description: 'Reach $100,000 in total profits',
      icon: <Ship className="h-5 w-5" />,
      unlocked: false,
      progress: totalProfit,
      maxProgress: 100000,
      rarity: 'legendary',
      wolfQuote: '"Was all this legal? Absolutely f***ing not."'
    },
  ]

  const getRarityStyles = (rarity: Achievement['rarity'], unlocked: boolean) => {
    if (!unlocked) return 'bg-muted/50 border-border text-muted-foreground'
    switch (rarity) {
      case 'common':
        return 'bg-slate-500/20 border-slate-500/50 text-slate-300'
      case 'rare':
        return 'bg-blue-500/20 border-blue-500/50 text-blue-300'
      case 'epic':
        return 'bg-purple-500/20 border-purple-500/50 text-purple-300'
      case 'legendary':
        return 'bg-gradient-to-r from-amber-500/20 to-yellow-500/20 border-amber-500/50 text-amber-300'
      default:
        return 'bg-muted border-border'
    }
  }

  const getRarityBadge = (rarity: Achievement['rarity']) => {
    switch (rarity) {
      case 'common':
        return <Badge variant="secondary" className="text-[10px]">Common</Badge>
      case 'rare':
        return <Badge className="bg-blue-500/20 text-blue-300 text-[10px]">Rare</Badge>
      case 'epic':
        return <Badge className="bg-purple-500/20 text-purple-300 text-[10px]">Epic</Badge>
      case 'legendary':
        return <Badge className="bg-amber-500/20 text-amber-300 text-[10px] flex items-center gap-1">
          <Sparkles className="h-2.5 w-2.5" />
          Legendary
        </Badge>
    }
  }

  const unlockedCount = achievements.filter(a => a.unlocked).length

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base font-medium">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500/20 to-yellow-500/20 border border-amber-500/30">
              <Trophy className="h-5 w-5 text-amber-500" />
            </div>
            Wall Street Trophies
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              {unlockedCount}/{achievements.length}
            </Badge>
            {unlockedCount === achievements.length && (
              <Badge className="bg-amber-500/20 text-amber-400 text-[10px]">
                LEGEND
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <TooltipProvider>
          <div className="grid grid-cols-4 gap-3">
            {achievements.map((achievement) => (
              <Tooltip key={achievement.id}>
                <TooltipTrigger asChild>
                  <div
                    className={`relative flex flex-col items-center justify-center rounded-lg border p-3 transition-all hover:scale-105 cursor-pointer ${getRarityStyles(achievement.rarity, achievement.unlocked)} ${achievement.rarity === 'legendary' && achievement.unlocked ? 'animate-pulse' : ''}`}
                  >
                    {!achievement.unlocked && (
                      <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-background/80 backdrop-blur-[1px]">
                        <Lock className="h-4 w-4 text-muted-foreground" />
                      </div>
                    )}
                    <div className={`${achievement.unlocked ? '' : 'opacity-30'}`}>
                      {achievement.icon}
                    </div>
                    {achievement.progress !== undefined && achievement.maxProgress && !achievement.unlocked && (
                      <Progress 
                        value={(achievement.progress / achievement.maxProgress) * 100} 
                        className="mt-2 h-1 w-full" 
                      />
                    )}
                    {achievement.unlocked && achievement.rarity === 'legendary' && (
                      <Sparkles className="absolute -top-1 -right-1 h-3 w-3 text-amber-400" />
                    )}
                  </div>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-[220px]">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-bold">{achievement.title}</p>
                      {getRarityBadge(achievement.rarity)}
                    </div>
                    <p className="text-xs text-muted-foreground">{achievement.description}</p>
                    {achievement.wolfQuote && (
                      <p className="text-[10px] text-amber-400/80 italic border-l-2 border-amber-500/30 pl-2">
                        {achievement.wolfQuote}
                      </p>
                    )}
                    {achievement.progress !== undefined && achievement.maxProgress && (
                      <div className="pt-1">
                        <Progress 
                          value={(achievement.progress / achievement.maxProgress) * 100} 
                          className="h-1.5" 
                        />
                        <p className="text-[10px] text-primary mt-1">
                          {achievement.progress.toLocaleString()}/{achievement.maxProgress.toLocaleString()}
                        </p>
                      </div>
                    )}
                    {achievement.unlocked && achievement.unlockedAt && (
                      <p className="text-[10px] text-emerald-400">
                        Unlocked: {achievement.unlockedAt.toLocaleDateString()}
                      </p>
                    )}
                  </div>
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        </TooltipProvider>
        
        {/* Achievement motivation */}
        <div className="mt-4 rounded-lg bg-secondary/50 p-3 text-center">
          <p className="text-[11px] text-muted-foreground italic">
            &quot;The only thing standing between you and your goal is the bullshit story you keep telling yourself.&quot;
          </p>
          <p className="text-[10px] text-amber-400/70 mt-1">- Jordan Belfort</p>
        </div>
      </CardContent>
    </Card>
  )
}
