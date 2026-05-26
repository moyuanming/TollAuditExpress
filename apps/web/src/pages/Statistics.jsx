import React, { useState, useEffect } from 'react'
import { auditApi } from '../api/audit'

function Statistics() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStats()
  }, [])

  async function loadStats() {
    setLoading(true)
    try {
      const data = await auditApi.getStats()
      setStats(data)
    } catch (e) {
      console.error('Failed to load stats:', e)
    } finally {
      setLoading(false)
    }
  }

  const suspiciousRate = stats?.total_trips > 0 
    ? ((stats.suspected_trips / stats.total_trips) * 100).toFixed(1) 
    : '0.0'
  
  const confirmRate = stats?.suspected_trips > 0 
    ? ((stats.confirmed_fraud / stats.suspected_trips) * 100).toFixed(1) 
    : '0.0'

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-group">
          <h2 className="page-title">统计分析</h2>
          <span className="page-subtitle">稽核系统数据统计与报告</span>
        </div>
        <button className="btn btn-secondary" onClick={loadStats}>🔄 刷新</button>
      </div>

      <div className="stats-strip">
        <div className="stat-mini">
          <span className="stat-mini-icon">🚗</span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{stats?.total_trips || 0}</span>
            <span className="stat-mini-label">总行程数</span>
          </div>
        </div>
        <div className="stat-mini">
          <span className="stat-mini-icon">✅</span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{stats?.verified_trips || 0}</span>
            <span className="stat-mini-label">已核验</span>
          </div>
        </div>
        <div className="stat-mini">
          <span className="stat-mini-icon">⚠️</span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{stats?.suspected_trips || 0}</span>
            <span className="stat-mini-label">可疑记录</span>
          </div>
        </div>
        <div className="stat-mini">
          <span className="stat-mini-icon">🚨</span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{stats?.confirmed_fraud || 0}</span>
            <span className="stat-mini-label">确认欺诈</span>
          </div>
        </div>
      </div>

      <div className="content-area">
        <div className="table-panel" style={{flex: 1, padding: '1rem'}}>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', height: '100%'}}>
            <div className="card" style={{margin: 0}}>
              <div className="card-header">
                <span className="card-title">📊 稽核效能指标</span>
              </div>
              <div style={{display: 'flex', flexDirection: 'column', gap: '1rem', padding: '0.5rem 0'}}>
                <div style={{
                  padding: '1.25rem',
                  background: 'var(--accent-blue-bg)',
                  borderRadius: 'var(--radius-md)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between'
                }}>
                  <div>
                    <div style={{fontSize: '0.8rem', color: 'var(--accent-blue)', fontWeight: 500}}>可疑率</div>
                    <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--accent-blue)'}}>{suspiciousRate}%</div>
                  </div>
                  <div style={{fontSize: '2rem'}}>🎯</div>
                </div>
                
                <div style={{
                  padding: '1.25rem',
                  background: 'var(--accent-green-bg)',
                  borderRadius: 'var(--radius-md)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between'
                }}>
                  <div>
                    <div style={{fontSize: '0.8rem', color: 'var(--accent-green)', fontWeight: 500}}>确认率</div>
                    <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--accent-green)'}}>{confirmRate}%</div>
                  </div>
                  <div style={{fontSize: '2rem'}}>✓</div>
                </div>
              </div>
            </div>

            <div className="card" style={{margin: 0}}>
              <div className="card-header">
                <span className="card-title">🔍 检测分布</span>
              </div>
              <div style={{padding: '1rem 0'}}>
                <div style={{marginBottom: '1.5rem'}}>
                  <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem'}}>
                    <span style={{fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                      <span>🚛</span> 货车套用OBU
                    </span>
                    <span style={{fontWeight: 600}}>~60%</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{width: '60%', background: 'var(--accent-purple)'}}></div>
                  </div>
                </div>
                <div>
                  <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem'}}>
                    <span style={{fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                      <span>🚗</span> 出入口不一致
                    </span>
                    <span style={{fontWeight: 600}}>~40%</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{width: '40%', background: 'var(--accent-blue)'}}></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Statistics
