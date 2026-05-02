import { NextResponse } from 'next/server'

// Static file map — files live in /public/sounds/ and are served directly
// This route exists only for legacy compatibility; clients should use /sounds/*.mp3 directly
const CLIP_MAP: Record<string, string> = {
  'not-leaving':    '/sounds/not-leaving.mp3',
  'poverty':        '/sounds/poverty.mp3',
  'show-goes-on':   '/sounds/show-goes-on.mp3',
  'pen':            '/sounds/pen.mp3',
  'unlock-buy':     '/sounds/buy.mp3',
  'unlock-die':     '/sounds/die.mp3',
  'client-buy-die': '/sounds/client-buy-die.mp3',
}

export async function GET(
  request: Request,
  { params }: { params: { clip: string } }
) {
  const path = CLIP_MAP[params.clip]
  if (!path) return new NextResponse('Not found', { status: 404 })
  // Redirect to static file — faster, no serverless timeout, no upstream dependency
  return NextResponse.redirect(new URL(path, request.url))
}
