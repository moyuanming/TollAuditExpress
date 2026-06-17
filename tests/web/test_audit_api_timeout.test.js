/**
 * fetchJSON 超时 + AbortController 测试 — 防止 OBU 详情页 fetch 永远 pending。
 *
 * 背景:之前 fetchJSON 直接 await fetch(),如果后端 hang(源库网络抖动/慢查询),
 * 前端就无限转圈 → UI "卡住"。新行为:
 *   - 默认 20s 超时,AbortController 自动中断
 *   - options.signal 可被调用方传入并被串联
 *   - 超时时抛出友好错误(errorListeners 会收到)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { fetchJSON, onApiError } from '../../apps/web/src/api/audit.js'

beforeEach(() => {
  vi.useFakeTimers()
  // vitest 在 isolated env 下 globalThis.localStorage 可能是 undefined,
  // 用 stubGlobal 注入一个最小可用的 in-memory 实现。
  const memStore = new Map()
  const memLocalStorage = {
    getItem: (k) => (memStore.has(k) ? memStore.get(k) : null),
    setItem: (k, v) => memStore.set(k, String(v)),
    removeItem: (k) => memStore.delete(k),
    clear: () => memStore.clear(),
    key: (i) => Array.from(memStore.keys())[i] ?? null,
    get length() { return memStore.size },
  }
  vi.stubGlobal('localStorage', memLocalStorage)
  global.fetch = vi.fn()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('fetchJSON timeout + AbortController', () => {
  // 5s 默认测试超时不够 — fake timer 要快进 20s 才能触发 AbortController

  // 用 signal 监听的 mock fetch 模拟真实行为:不返回数据,但 abort 时 reject
  function signalAwarePendingFetch() {
    return (_url, init) =>
      new Promise((_resolve, reject) => {
        if (init.signal.aborted) {
          reject(new DOMException('Aborted', 'AbortError'))
        } else {
          init.signal.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        }
      })
  }

  // 立刻把 promise 标成 handled,避免 vitest unhandled-rejection 误报
  function trapRejection(p) {
    return p.catch((e) => e)
  }

  it('默认 20s 超时,fetch 永远不返回时抛出友好错误', async () => {
    global.fetch.mockImplementation(signalAwarePendingFetch())

    const listener = vi.fn()
    onApiError(listener)

    const promise = trapRejection(fetchJSON('/api/audit/suspect/1'))

    // 快进 20s,触发 AbortController.abort
    await vi.advanceTimersByTimeAsync(20000)

    const err = await promise
    expect(err.message).toMatch(/请求超时/)
    expect(listener).toHaveBeenCalled()
  }, 30000)

  it('options.timeout 覆盖默认 20s', async () => {
    global.fetch.mockImplementation(signalAwarePendingFetch())

    const promise = trapRejection(fetchJSON('/api/audit/suspect/1', { timeout: 1000 }))
    await vi.advanceTimersByTimeAsync(1000)
    const err = await promise
    expect(err.message).toMatch(/请求超时/)
  }, 30000)

  it('options.signal 被 abort 时,fetch 立即被中断', async () => {
    let observedSignal = null
    global.fetch.mockImplementation((_url, init) => {
      observedSignal = init.signal
      return new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => reject(new Error('aborted by signal')))
      })
    })

    const controller = new AbortController()
    const promise = trapRejection(fetchJSON('/api/audit/suspect/1', { signal: controller.signal }))
    controller.abort()

    const err = await promise
    expect(err).toBeInstanceOf(Error)
    expect(observedSignal).not.toBeNull()
    expect(observedSignal.aborted).toBe(true)
  }, 30000)
})
