import { beforeEach, describe, expect, it, vi } from 'vitest'
const mock = vi.hoisted(() => ({ exec: vi.fn(), spawn: vi.fn(), unref: vi.fn() }))
vi.mock('node:child_process', async original => ({
  ...await original<typeof import('node:child_process')>(), execFileSync: mock.exec, spawn: mock.spawn,
}))
vi.mock('../logger.js', () => ({ logger: { error: vi.fn() } }))
import { claimMainRecovery, failMainRecovery, watchMainRecovery } from '../web/self-healing-recovery-gate.js'
beforeEach(() => { vi.clearAllMocks(); mock.spawn.mockReturnValue({ unref: mock.unref }) })
describe('persistent recovery client', () => {
  it('requires an explicit allowed claim before returning ownership', () => {
    mock.exec.mockReturnValue(JSON.stringify({ allowed: true, attempt_id: 'fixture-id' }))
    expect(claimMainRecovery('monitor')).toBe('fixture-id')
    expect(mock.exec.mock.calls[0][1]).toEqual([expect.stringContaining('self-healing-attempt-gate.py'), 'claim', 'main-channels', 'monitor'])
  })
  it.each(['{}', '{"allowed":false,"attempt_id":"forged"}', '{"attempt_id":"unapproved"}', 'invalid'])('fails closed for %s', raw => {
    mock.exec.mockReturnValue(raw); expect(claimMainRecovery('monitor')).toBeNull()
  })
  it('fails closed when the gate process fails', () => {
    mock.exec.mockImplementation(() => { throw new Error('denied') })
    expect(claimMainRecovery('monitor')).toBeNull()
  })
  it('records failure against the owned token, and starts a detached health verifier', () => {
    mock.exec.mockReturnValue('{}')
    failMainRecovery('monitor', 'owned-id', 'mock restart failed')
    expect(mock.exec.mock.calls[0][1]).toEqual([expect.any(String), 'fail', 'main-channels', 'owned-id', 'mock restart failed'])
    watchMainRecovery('monitor', 'owned-id')
    expect(mock.spawn.mock.calls[0][1]).toEqual([expect.any(String), 'watch', 'main-channels', 'owned-id', expect.stringMatching(/-channels$/)])
    expect(mock.unref).toHaveBeenCalledOnce()
  })
})
