/**
 * 路由测试 — 4 个用例覆盖 Task 5 的路由拆分:
 *   1. /           → 公开 Landing 页面 (Hero 文本可见)
 *   2. /app        → 命中 AuthGuard (mock 后渲染 <div data-testid="guard">)
 *   3. /trips      → 老路径重定向到 /app/trips (NavLink href 校验)
 *   4. /vehicles   → 老路径重定向到 /app/vehicles
 *
 * 路由来源: apps/web/src/App.jsx
 *   - Route path="/"            element={<Landing />}
 *   - Route path="/trips"       element={<LegacyRedirect />}  → /app/trips
 *   - Route path="/vehicles"    element={<LegacyRedirect />}  → /app/vehicles
 *   - Route path="/app/*"       element={<AuthGuard>...      </AuthGuard>}
 *
 * App 内部用 <BrowserRouter>,我们在测试里把它替换成 <MemoryRouter initialEntries=[TEST_PATH]>,
 * 通过模块级变量 __TEST_PATH__ 在每个 it() 里覆盖。
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// 模块级测试上下文,让 react-router-dom mock 能拿到当前 it() 的目标路径
globalThis.__TEST_PATH__ = '/'

// 把 BrowserRouter 替换成 MemoryRouter,initialEntries 用 __TEST_PATH__。
// Routes / Route / Navigate / NavLink 等路由原语透传(保持原行为)。
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    BrowserRouter: ({ children }) => (
      <MemoryRouter initialEntries={[globalThis.__TEST_PATH__]}>
        {children}
      </MemoryRouter>
    ),
  }
})

// Mock AuthGuard —— 让它直接渲染 <div data-testid="guard">{children}</div>,
// 同时把受保护的 children 也渲染出来,这样我们能通过 DOM 断言路由结果。
vi.mock('../../apps/web/src/components/AuthGuard.jsx', () => ({
  AuthGuard: ({ children }) => (
    <div data-testid="guard">{children}</div>
  ),
}))

// Mock AuthProvider —— 避免被 useAuth / window.location 副作用干扰
vi.mock('../../apps/web/src/components/AuthContext.jsx', () => ({
  AuthProvider: ({ children }) => <>{children}</>,
  useAuth: () => ({ isAuthenticated: true, logout: () => {} }),
}))

import App from '../../apps/web/src/App.jsx'

function renderAt(path) {
  globalThis.__TEST_PATH__ = path
  return render(<App />)
}

beforeEach(() => {
  vi.clearAllMocks()
  globalThis.__TEST_PATH__ = '/'
})

describe('路由拆分', () => {
  it('访问 / 看到 Landing 内容 (Hero 标题)', () => {
    renderAt('/')
    // Hero.jsx 实际标题
    expect(screen.getByText('让每一笔通行费,都不再流失')).toBeInTheDocument()
    // Hero eyebrow
    expect(screen.getByText('TollAudit · 高速公路 AI 稽核')).toBeInTheDocument()
  })

  it('访问 /app 命中 AuthGuard', () => {
    renderAt('/app')
    // 我们的 mock 渲染了 <div data-testid="guard">
    expect(screen.getByTestId('guard')).toBeInTheDocument()
  })

  it('老路径 /trips 重定向后,nav 上的行程查询链接 href 指向 /app/trips', () => {
    renderAt('/trips')
    // LegacyRedirect → /app/trips → 进入 /app/* 分支
    // → AuthGuard(moked) 渲染 children → AppNav + Dashboard
    // AppNav 里有 <NavLink to="/app/trips">🚗 行程查询</NavLink>
    const link = screen.getByRole('link', { name: '🚗 行程查询' })
    expect(link).toBeInTheDocument()
    expect(link.getAttribute('href')).toBe('/app/trips')
  })

  it('老路径 /vehicles 重定向后,nav 上的车辆查询链接 href 指向 /app/vehicles', () => {
    renderAt('/vehicles')
    const link = screen.getByRole('link', { name: '🔎 车辆查询' })
    expect(link).toBeInTheDocument()
    expect(link.getAttribute('href')).toBe('/app/vehicles')
  })
})
