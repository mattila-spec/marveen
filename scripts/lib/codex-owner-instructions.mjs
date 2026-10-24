import { readFileSync } from 'node:fs'
import { join } from 'node:path'
export function readCanonicalOwnerRules(cwd) {
  const path = join(cwd, 'AGENTS.md')
  let rules
  try { rules = readFileSync(path, 'utf8') }
  catch (cause) { throw new Error(`Required owner rules are missing or unreadable: ${path}`, { cause }) }
  if (!rules.trim()) throw new Error(`Required owner rules are empty: ${path}`)
  return rules
}
export function workerDeveloperInstructions(cwd, allowTools, economyInstructions) {
  return readCanonicalOwnerRules(cwd) + '\n\n' + (allowTools
    ? 'Complete the requested task.'
    : 'Generate only the requested text. Do not use external tools or modify files; only the model-upgrade control is available.') + economyInstructions
}
