import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { runInNewContext } from 'node:vm'
import ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'
import { PROJECT_ROOT } from '../config.js'
const source = readFileSync(join(PROJECT_ROOT, 'src/web/channel-monitor.ts'), 'utf8')
const ast = ts.createSourceFile('monitor.ts', source, ts.ScriptTarget.Latest, true)
function scenario(name: string, allowed = true, restartOk = true) {
  const fn = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === name)!
  const code = ts.transpileModule('(' + fn.getText(ast).replace('export ', '') + ')', { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
  const end = vi.fn(), claim = vi.fn(() => allowed ? 'owned-attempt' : null)
  const restart = vi.fn(() => ({ ok: restartOk, error: restartOk ? undefined : 'fixture failure' }))
  const watch = vi.fn(), fail = vi.fn()
  const run = runInNewContext(code, {
    process: { env: { MARVEEN_AGENT_BACKEND: 'codex' } },
    getProvider: () => ({ type: 'telegram' }), getMainAgentProvider: () => 'telegram',
    beginMainRespawn: () => end, claimMainRecovery: claim, watchMainRecovery: watch, failMainRecovery: fail,
    restartCodexChannels: restart, logger: { error: vi.fn() },
  }) as (...args: any[]) => any
  return { run, claim, restart, watch, fail, end }
}
describe('actual Codex recovery functions use one persistent incident budget', () => {
  it.each(['resumeMarveenSession', 'respawnMainSessionFresh', 'respawnMarveenSessionFresh'])('%s never launches a Claude fallback on Codex', async name => {
    const f = scenario(name); await f.run()
    expect(f.claim).toHaveBeenCalledOnce(); expect(f.restart).toHaveBeenCalledOnce()
    expect(f.watch).toHaveBeenCalledWith(expect.any(String), 'owned-attempt')
    expect(f.fail).not.toHaveBeenCalled(); expect(f.end).toHaveBeenCalledOnce()
  })
  it.each(['resumeMarveenSession', 'respawnMarveenSessionFresh'])('%s refuses a denied claim without replacing the pane', async name => {
    const f = scenario(name, false); expect(await f.run()).toBe(false)
    expect(f.restart).not.toHaveBeenCalled(); expect(f.watch).not.toHaveBeenCalled()
    expect(f.end).toHaveBeenCalledOnce()
  })
  it('the scheduled restart surfaces denial and still releases its scheduling hold', () => {
    const f = scenario('respawnMainSessionFresh', false)
    expect(() => f.run()).toThrow(/shared recovery gate denied/)
    expect(f.restart).not.toHaveBeenCalled(); expect(f.end).toHaveBeenCalledOnce()
  })
  it('automatic Codex hard restart is denied before touching the process', () => {
    const f = scenario('hardRestartMarveenChannels', false)
    expect(f.run({ automatic: true, actor: 'monitor' }).ok).toBe(false)
    expect(f.restart).not.toHaveBeenCalled()
    expect(f.end).toHaveBeenCalledOnce()
  })
  it('successful automatic Codex restart gets one verification watcher', () => {
    const f = scenario('hardRestartMarveenChannels')
    expect(f.run({ automatic: true, actor: 'monitor' }).ok).toBe(true)
    expect(f.claim).toHaveBeenCalledOnce(); expect(f.watch).toHaveBeenCalledWith('monitor', 'owned-attempt')
    expect(f.end).toHaveBeenCalledOnce()
  })
  it('failed automatic Codex restart consumes a failure instead of claiming health', () => {
    const f = scenario('hardRestartMarveenChannels', true, false)
    expect(f.run({ automatic: true }).ok).toBe(false)
    expect(f.fail).toHaveBeenCalledOnce(); expect(f.watch).not.toHaveBeenCalled()
  })
  it('a manual restart does not claim or reset the automatic incident budget', () => {
    const f = scenario('hardRestartMarveenChannels', false)
    expect(f.run().ok).toBe(true); expect(f.claim).not.toHaveBeenCalled()
    expect(f.watch).not.toHaveBeenCalled(); expect(f.fail).not.toHaveBeenCalled()
  })
})


describe('Codex absent-pane recovery preserves parent ownership', () => {
  function actual(name: string, context: Record<string, unknown>) {
    const fn = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === name)!
    const code = ts.transpileModule('(' + fn.getText(ast).replace('export ', '') + ')', { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
    return runInNewContext(code, context) as (...args: any[]) => any
  }
  it.each(['started', 'grace', 'spawn-failed'])('missing pane delegates to the canonical launcher: %s', created => {
    const create = vi.fn(() => created)
    const restart = actual('restartCodexChannels', {
      join: (...parts: string[]) => parts.join('/'), PROJECT_ROOT: '/fixture',
      process: { env: {} }, shSingleQuote: (s: string) => s,
      tmuxBin: () => '/fake/tmux', MAIN_CHANNELS_SESSION: 'fixture-channels', exactTmuxTarget: (s: string) => '=' + s + ':',
      execFileSync: () => { throw new Error("can't find pane") },
      createMainChannelsSession: create, writeRespawnStamp: vi.fn(),
    })
    expect(restart('parent-owned-id').ok).toBe(created !== 'spawn-failed')
    expect(create).toHaveBeenCalledWith('parent-owned-id')
  })
  it('the canonical launcher forwards its owned attempt to the child environment', () => {
    const spawn = vi.fn((..._args: any[]) => ({ unref: vi.fn() }))
    const create = actual('createMainChannelsSession', {
      marveenLastSessionCreate: 0, MAIN_SESSION_CREATE_GRACE_MS: 1000,
      CHANNELS_SCRIPT: '/fixture/scripts/channels.sh', PROJECT_ROOT: '/fixture', MAIN_CHANNELS_SESSION: 'fixture-channels',
      existsSync: () => true, runningChannelsSupervisors: () => [],
      supervisorWait: null, supervisorWaitDecision: () => ({ state: null, verdict: 'start' }),
      spawn, process: { env: { MARVEEN_AGENT_BACKEND: 'codex' } },
      writeRespawnStamp: vi.fn(), sendRoutineAlert: vi.fn(), logger: { warn: vi.fn(), error: vi.fn() },
    })
    expect(create('parent-owned-id')).toBe('started')
    expect(spawn.mock.calls[0][2].env).toEqual({ MARVEEN_AGENT_BACKEND: 'codex', MARVEEN_SELF_HEALING_ATTEMPT_ID: 'parent-owned-id' })
  })
})
