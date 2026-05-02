'use client'

import { Area, AreaChart, Bar, BarChart, CartesianGrid, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { PnLDataPoint } from '@/lib/wolf-types'

interface PnLChartProps {
  data: PnLDataPoint[]
}

export function PnLChart({ data }: PnLChartProps) {
  const latestCumulative = data[data.length - 1]?.cumulative ?? 0

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-medium">P&L Performance</CardTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Cumulative:</span>
            <span className={`text-sm font-semibold ${latestCumulative >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {latestCumulative >= 0 ? '+' : ''}${latestCumulative.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="cumulative" className="w-full">
          <TabsList className="mb-4 grid w-full max-w-xs grid-cols-2">
            <TabsTrigger value="cumulative">Cumulative</TabsTrigger>
            <TabsTrigger value="daily">Daily</TabsTrigger>
          </TabsList>
          
          <TabsContent value="cumulative" className="mt-0">
            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="oklch(0.65 0.2 145)" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="oklch(0.65 0.2 145)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.28 0.01 250)" vertical={false} />
                  <XAxis 
                    dataKey="date" 
                    stroke="oklch(0.5 0 0)" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis 
                    stroke="oklch(0.5 0 0)" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    tickFormatter={(value) => `$${value}`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'oklch(0.18 0.01 250)',
                      border: '1px solid oklch(0.28 0.01 250)',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    labelStyle={{ color: 'oklch(0.6 0 0)' }}
                    formatter={(value: number) => [`$${value.toFixed(2)}`, 'Cumulative P&L']}
                  />
                  <Area
                    type="monotone"
                    dataKey="cumulative"
                    stroke="oklch(0.65 0.2 145)"
                    strokeWidth={2}
                    fill="url(#pnlGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </TabsContent>
          
          <TabsContent value="daily" className="mt-0">
            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.28 0.01 250)" vertical={false} />
                  <XAxis 
                    dataKey="date" 
                    stroke="oklch(0.5 0 0)" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis 
                    stroke="oklch(0.5 0 0)" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    tickFormatter={(value) => `$${value}`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'oklch(0.18 0.01 250)',
                      border: '1px solid oklch(0.28 0.01 250)',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    labelStyle={{ color: 'oklch(0.6 0 0)' }}
                    formatter={(value: number) => [`$${value.toFixed(2)}`, 'Daily P&L']}
                  />
                  <Bar
                    dataKey="pnl"
                    fill="oklch(0.65 0.2 145)"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}
