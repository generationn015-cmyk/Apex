'use client'

import { LayoutDashboard, Crosshair, BarChart3, ShieldCheck, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'

interface MobileNavProps {
  activeTab: string
  onTabChange: (tab: string) => void
}

const items = [
  { id: 'dashboard', label: 'Floor',    icon: LayoutDashboard },
  { id: 'trades',    label: 'Hunts',    icon: Crosshair },
  { id: 'analytics', label: 'Intel',    icon: BarChart3 },
  { id: 'guardian',  label: 'Guardian', icon: ShieldCheck },
  { id: 'settings',  label: 'Config',   icon: Settings },
]

export function MobileNav({ activeTab, onTabChange }: MobileNavProps) {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 lg:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
    >
      {/* Top border glow */}
      <div className="h-px w-full bg-gradient-to-r from-transparent via-amber-500/20 to-transparent" />

      <div className="flex items-center justify-around bg-[#0d0d1a]/95 backdrop-blur-xl px-1 py-2">
        {items.map(item => {
          const Icon = item.icon
          const active = activeTab === item.id

          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className="relative flex flex-col items-center gap-1 px-3 py-2 transition-transform duration-150 active:scale-95"
            >
              {/* Active pill background */}
              {active && (
                <span className="absolute inset-0 rounded-xl bg-amber-500/10" />
              )}

              <Icon
                className={cn(
                  'relative h-5 w-5 transition-colors duration-200',
                  active ? 'text-amber-400' : 'text-zinc-600'
                )}
                strokeWidth={active ? 2.5 : 1.8}
              />
              <span
                className={cn(
                  'relative text-[10px] font-bold tracking-wide transition-colors duration-200',
                  active ? 'text-amber-400' : 'text-zinc-600'
                )}
              >
                {item.label}
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
