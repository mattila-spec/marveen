import { spawn } from 'node:child_process'
import { execFileSync } from 'node:child_process'
import { join } from 'node:path'
import { MAIN_AGENT_ID, PROJECT_ROOT } from '../config.js'
import { logger } from '../logger.js'

const GATE = join(PROJECT_ROOT, 'scripts', 'self-healing-attempt-gate.py')
const INCIDENT = 'main-channels'

export function claimMainRecovery(actor: string): string | null {
  try {
    const raw = execFileSync('python3', [GATE, 'claim', INCIDENT, actor], { encoding: 'utf8', timeout: 5000 })
    const parsed = JSON.parse(raw) as { allowed?: boolean; attempt_id?: string }
    if (parsed.allowed !== true || !parsed.attempt_id) throw new Error('gate claim returned no attempt id')
    return parsed.attempt_id
  } catch (err) {
    logger.error({ actor, err }, 'self-healing gate denied recovery; STOP and escalate')
    return null
  }
}

export function failMainRecovery(actor: string, attemptId: string, reason: string): void {
  try {
    execFileSync('python3', [GATE, 'fail', INCIDENT, attemptId, reason], { encoding: 'utf8', timeout: 5000 })
  } catch (err) {
    logger.error({ actor, err }, 'self-healing gate could not record failed recovery')
  }
}

export function watchMainRecovery(actor: string, attemptId: string): void {
  try {
    const child = spawn('python3', [GATE, 'watch', INCIDENT, attemptId, `${MAIN_AGENT_ID}-channels`], {
      detached: true,
      stdio: 'ignore',
      env: process.env,
    })
    child.unref()
  } catch (err) {
    logger.error({ actor, err }, 'self-healing gate health watcher could not start; attempt will fail closed on lease expiry')
  }
}
