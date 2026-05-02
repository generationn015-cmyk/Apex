import { NextRequest, NextResponse } from 'next/server'
import { updateStatus, updatePerformance, updateMarketData, addDdubDataPoint, addActivityLog, updateLearning, addPnlDataPoint, updateGuardian } from '@/lib/wolf-store'

export async function POST(request: NextRequest) {
  const apiKey = request.headers.get('x-wolf-api-key') || request.headers.get('authorization')?.replace('Bearer ', '')
  const expectedKey = process.env.WOLF_API_KEY
  if (expectedKey && apiKey !== expectedKey) return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 })

  try {
    const body = await request.json()
    const event = body.event

    if (event === 'alert') {
      await addActivityLog({ id: `log-${Date.now()}`, type: body.type || 'ALERT', message: body.message || 'Wolf alert', timestamp: new Date().toISOString(), priority: body.priority || 'medium' })
      return NextResponse.json({ success: true, data: { event, processed: true }, timestamp: new Date().toISOString() })
    }

    if (event === 'learning_update') {
      const learning = body.data?.learning || { progress: body.progress || 0, modulesCompleted: body.modulesCompleted || 0, totalModules: body.totalModules || 5, currentModule: body.currentModule || '', accuracy: body.accuracy || 0, lessonsLearned: body.lessonsLearned || [] }
      await updateLearning(learning)
      if (body.data?.pnlData) { for (const p of body.data.pnlData) await addPnlDataPoint(p) }
      await addActivityLog({ id: `log-${Date.now()}`, type: 'SYSTEM', message: `Received learning_update from OpenClaw`, timestamp: new Date().toISOString(), priority: 'low' })
      return NextResponse.json({ success: true, data: { event, processed: true }, timestamp: new Date().toISOString() })
    }

    if (event === 'guardian_update') {
      const g = body.data ?? {}
      await updateGuardian({
        scan_count: g.scan_count ?? 0,
        healthy: g.healthy ?? true,
        error_count: g.error_count ?? 0,
        errors: g.errors ?? [],
        last_scan_ts: g.last_scan_ts ?? (Date.now() / 1000),
      })
      return NextResponse.json({ success: true, data: { event, processed: true }, timestamp: new Date().toISOString() })
    }

    return NextResponse.json({ success: false, error: `Unknown event type: ${event}`, timestamp: new Date().toISOString() }, { status: 400 })
  } catch {
    return NextResponse.json({ success: false, error: 'Invalid request body' }, { status: 400 })
  }
}
