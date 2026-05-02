'use client'

import { Line, LineChart, CartesianGrid, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { DdubIndexData } from '@/lib/wolf-types'

interface DdubIndexChartProps {
  data: DdubIndexData[]
}

export function DdubIndexChart({ data }: DdubIndexChartProps) {
  const latestData = data[data.length - 1]
  
  const getSignalColor = (signal: DdubIndexData['signal']) => {
    switch (signal) {
      case 'BUY':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
      case 'SELL':
        return 'bg-red-500/20 text-red-400 border-red-500/30'
      case 'HOLD':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30'
      default:
        return 'bg-muted text-muted-foreground'
    }
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-medium">D-Dub Index</CardTitle>
            <p className="text-xs text-muted-foreground">24h Signal Analysis</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-lg font-semibold text-foreground">{latestData?.value.toFixed(1)}</p>
              <p className="text-xs text-muted-foreground">Current</p>
            </div>
            <Badge variant="outline" className={getSignalColor(latestData?.signal ?? 'HOLD')}>
              {latestData?.signal ?? 'HOLD'}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-[200px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="ddubGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="oklch(0.6 0.18 280)" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="oklch(0.6 0.18 280)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.28 0.01 250)" vertical={false} />
              <XAxis 
                dataKey="timestamp" 
                stroke="oklch(0.5 0 0)" 
                fontSize={10} 
                tickLine={false} 
                axisLine={false}
                interval={3}
              />
              <YAxis 
                stroke="oklch(0.5 0 0)" 
                fontSize={10} 
                tickLine={false} 
                axisLine={false}
                domain={[30, 80]}
              />
              <ReferenceLine y={65} stroke="oklch(0.65 0.2 145)" strokeDasharray="3 3" strokeOpacity={0.5} />
              <ReferenceLine y={45} stroke="oklch(0.55 0.22 25)" strokeDasharray="3 3" strokeOpacity={0.5} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'oklch(0.18 0.01 250)',
                  border: '1px solid oklch(0.28 0.01 250)',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
                labelStyle={{ color: 'oklch(0.6 0 0)' }}
                formatter={(value: number, name: string) => [value.toFixed(2), 'D-Dub Index']}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="oklch(0.6 0.18 280)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: 'oklch(0.6 0.18 280)' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-3 flex items-center justify-between text-xs">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              <span className="text-muted-foreground">Buy Zone (65+)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-red-500" />
              <span className="text-muted-foreground">Sell Zone (45-)</span>
            </div>
          </div>
          <span className="text-muted-foreground">Signal Strength: {latestData?.strength ?? 0}%</span>
        </div>
      </CardContent>
    </Card>
  )
}
