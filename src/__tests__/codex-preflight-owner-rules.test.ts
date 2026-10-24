import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { expect, it } from 'vitest'
import { PROJECT_ROOT } from '../config.js'
it('Codex preflight rejects a missing canonical source before spawning app-server', () => {
  const root = mkdtempSync(join(tmpdir(), 'codex-preflight-owner-'))
  try {
    mkdirSync(join(root, 'scripts'))
    cpSync(join(PROJECT_ROOT, 'scripts/codex-channels.mjs'), join(root, 'scripts/codex-channels.mjs'))
    cpSync(join(PROJECT_ROOT, 'scripts/lib'), join(root, 'scripts/lib'), { recursive: true })
    cpSync(join(PROJECT_ROOT, 'dist'), join(root, 'dist'), { recursive: true })
    cpSync(join(PROJECT_ROOT, 'package.json'), join(root, 'package.json'))
    symlinkSync(join(PROJECT_ROOT, 'node_modules'), join(root, 'node_modules'), 'dir')
    const started = join(root, 'app-server-started')
    const fake = join(root, 'fake-codex.cjs')
    writeFileSync(fake, '#!/usr/bin/env node\nrequire("node:fs").writeFileSync(process.env.FIXTURE_STARTED, "started")\n', { mode: 0o755 })
    const control = spawnSync(fake, [], { env: { ...process.env, FIXTURE_STARTED: started }, encoding: 'utf8' })
    expect(control.status, control.stderr).toBe(0)
    expect(existsSync(started)).toBe(true)
    rmSync(started)
    const out = spawnSync(process.execPath, [join(root, 'scripts/codex-channels.mjs'), '--preflight'], {
      cwd: root, env: { ...process.env, MARVEEN_CODEX_BIN: fake, FIXTURE_STARTED: started }, encoding: 'utf8', timeout: 15000,
    })
    expect(out.status).not.toBe(0)
    expect(out.stderr).toContain('Required owner rules')
    expect(existsSync(started)).toBe(false)
  } finally { rmSync(root, { recursive: true, force: true }) }
})
