'use client'

import {
  LayoutDashboard,
  TrendingUp,
  Brain,
  Settings,
  History,
  BarChart3,
  Shield,
  Zap,
  Building2,
  Crosshair,
  ShieldCheck
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface SidebarProps {
  activeTab: string
  onTabChange: (tab: string) => void
}

const navItems = [
  { id: 'dashboard', label: 'The Floor', icon: LayoutDashboard, subtitle: 'Mission Control' },
  { id: 'trades', label: 'Hunt Log', icon: Crosshair, subtitle: 'Active Positions' },
  { id: 'analytics', label: 'Intel', icon: BarChart3, subtitle: 'Performance Data' },
  { id: 'learning', label: 'Evolution', icon: Brain, subtitle: 'Self-Improving' },
  { id: 'history', label: 'Ledger', icon: History, subtitle: 'Closed Trades' },
  { id: 'risk', label: 'Risk Desk', icon: Shield, subtitle: 'Kill Switch' },
  { id: 'automation', label: 'Autopilot', icon: Zap, subtitle: 'Strategies' },
  { id: 'guardian', label: 'Guardian', icon: ShieldCheck, subtitle: 'Error Monitor' },
  { id: 'settings', label: 'Configure', icon: Settings, subtitle: 'Data & Settings' },
]

export function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  return (
    <aside className="hidden lg:flex h-full w-16 flex-col border-r border-border bg-sidebar lg:w-56">
      {/* Stratton Oakmont badge */}
      <div className="hidden lg:block border-b border-sidebar-border p-3">
        <div className="flex items-center gap-2 px-2">
          <Building2 className="h-5 w-5 text-amber-500 shrink-0" />
          <div>
            <p className="text-xs font-black text-sidebar-foreground tracking-widest">STRATTON</p>
            <p className="text-[10px] text-amber-500/60 italic">Trading Division</p>
          </div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1 p-2 lg:p-3">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = activeTab === item.id

          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all',
                isActive
                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/20 shadow-sm'
                  : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground border border-transparent'
              )}
            >
              <Icon className={cn('h-5 w-5 shrink-0', isActive ? 'text-amber-400' : '')} />
              <div className="hidden lg:block text-left">
                <span className={cn('block font-bold', isActive ? 'text-amber-400' : '')}>{item.label}</span>
                {isActive && (
                  <span className="text-[10px] text-sidebar-foreground/50">{item.subtitle}</span>
                )}
              </div>
            </button>
          )
        })}
      </nav>

      {/* Wolf status at bottom */}
      <div className="border-t border-sidebar-border p-3">
        <div className="flex items-center gap-3 rounded-lg bg-gradient-to-r from-amber-500/10 to-transparent border border-amber-500/20 p-3 relative overflow-hidden">
          <div className="absolute inset-0 opacity-5 pointer-events-none">
            <div className="absolute -right-4 -top-4 h-16 w-16 rounded-full border-4 border-amber-500" />
          </div>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500/20 to-amber-600/20 border border-amber-500/30">
            <span className="text-xl">🐺</span>
          </div>
          <div className="hidden lg:block relative z-10">
            <p className="text-xs font-black text-amber-400 tracking-wider">WOLF v2.5</p>
            <p className="text-[10px] text-sidebar-foreground/50 italic">&quot;The hunt never stops&quot;</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
