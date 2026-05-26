import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import TripQuery from './pages/TripQuery'
import SuspectList from './pages/SuspectList'
import Statistics from './pages/Statistics'

function App() {
  return (
    <BrowserRouter>
      <div className="app">
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
            <NavLink to="/suspects" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
              ⚠️ 可疑记录
            </NavLink>
            <NavLink to="/stats" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
              📈 统计分析
            </NavLink>
          </div>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/trips" element={<TripQuery />} />
            <Route path="/suspects" element={<SuspectList />} />
            <Route path="/stats" element={<Statistics />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
