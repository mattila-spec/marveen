// Shared Claude launch gate: no model/session starts if canonical sync fails.
import { MAIN_AGENT_ID, PROJECT_ROOT } from '../dist/config.js'
import { ensureOwnerOperatingRulesSection } from '../dist/web/agent-scaffold.js'
const projectRoot = process.argv[2] || PROJECT_ROOT
ensureOwnerOperatingRulesSection(process.argv[3] || MAIN_AGENT_ID, { projectRoot })
