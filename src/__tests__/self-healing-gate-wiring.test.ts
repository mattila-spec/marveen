import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const ROOT = join(import.meta.dirname, '..', '..')
const read = (path: string) => readFileSync(join(ROOT, path), 'utf8')

describe('persistent main-channel recovery gate wiring', () => {
  it('the systemd template claims before startup and verifies after startup', () => {
    const unit = read('scripts/systemd/marveen-channels.service')
    expect(unit).toMatch(/ExecStartPre=.*self-healing-attempt-gate\.py claim main-channels systemd-supervisor/)
    expect(unit).toMatch(/ExecStartPost=.*self-healing-attempt-gate\.py watch-active main-channels systemd-supervisor/)
    expect(unit).toMatch(/ExecStopPost=.*self-healing-attempt-gate\.py fail-active main-channels systemd-supervisor/)
    expect(unit).toMatch(/^TimeoutStartSec=360$/m)
  })

  it('shell recovery actors use the same incident key and persist failed outcomes', () => {
    const watchdog = read('scripts/channel-watchdog.sh')
    const modal = read('scripts/stuck-modal-guard.sh')
    expect(watchdog).toMatch(/claim "\$INCIDENT" channel-watchdog/)
    expect(watchdog).toMatch(/watch "\$INCIDENT" "\$attempt_id"/)
    expect(watchdog).toMatch(/fail "\$INCIDENT" "\$attempt_id"/)
    expect(modal).toMatch(/claim main-channels stuck-modal-guard/)
    expect(modal).toMatch(/watch main-channels "\$attempt_id"/)
    expect(modal).toMatch(/fail main-channels "\$attempt_id"/)
  })

  it('automatic main-session restart call sites opt into the durable gate', () => {
    const automaticCallers = [
      'src/web/channel-monitor.ts',
      'src/web/context-guard-runner.ts',
      'src/web/inbound-probe.ts',
      'src/web/model-fallback-runner.ts',
      'src/web/reauth-healer.ts',
    ]
    for (const path of automaticCallers) {
      expect(read(path), path).toMatch(/hardRestartMarveenChannels\(\{\s*automatic:\s*true/)
    }
    const monitor = read('src/web/channel-monitor.ts')
    expect(monitor).toMatch(/const actor = 'channel-mcp-soft-reconnect'[\s\S]*?claimMainRecovery\(actor\)/)
    expect(monitor).toMatch(/const actor = 'channel-monitor-fresh-respawn'[\s\S]*?claimMainRecovery\(actor\)/)
    expect(monitor).toMatch(/const actor = 'channel-down-cascade-resume'[\s\S]*?claimMainRecovery\(actor\)/)
  })

  it('channels.sh leaves pure resolver modes outside the gate and verifies parent attempts', () => {
    const sh = read('scripts/channels.sh')
    const resolver = sh.indexOf('if [ "${1:-}" = "--resolve-main-model" ]')
    const claim = sh.indexOf('_gate_claim=')
    expect(resolver).toBeGreaterThan(-1)
    expect(claim).toBeGreaterThan(resolver)
    expect(sh).toMatch(/MARVEEN_SELF_HEALING_ATTEMPT_ID/)
    expect(sh).toMatch(/parent recovery attempt is not active/)
  })
})
