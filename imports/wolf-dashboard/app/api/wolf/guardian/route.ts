import { NextResponse } from 'next/server'
import { getFullState } from '@/lib/wolf-store'

// Guardian status endpoint — reads from wolf-store (VPS pushes guardian state via webhook)
export async function GET() {
  try {
    const state = await getFullState()
    const g = (state as any).guardian ?? {
      scan_count: 0,
      healthy: true,
      error_count: 0,
      errors: [],
      last_scan_ts: null,
    }

    const now = Date.now() / 1000
    const age = g.last_scan_ts ? Math.round(now - g.last_scan_ts) : null
    // stale = store was cold-started and has never received a guardian push
    const stale = g.scan_count === 0 && g.last_scan_ts === null

    return NextResponse.json({
      success: true,
      data: {
        scan_count: g.scan_count,
        healthy: g.healthy,
        error_count: g.error_count,
        errors: g.errors ?? [],
        last_scan_age_s: age,
        last_scan_ts: g.last_scan_ts,
        stale,
      },
      timestamp: new Date().toISOString(),
    })
  } catch (e) {
    return NextResponse.json({
      success: true,
      data: { scan_count: 0, healthy: true, error_count: 0, errors: [], last_scan_age_s: null },
      timestamp: new Date().toISOString(),
    })
  }
}
