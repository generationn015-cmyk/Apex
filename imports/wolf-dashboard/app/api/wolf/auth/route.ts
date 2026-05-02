import { NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'
import crypto from 'crypto'

// Server-side password auth — password set once in Vercel env as WOLF_SITE_PASSWORD
// Works on every device, every browser, no localStorage dependency

const SESSION_COOKIE = 'wolf_session'
const SESSION_MAX_AGE = 60 * 60 * 24 * 30 // 30 days

function makeToken(): string {
  return crypto.randomBytes(32).toString('hex')
}

// In-memory token store (survives within serverless function lifetime — Vercel)
// For true persistence across cold starts, this uses a fixed HMAC instead
function signToken(token: string): string {
  const secret = process.env.WOLF_SITE_PASSWORD ?? 'wolf-default'
  return crypto.createHmac('sha256', secret).update(token).digest('hex')
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const submitted = (body.password ?? '').trim()
    const expected = (process.env.WOLF_SITE_PASSWORD ?? '').trim()

    if (!expected) {
      // No password configured — auto-unlock
      const token = makeToken()
      const response = NextResponse.json({ ok: true, configured: false })
      response.cookies.set(SESSION_COOKIE, `${token}.${signToken(token)}`, {
        httpOnly: true,
        sameSite: 'lax',
        maxAge: SESSION_MAX_AGE,
        path: '/',
      })
      return response
    }

    // Constant-time comparison
    const submittedBuf = Buffer.from(submitted)
    const expectedBuf  = Buffer.from(expected)
    const match =
      submittedBuf.length === expectedBuf.length &&
      crypto.timingSafeEqual(submittedBuf, expectedBuf)

    if (!match) {
      return NextResponse.json({ ok: false, error: 'Access denied' }, { status: 401 })
    }

    const token = makeToken()
    const signed = `${token}.${signToken(token)}`
    const response = NextResponse.json({ ok: true, configured: true })
    response.cookies.set(SESSION_COOKIE, signed, {
      httpOnly: true,
      sameSite: 'lax',
      maxAge: SESSION_MAX_AGE,
      path: '/',
    })
    return response
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid request' }, { status: 400 })
  }
}

export async function GET(request: NextRequest) {
  // Check if current session is valid
  const cookieStore = await cookies()
  const cookie = cookieStore.get(SESSION_COOKIE)?.value ?? ''
  const configured = !!(process.env.WOLF_SITE_PASSWORD ?? '').trim()

  if (!configured) return NextResponse.json({ authenticated: true, configured: false })
  if (!cookie) return NextResponse.json({ authenticated: false, configured: true })

  const [token, sig] = cookie.split('.')
  if (!token || !sig) return NextResponse.json({ authenticated: false, configured: true })

  const expected = signToken(token)
  const valid = crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))
  return NextResponse.json({ authenticated: valid, configured: true })
}

export async function DELETE(request: NextRequest) {
  // Logout
  const response = NextResponse.json({ ok: true })
  response.cookies.set(SESSION_COOKIE, '', { maxAge: 0, path: '/' })
  return response
}
