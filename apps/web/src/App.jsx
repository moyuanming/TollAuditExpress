import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import TripQuery from './pages/TripQuery'
import VehicleQuery from './pages/VehicleQuery'
import SuspectList from './pages/SuspectList'
import Statistics from './pages/Statistics'
import TaskManager from './pages/TaskManager'
import Redirect from './pages/Redirect'
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
        <NavLink to="/" end className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          📊 仪表盘
        </NavLink>
        <NavLink to="/trips" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          🚗 行程查询
        </NavLink>
        <NavLink to="/vehicles" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          🔎 车辆查询
        </NavLink>
        <NavLink to="/suspects" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          ⚠️ 可疑记录
        </NavLink>
        <NavLink to="/stats" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          📈 统计分析
        </NavLink>
        <NavLink to="/tasks" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          ⏰ 定时任务
        </NavLink>
      </div>
      {isAuthenticated && (
        <button className="btn-logout" onClick={logout}>退出登录</button>
      )}
    </nav>
  )
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
          <AppNav />
          <main className="main">
            <Routes>
              <Route path="/redirect" element={<Redirect />} />
              <Route path="*" element={
                <AuthGuard>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/trips" element={<TripQuery />} />
                    <Route path="/vehicles" element={<VehicleQuery />} />
                    <Route path="/suspects" element={<SuspectList />} />
                    <Route path="/stats" element={<Statistics />} />
                    <Route path="/tasks" element={<TaskManager />} />
                    <Route path="*" element={<Navigate to="/" />} />
                  </Routes>
                </AuthGuard>
              } />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
