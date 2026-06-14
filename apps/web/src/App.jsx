import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import TripQuery from './pages/TripQuery'
import VehicleQuery from './pages/VehicleQuery'
import SuspectList from './pages/SuspectList'
import Statistics from './pages/Statistics'
import TaskManager from './pages/TaskManager'
import TruckOBUMonitor from './pages/TruckOBUMonitor'
import RuleStudio from './pages/RuleStudio'
import Redirect from './pages/Redirect'
import Landing from './pages/Landing/Landing'
import { onApiError } from './api/audit'
import { AuthProvider, useAuth } from './components/AuthContext'
import { AuthGuard } from './components/AuthGuard'

function AppNav() {
  const { isAuthenticated, logout } = useAuth()

  return (
    <nav className="nav">
      <div className="nav-brand">
        <div className="nav-brand-icon">稽</div>
        <h1>高速公路收费稽核系统</h1>
      </div>
      <div className="nav-links">
        <NavLink to="/app" end className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          📊 仪表盘
        </NavLink>
        <NavLink to="/app/trips" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          🚗 行程查询
        </NavLink>
        <NavLink to="/app/vehicles" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          🔎 车辆查询
        </NavLink>
        <NavLink to="/app/suspects" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          ⚠️ 可疑记录
        </NavLink>
        <NavLink to="/app/stats" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          📈 统计分析
        </NavLink>
        <NavLink to="/app/tasks" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          ⏰ 定时任务
        </NavLink>
        <NavLink to="/app/truck-obu-monitor" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          🚛 货车OBU监测
        </NavLink>
        <NavLink to="/app/rules" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          📐 规则管理
        </NavLink>
      </div>
      {isAuthenticated && (
        <button className="btn-logout" onClick={logout}>退出登录</button>
      )}
    </nav>
  )
}

const OLD_PATH_REDIRECTS = {
  '/trips': '/app/trips',
  '/vehicles': '/app/vehicles',
  '/suspects': '/app/suspects',
  '/stats': '/app/stats',
  '/tasks': '/app/tasks',
  '/truck-obu-monitor': '/app/truck-obu-monitor',
  '/rules': '/app/rules',
}

function LegacyRedirect() {
  // 处理老路径,根据当前 location.pathname 302
  const path = window.location.pathname
  const target = OLD_PATH_REDIRECTS[path] || '/app'
  return <Navigate to={target} replace />
}

function App() {
  const [apiError, setApiError] = useState(null)

  useEffect(() => {
    return onApiError((err) => {
      setApiError(err.message)
      setTimeout(() => setApiError(null), 4000)
    })
  }, [])

  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app">
          {apiError && <div className="error-banner">{apiError}</div>}
          <Routes>
            {/* 公开路由:营销落地页 */}
            <Route path="/" element={<Landing />} />

            {/* 老路径兼容 → 跳新路径 */}
            <Route path="/trips" element={<LegacyRedirect />} />
            <Route path="/vehicles" element={<LegacyRedirect />} />
            <Route path="/suspects" element={<LegacyRedirect />} />
            <Route path="/stats" element={<LegacyRedirect />} />
            <Route path="/tasks" element={<LegacyRedirect />} />
            <Route path="/truck-obu-monitor" element={<LegacyRedirect />} />
            <Route path="/rules" element={<LegacyRedirect />} />

            {/* 内部 /app/* 受 AuthGuard 保护 */}
            <Route path="/app/*" element={
              <AuthGuard>
                <AppNav />
                <main className="main">
                  <Routes>
                    <Route index element={<Dashboard />} />
                    <Route path="trips" element={<TripQuery />} />
                    <Route path="vehicles" element={<VehicleQuery />} />
                    <Route path="suspects" element={<SuspectList />} />
                    <Route path="stats" element={<Statistics />} />
                    <Route path="tasks" element={<TaskManager />} />
                    <Route path="truck-obu-monitor" element={<TruckOBUMonitor />} />
                    <Route path="rules" element={<RuleStudio />} />
                    <Route path="*" element={<Navigate to="/app" replace />} />
                  </Routes>
                </main>
              </AuthGuard>
            } />

            {/* 其他公开路由 */}
            <Route path="/redirect" element={<Redirect />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App