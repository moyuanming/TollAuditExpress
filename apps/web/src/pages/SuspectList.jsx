import React, { useState, useEffect } from 'react'
import { auditApi } from '../api/audit'

function SuspectList() {
  const [suspects, setSuspects] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [filters, setFilters] = useState({
    fraudType: '',
    status: ''
  })

  useEffect(() => {
    loadSuspects()
  }, [filters])

  async function loadSuspects() {
    setLoading(true)
    try {
      const params = { limit: 200 }
      if (filters.fraudType) params.fraud_type = filters.fraudType
      if (filters.status) params.process_status = filters.status
      const data = await auditApi.getSuspects(params)
      setSuspects(data.suspects || [])
    } catch (e) {
      console.error('Failed to load suspects:', e)
    } finally {
      setLoading(false)
    }
  }

  async function handleProcess(id, action) {
    try {
      await auditApi.processSuspect(id, { action, operator: 'admin' })
      loadSuspects()
    } catch (e) {
      console.error('Failed to process:', e)
    }
  }

  const displayedSuspects = suspects

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-group">
          <h2 className="page-title">可疑记录</h2>
          <span className="page-subtitle">管理和处理检测到的异常通行记录</span>
        </div>
        <div className="stats-strip">
          <div className="stat-mini">
            <span className="stat-mini-icon">📊</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{displayedSuspects.length}</span>
              <span className="stat-mini-label">当前显示</span>
            </div>
          </div>
          <div className="stat-mini">
            <span className="stat-mini-icon">⏳</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{displayedSuspects.filter(s => s.process_status === 'UNPROCESSED').length}</span>
              <span className="stat-mini-label">待处理</span>
            </div>
          </div>
        </div>
      </div>

      <div className="filter-section">
        <div className="filter-group">
          <span className="filter-label">欺诈类型:</span>
          <select 
            className="filter-select"
            value={filters.fraudType}
            onChange={(e) => setFilters({...filters, fraudType: e.target.value})}
          >
            <option value="">全部</option>
            <option value="TRUCK_USES_PASSENGER_OBU">货车套用OBU</option>
            <option value="ENTRY_EXIT_MISMATCH">出入口不一致</option>
          </select>
        </div>
        <div className="filter-group">
          <span className="filter-label">处理状态:</span>
          <select 
            className="filter-select"
            value={filters.status}
            onChange={(e) => setFilters({...filters, status: e.target.value})}
          >
            <option value="">全部</option>
            <option value="UNPROCESSED">待处理</option>
            <option value="CONFIRMED">已确认</option>
            <option value="REJECTED">已排除</option>
          </select>
        </div>
      </div>

      <div className="content-area">
        <div className="table-panel" style={{flex: 1}}>
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th style={{width: '60px'}}>ID</th>
                  <th style={{width: '120px'}}>PASSID</th>
                  <th style={{width: '120px'}}>欺诈类型</th>
                  <th style={{width: '100px'}}>入口车辆</th>
                  <th style={{width: '100px'}}>出口车辆</th>
                  <th style={{width: '100px'}}>入口视觉</th>
                  <th style={{width: '100px'}}>出口视觉</th>
                  <th style={{width: '80px'}}>风险评分</th>
                  <th style={{width: '80px'}}>状态</th>
                  <th style={{width: '150px'}}>操作</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={10} style={{textAlign: 'center', padding: '2rem'}}>
                      <span className="loading-spinner"></span> 加载中...
                    </td>
                  </tr>
                ) : displayedSuspects.length === 0 ? (
                  <tr>
                    <td colSpan={10}>
                      <div className="empty-state">
                        <div className="empty-state-icon">✅</div>
                        <div className="empty-state-title">暂无可疑记录</div>
                        <div className="empty-state-text">系统运行正常，未检测到异常</div>
                      </div>
                    </td>
                  </tr>
                ) : (
                  displayedSuspects.map(s => (
                    <tr key={s.id}>
                      <td><span className="mono">#{s.id}</span></td>
                      <td><span className="mono">{s.passid}</span></td>
                      <td>
                        <span className={`badge ${s.fraud_type === 'TRUCK_USES_PASSENGER_OBU' ? 'badge-purple' : 'badge-info'}`}>
                          {s.fraud_type === 'TRUCK_USES_PASSENGER_OBU' ? '🚛 货车套OBU' : '🚗 出入口'}
                        </span>
                      </td>
                      <td>
                        <span style={{fontWeight: 500}}>{s.entry_vehicle_id || '-'}</span>
                      </td>
                      <td>
                        <span style={{fontWeight: 500}}>{s.exit_vehicle_id || '-'}</span>
                      </td>
                      <td>
                        <span style={{
                          padding: '0.2rem 0.5rem',
                          borderRadius: 4,
                          fontSize: '0.75rem',
                          background: s.entry_visual_type === 'truck' ? 'var(--accent-red-bg)' : 'var(--accent-green-bg)',
                          color: s.entry_visual_type === 'truck' ? 'var(--accent-red)' : 'var(--accent-green)'
                        }}>
                          {s.entry_visual_type === 'truck' ? '货车' : s.entry_visual_type === 'car' ? '客车' : '-'}
                        </span>
                      </td>
                      <td>
                        <span style={{
                          padding: '0.2rem 0.5rem',
                          borderRadius: 4,
                          fontSize: '0.75rem',
                          background: s.exit_visual_type === 'truck' ? 'var(--accent-red-bg)' : 'var(--accent-green-bg)',
                          color: s.exit_visual_type === 'truck' ? 'var(--accent-red)' : 'var(--accent-green)'
                        }}>
                          {s.exit_visual_type === 'truck' ? '货车' : s.exit_visual_type === 'car' ? '客车' : '-'}
                        </span>
                      </td>
                      <td>
                        <span style={{
                          fontWeight: 600,
                          color: (s.risk_score || 0) > 0.7 ? 'var(--accent-red)' : 'var(--accent-amber)'
                        }}>
                          {(s.risk_score || 0).toFixed(2)}
                        </span>
                      </td>
                      <td>
                        <span className={`badge badge-${s.process_status === 'CONFIRMED' ? 'danger' : s.process_status === 'REJECTED' ? 'success' : 'warning'}`}>
                          {s.process_status === 'UNPROCESSED' ? '待处理' : 
                           s.process_status === 'CONFIRMED' ? '已确认' : 
                           s.process_status === 'REJECTED' ? '已排除' : s.process_status}
                        </span>
                      </td>
                      <td>
                        <div className="action-btns">
                          {s.process_status === 'UNPROCESSED' && (
                            <>
                              <button 
                                className="btn btn-success btn-sm" 
                                onClick={() => handleProcess(s.id, 'CONFIRMED')}
                              >
                                ✓ 确认
                              </button>
                              <button 
                                className="btn btn-secondary btn-sm" 
                                onClick={() => handleProcess(s.id, 'REJECTED')}
                              >
                                ✗ 排除
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

export default SuspectList
