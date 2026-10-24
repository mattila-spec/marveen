import { afterAll, expect, it, vi } from 'vitest'
import { existsSync, readFileSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
const fixture = vi.hoisted(() => ({ root: '' }))
vi.mock('../config.js', async original => {
  const config = await original<typeof import('../config.js')>()
  const fs = await import('node:fs'); const os = await import('node:os'); const path = await import('node:path')
  fixture.root = fs.mkdtempSync(path.join(os.tmpdir(), 'owner-scaffold-'))
  return { ...config, PROJECT_ROOT: fixture.root, STORE_DIR: path.join(fixture.root, 'store') }
})
vi.mock('../web/agent-config.js', async original => ({
  ...await original<typeof import('../web/agent-config.js')>(),
  agentDir: (name: string) => join(fixture.root, 'agents', name),
}))
import { scaffoldAgentDir, ensureOwnerOperatingRulesSection } from '../web/agent-scaffold.js'
afterAll(() => { if (fixture.root) rmSync(fixture.root, { recursive: true, force: true }) })
it('a genuinely scaffolded new agent receives canonical rules before its first launch', () => {
  const rules = '# Approved fixture rules\n1. Owner decides.\n2. Verify completion.\n3. Keep owner informed.\n'
  writeFileSync(join(fixture.root, 'AGENTS.md'), rules)
  scaffoldAgentDir('fresh-owner-fixture')
  const dir = join(fixture.root, 'agents', 'fresh-owner-fixture')
  expect(existsSync(join(dir, '.claude', 'skills'))).toBe(true)
  // Agent creation writes the generated persona after directory scaffolding.
  const prompt = join(dir, 'CLAUDE.md')
  writeFileSync(prompt, '# Generated fixture persona\n')
  ensureOwnerOperatingRulesSection('fresh-owner-fixture')
  const once = readFileSync(prompt, 'utf8')
  expect(once).toContain(rules)
  expect(once.match(/<!-- BEGIN GENERATED: owner-operating-rules -->/g)).toHaveLength(1)
  ensureOwnerOperatingRulesSection('fresh-owner-fixture')
  expect(readFileSync(prompt, 'utf8')).toBe(once)
})
