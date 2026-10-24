import { spawnSync } from 'node:child_process'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { runInNewContext } from 'node:vm'
import ts from 'typescript'
import { MAIN_AGENT_ID, PROJECT_ROOT } from '../config.js'
import { ensureOwnerOperatingRulesSection } from '../web/agent-scaffold.js'
import { readCanonicalOwnerRules, workerDeveloperInstructions } from '../../scripts/lib/codex-owner-instructions.mjs'
const roots: string[] = []
const begin = '<!-- BEGIN GENERATED: owner-operating-rules -->'
const end = '<!-- END GENERATED: owner-operating-rules -->'
const rules = readFileSync(join(PROJECT_ROOT, 'AGENTS.md'), 'utf8')
function fixture(name = MAIN_AGENT_ID) {
  const root = mkdtempSync(join(tmpdir(), 'owner-rules-')); roots.push(root)
  const agentsBaseDir = join(root, 'agents')
  const dir = name === MAIN_AGENT_ID ? root : join(agentsBaseDir, name)
  mkdirSync(dir, { recursive: true })
  const prompt = join(dir, 'CLAUDE.md')
  writeFileSync(join(root, 'AGENTS.md'), rules)
  writeFileSync(prompt, '# Existing persona\nKeep this.\n')
  return { root, prompt, paths: { projectRoot: root, agentsBaseDir } }
}
afterEach(() => { for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true }) })
function assertBlock(prompt: string, source = rules) {
  const text = readFileSync(prompt, 'utf8')
  expect(text.split(begin)).toHaveLength(2)
  expect(text.split(end)).toHaveLength(2)
  expect(text).toContain(begin + '\n' + source + end)
  expect(text).toContain('# Existing persona\nKeep this.')
}
describe('canonical owner rules synchronization', () => {
  it.each([MAIN_AGENT_ID, 'gazdasagi-vezeto', 'procurement-logistics-lead', 'existing-agent', 'newly-scaffolded-agent'])('syncs exactly one complete block for %s', name => {
    const f = fixture(name)
    ensureOwnerOperatingRulesSection(name, f.paths); assertBlock(f.prompt)
    const once = readFileSync(f.prompt, 'utf8')
    ensureOwnerOperatingRulesSection(name, f.paths)
    expect(readFileSync(f.prompt, 'utf8')).toBe(once)
  })
  it('refreshes the block after a canonical source change', () => {
    const f = fixture(); ensureOwnerOperatingRulesSection(MAIN_AGENT_ID, f.paths)
    const updated = rules + '\nApproved source update fixture.\n'
    writeFileSync(join(f.root, 'AGENTS.md'), updated)
    ensureOwnerOperatingRulesSection(MAIN_AGENT_ID, f.paths); assertBlock(f.prompt, updated)
  })
  it('heals duplicate complete blocks and preserves surrounding persona', () => {
    const f = fixture(); ensureOwnerOperatingRulesSection(MAIN_AGENT_ID, f.paths)
    writeFileSync(f.prompt, readFileSync(f.prompt, 'utf8') + begin + '\nold\n' + end)
    ensureOwnerOperatingRulesSection(MAIN_AGENT_ID, f.paths); assertBlock(f.prompt)
  })
  it.each(['source', 'prompt', 'empty', 'broken-marker', 'nested-marker'])('fails closed for %s without changing the prompt', kind => {
    const f = fixture()
    if (kind === 'source') rmSync(join(f.root, 'AGENTS.md'))
    if (kind === 'prompt') rmSync(f.prompt)
    if (kind === 'empty') writeFileSync(join(f.root, 'AGENTS.md'), '  ')
    if (kind === 'broken-marker') writeFileSync(f.prompt, 'persona\n' + begin)
    if (kind === 'nested-marker') writeFileSync(f.prompt, 'persona\n' + begin + '\n' + begin + '\nold\n' + end)
    const previous = existsSync(f.prompt) ? readFileSync(f.prompt, 'utf8') : null
    expect(() => ensureOwnerOperatingRulesSection(MAIN_AGENT_ID, f.paths)).toThrow()
    expect(existsSync(f.prompt) ? readFileSync(f.prompt, 'utf8') : null).toBe(previous)
  })
})
describe('actual Codex channel instruction builder', () => {
  function builder(root: string) {
    const source = readFileSync(join(PROJECT_ROOT, 'scripts/codex-channels.mjs'), 'utf8')
    const ast = ts.createSourceFile('channel.mjs', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS)
    const fn = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'instructions')!
    return runInNewContext('(' + fn.getText(ast) + ')', {
      root, bridgeTest: false, economyInstructions: '\nCost policy fixture',
      existsSync, readFileSync, join, readCanonicalOwnerRules,
    }) as (internal?: boolean) => string
  }
  it.each([false, true])('loads complete canonical rules before persona for internal=%s', internal => {
    const f = fixture(); const text = builder(f.root)(internal)
    expect(text.startsWith(rules + '\n\n')).toBe(true)
    expect(text).toContain('# Existing persona')
  })
  it('rejects a missing canonical source', () => {
    const f = fixture(); rmSync(join(f.root, 'AGENTS.md'))
    expect(() => builder(f.root)()).toThrow(/Required owner rules/)
  })
})
describe('worker cwd and dashboard startup gate', () => {
  it.each([false, true])('loads rules from the supplied worker cwd, tools=%s', tools => {
    const first = fixture(); const second = fixture()
    writeFileSync(join(second.root, 'AGENTS.md'), 'Other fixture rules\n')
    expect(workerDeveloperInstructions(first.root, tools, '')).toContain(rules)
    expect(workerDeveloperInstructions(second.root, tools, '')).toContain('Other fixture rules\n')
    rmSync(join(second.root, 'AGENTS.md'))
    expect(() => workerDeveloperInstructions(second.root, tools, '')).toThrow(/Required owner rules/)
  })
  it.each([false, true])('executes the actual web startup sync block, webOnly=%s', webOnly => {
    const f = fixture()
    const source = readFileSync(join(PROJECT_ROOT, 'src/web.ts'), 'utf8')
    const ast = ts.createSourceFile('web.ts', source, ts.ScriptTarget.Latest, true)
    let block: ts.IfStatement | undefined
    function visit(n: ts.Node) {
      if (ts.isIfStatement(n) && n.expression.getText(ast) === '!webOnly' && n.thenStatement.getText(ast).includes('ensureOwnerOperatingRulesSection(MAIN_AGENT_ID)')) block = n
      ts.forEachChild(n, visit)
    }
    visit(ast); expect(block).toBeDefined()
    const context: Record<string, unknown> = { webOnly, MAIN_AGENT_ID }
    for (const name of block!.getText(ast).matchAll(/(ensure[A-Za-z]+)\(/g)) context[name[1]] = vi.fn()
    context.ensureOwnerOperatingRulesSection = (name: string) => ensureOwnerOperatingRulesSection(name, f.paths)
    const before = readFileSync(f.prompt, 'utf8')
    runInNewContext(block!.getText(ast), context)
    if (webOnly) expect(readFileSync(f.prompt, 'utf8')).toBe(before)
    else assertBlock(f.prompt)
  })
})

describe('real worker entrypoint over a local fake app-server', () => {
  it.each([false, true])('passes the canonical rules to thread/start, tools=%s', allowTools => {
    const f = fixture()
    const capture = join(f.root, 'thread.json')
    const fake = join(f.root, 'fake-codex')
    writeFileSync(fake, `#!/usr/bin/env node
const fs = require('node:fs');
const lines = require('node:readline').createInterface({ input: process.stdin });
lines.on('line', line => {
  const m = JSON.parse(line);
  const reply = result => process.stdout.write(JSON.stringify({ id: m.id, result }) + '\\n');
  if (m.method === 'initialize') reply({});
  else if (m.method === 'account/read') reply({ account: { type: 'chatgpt' } });
  else if (m.method === 'thread/start') {
    fs.writeFileSync(process.env.FIXTURE_CAPTURE, JSON.stringify(m.params));
    reply({ thread: { id: 'fixture-thread' } });
  } else if (m.method === 'turn/start') {
    reply({ turn: { id: 'fixture-turn' } });
    process.stdout.write(JSON.stringify({ method: 'item/completed', params: { threadId: 'fixture-thread', item: { type: 'agentMessage', text: 'fixture-result' } } }) + '\\n');
    process.stdout.write(JSON.stringify({ method: 'turn/completed', params: { threadId: 'fixture-thread', turn: { status: 'completed' } } }) + '\\n');
  }
});
`, { mode: 0o755 })
    const out = spawnSync(process.execPath, [join(PROJECT_ROOT, 'scripts/codex-worker.mjs')], {
      cwd: f.root, input: JSON.stringify({ message: 'fixture', cwd: f.root, allowTools }),
      env: { ...process.env, MARVEEN_CODEX_BIN: fake, FIXTURE_CAPTURE: capture }, encoding: 'utf8', timeout: 10000,
    })
    expect(out.status, out.stderr).toBe(0)
    expect(JSON.parse(out.stdout).text).toBe('fixture-result')
    const thread = JSON.parse(readFileSync(capture, 'utf8'))
    expect(thread.cwd).toBe(f.root)
    expect(thread.developerInstructions.startsWith(rules + '\n\n')).toBe(true)
    expect(thread.sandbox).toBe(allowTools ? 'workspace-write' : 'read-only')
  })
  it('fails before spawning app-server when AGENTS.md is missing', () => {
    const f = fixture(); rmSync(join(f.root, 'AGENTS.md'))
    const out = spawnSync(process.execPath, [join(PROJECT_ROOT, 'scripts/codex-worker.mjs')], {
      cwd: f.root, input: JSON.stringify({ message: 'fixture', cwd: f.root, allowTools: false }),
      env: { ...process.env, MARVEEN_CODEX_BIN: join(f.root, 'must-not-start') }, encoding: 'utf8', timeout: 10000,
    })
    expect(out.status).not.toBe(0)
    expect(out.stderr).toContain('Required owner rules')
    expect(out.stderr).not.toContain('must-not-start')
  })
})

// Exercise the standalone launch gate against the same compiled implementation
// used by dashboard startup, without starting a model or a tmux session.
describe('standalone Claude launch gate', () => {
  it('synchronizes the full source and rejects a missing source before launch', () => {
    const f = fixture()
    const run = () => spawnSync(process.execPath, [join(PROJECT_ROOT, 'scripts/sync-owner-rules.mjs'), f.root], {
      cwd: PROJECT_ROOT, encoding: 'utf8', timeout: 15000,
    })
    const first = run()
    expect(first.status, first.stderr).toBe(0)
    assertBlock(f.prompt)
    const once = readFileSync(f.prompt, 'utf8')
    expect(run().status).toBe(0)
    expect(readFileSync(f.prompt, 'utf8')).toBe(once)
    rmSync(join(f.root, 'AGENTS.md'))
    const failed = run()
    expect(failed.status).not.toBe(0)
    expect(failed.stderr).toContain('Required owner rules')
    expect(readFileSync(f.prompt, 'utf8')).toBe(once)
  })
})


describe('dashboard Claude resume gate', () => {
  it('a missing source prevents the actual resume function from replacing the pane', async () => {
    const f = fixture()
    rmSync(join(f.root, 'AGENTS.md'))
    const source = readFileSync(join(PROJECT_ROOT, 'src/web/channel-monitor.ts'), 'utf8')
    const ast = ts.createSourceFile('monitor.ts', source, ts.ScriptTarget.Latest, true)
    const fn = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'resumeMarveenSession')!
    const javascript = ts.transpileModule('(' + fn.getText(ast).replace('export ', '') + ')', {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText
    const replacePane = vi.fn()
    const endRespawn = vi.fn()
    const logError = vi.fn()
    const resume = runInNewContext(javascript, {
      getProvider: () => ({ type: 'telegram', pluginId: 'fixture' }), getMainAgentProvider: () => 'telegram',
      process: { env: { MARVEEN_AGENT_BACKEND: 'sdk' } },
      claimMainRecovery: () => 'owner-fixture-attempt', watchMainRecovery: vi.fn(), failMainRecovery: vi.fn(),
      beginMainRespawn: () => endRespawn, reapChannelOrphans: vi.fn(), reapDetachedChannelClaudes: vi.fn(),
      tmuxBin: () => 'fixture-tmux', PROJECT_ROOT: f.root, MAIN_AGENT_ID,
      ensureSharedClaudeOnboarded: vi.fn(), claudeBin: () => 'fixture-claude',
      buildMainSessionRespawnCmd: () => 'fixture-command', readExtraChannelPluginIds: () => [],
      writeMainExtraPluginsSettings: vi.fn(), mainChannelStateEnv: vi.fn(), readConfiguredMainModel: vi.fn(),
      resolveMainConfigDecision: vi.fn(), execFileSync: replacePane,
      ensureOwnerOperatingRulesSection: (name: string) => ensureOwnerOperatingRulesSection(name, f.paths),
      logger: { warn: vi.fn(), error: logError },
    }) as () => Promise<boolean>
    expect(await resume()).toBe(false)
    expect(replacePane).not.toHaveBeenCalled()
    expect(String(logError.mock.calls[0][0].err)).toContain('Required owner rules')
    expect(endRespawn).toHaveBeenCalledOnce()
  })
})
