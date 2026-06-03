import React, { useState, useEffect } from 'react'
import { auditApi } from '../api/audit'

function TripQuery() {
  const [activeModel, setActiveModel] = useState('modelA')
  const [trips, setTrips] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [selectedTrip, setSelectedTrip] = useState(null)
  const [filters, setFilters] = useState({
    passid: '',
    status: '',
    entry_station: '',
    exit_station: '',
    start_time: '',
    end_time: ''
  })
  const limit = 50

  useEffect(() => {
    loadTrips()
  }, [page, activeModel, filters.status, filters.entry_station, filters.exit_station, filters.start_time, filters.end_time])

  async function loadTrips() {
    setLoading(true)
    try {
      const params = { limit, offset: page * limit }
      if (filters.status) params.status = filters.status
      if (filters.entry_station) params.entry_station = filters.entry_station
      if (filters.exit_station) params.exit_station = filters.exit_station
      if (filters.start_time) params.start_time = filters.start_time
      if (filters.end_time) params.end_time = filters.end_time
      const data = await auditApi.getTrips(params)
      let tripList = data.trips || []
      // Model A 只检测客车(类型1)，过滤掉原车型是货车的记录
      if (activeModel === 'modelA') {
        tripList = tripList.filter(t => t.entry_vehicle_type === 1)
      }
      setTrips(tripList)
      setTotal(data.total || 0)
    } catch (e) {
      console.error('Failed to load trips:', e)
    } finally {
      setLoading(false)
    }
  }

  function searchTrips() {
    setPage(0)
    loadTrips()
  }

  async function viewDetail(trip) {
    setSelectedTrip(trip)
  }

  // Model A columns: 货车套用客车OBU
  const modelAColumns = [
    { key: 'entry_time', label: '交易时间', width: '160px' },
    { key: 'entry_vehicle', label: '入口车牌', width: '100px' },
    { key: 'entry_type', label: '交易车型', width: '80px' },
    { key: 'visual_type', label: '视觉识别', width: '80px' },
    { key: 'entry_image_status', label: '图片下载', width: '100px' },
    { key: 'entry_image', label: '入口图片', width: '100px' },
    { key: 'result', label: '结果', width: '80px' },
    { key: 'risk', label: '风险评分', width: '80px' },
    { key: 'status', label: '状态', width: '80px' },
  ]

  // Model B columns: 出入口车辆比对
  const modelBColumns = [
    { key: 'entry_time', label: '入口时间', width: '140px' },
    { key: 'entry_station', label: '入口站点', width: '100px' },
    { key: 'exit_station', label: '出口站点', width: '100px' },
    { key: 'entry_vehicle', label: '入口车牌', width: '100px' },
    { key: 'exit_vehicle', label: '出口车牌', width: '100px' },
    { key: 'entry_image_status', label: '入口图', width: '100px' },
    { key: 'exit_image_status', label: '出口图', width: '100px' },
    { key: 'entry_image', label: '入口图片', width: '100px' },
    { key: 'exit_image', label: '出口图片', width: '100px' },
    { key: 'fingerprint_sim', label: '车纹相似度', width: '100px' },
    { key: 'result', label: '结果', width: '80px' },
    { key: 'status', label: '状态', width: '80px' },
  ]

  const columns = activeModel === 'modelA' ? modelAColumns : modelBColumns

  const getImageStatusBadge = (url) => {
    if (!url) return <span className="badge badge-warning">无URL</span>
    return <span className="badge badge-info">有图片</span>
  }

  const renderModelACell = (trip, key) => {
    switch (key) {
      case 'entry_time':
        return trip.entry_time ? trip.entry_time.slice(0, 19).replace('T', ' ') : '-'
      case 'entry_station':
        return trip.entry_station_name || '-'
      case 'entry_vehicle':
        return trip.entry_vehicle_id || '-'
      case 'entry_type':
        return (
          <span style={{
            padding: '0.2rem 0.5rem',
            borderRadius: 4,
            fontSize: '0.75rem',
            background: trip.entry_vehicle_type === 1 ? 'var(--accent-green-bg)' : 'var(--accent-amber-bg)',
            color: trip.entry_vehicle_type === 1 ? 'var(--accent-green)' : 'var(--accent-amber)'
          }}>
            {trip.entry_vehicle_type === 1 ? '客车' : '货车'}
          </span>
        )
      case 'entry_image_status':
        return getImageStatusBadge(trip.entry_image_trans)
      case 'entry_image':
        if (trip.entry_image_trans) {
          return (
            <img 
              src={trip.entry_image_trans} 
              alt="entry" 
              className="image-thumb"
              onError={(e) => e.target.style.display = 'none'}
            />
          )
        }
        return <span style={{color: 'var(--text-tertiary)'}}>无</span>
      case 'visual_type':
        const visType = trip.entry_visual_type
        return (
          <span style={{
            padding: '0.2rem 0.5rem',
            borderRadius: 4,
            fontSize: '0.75rem',
            background: visType === 'truck' ? 'var(--accent-red-bg)' : visType === 'car' ? 'var(--accent-green-bg)' : 'var(--bg-tertiary)',
            color: visType === 'truck' ? 'var(--accent-red)' : visType === 'car' ? 'var(--accent-green)' : 'var(--text-secondary)'
          }}>
            {visType === 'truck' ? '货车(视觉)' : visType === 'car' ? '客车(视觉)' : '-'}
          </span>
        )
      case 'result':
        if (trip.audit_status === 'SUSPECTED') {
          return <span className="badge badge-danger">可疑</span>
        }
        if (trip.entry_visual_type) {
          return <span className="badge badge-success">正常</span>
        }
        return <span className="badge badge-warning">未检测</span>
      case 'risk':
        return ((trip.risk_score || 0) * 100).toFixed(0) + '%'
      case 'status':
        return (
          <span className={`badge badge-${trip.audit_status === 'VERIFIED' ? 'success' : trip.audit_status === 'SUSPECTED' ? 'danger' : 'warning'}`}>
            {trip.audit_status === 'PENDING' ? '待处理' : 
             trip.audit_status === 'VERIFIED' ? '已核验' : 
             trip.audit_status === 'SUSPECTED' ? '可疑' : trip.audit_status}
          </span>
        )
      default:
        return trip[key] || '-'
    }
  }

  const renderModelBCell = (trip, key) => {
    switch (key) {
      case 'entry_time':
        return trip.entry_time ? trip.entry_time.slice(0, 19).replace('T', ' ') : '-'
      case 'entry_station':
        return trip.entry_station_name || '-'
      case 'exit_station':
        return trip.exit_station_name || '-'
      case 'entry_vehicle':
        return trip.entry_vehicle_id || '-'
      case 'exit_vehicle':
        return trip.exit_vehicle_id || '-'
      case 'entry_image_status':
        return getImageStatusBadge(trip.entry_image_license)
      case 'exit_image_status':
        return getImageStatusBadge(trip.exit_image_license)
      case 'entry_image':
        if (trip.entry_image_license) {
          return (
            <img 
              src={trip.entry_image_license} 
              alt="entry" 
              className="image-thumb"
              onError={(e) => e.target.style.display = 'none'}
            />
          )
        }
        return <span style={{color: 'var(--text-tertiary)'}}>无</span>
      case 'exit_image':
        if (trip.exit_image_license) {
          return (
            <img 
              src={trip.exit_image_license} 
              alt="exit" 
              className="image-thumb"
              onError={(e) => e.target.style.display = 'none'}
            />
          )
        }
        return <span style={{color: 'var(--text-tertiary)'}}>无</span>
      case 'fingerprint_sim':
        const sim = trip.fingerprint_sim || 0
        return (
          <span style={{
            fontWeight: 600,
            color: sim < 0.6 ? 'var(--accent-red)' : sim < 0.8 ? 'var(--accent-amber)' : 'var(--accent-green)'
          }}>
            {(sim * 100).toFixed(0)}%
          </span>
        )
      case 'result':
        return <span className="badge badge-warning">待检测</span>
      case 'status':
        return (
          <span className={`badge badge-${trip.audit_status === 'VERIFIED' ? 'success' : trip.audit_status === 'SUSPECTED' ? 'danger' : 'warning'}`}>
            {trip.audit_status === 'PENDING' ? '待处理' : 
             trip.audit_status === 'VERIFIED' ? '已核验' : 
             trip.audit_status === 'SUSPECTED' ? '可疑' : trip.audit_status}
          </span>
        )
      default:
        return trip[key] || '-'
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-group">
          <h2 className="page-title">行程查询</h2>
          <span className="page-subtitle">查看和管理车辆通行记录</span>
        </div>
        <div className="stats-strip">
          <div className="stat-mini">
            <span className="stat-mini-icon">📊</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{total}</span>
              <span className="stat-mini-label">总记录数</span>
            </div>
          </div>
          <div className="stat-mini">
            <span className="stat-mini-icon">⏳</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{trips.filter(t => t.audit_status === 'PENDING').length}</span>
              <span className="stat-mini-label">待处理</span>
            </div>
          </div>
          <div className="stat-mini">
            <span className="stat-mini-icon">⚠️</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{trips.filter(t => t.audit_status === 'SUSPECTED').length}</span>
              <span className="stat-mini-label">可疑</span>
            </div>
          </div>
        </div>
      </div>

      <div className="model-tabs">
        <button 
          className={`model-tab model-a ${activeModel === 'modelA' ? 'active' : ''}`}
          onClick={() => { setActiveModel('modelA'); setPage(0) }}
        >
          🚛 模型A: 货车套用客车OBU
        </button>
        <button 
          className={`model-tab model-b ${activeModel === 'modelB' ? 'active' : ''}`}
          onClick={() => { setActiveModel('modelB'); setPage(0) }}
        >
          🚗 模型B: 出入口车辆比对
        </button>
      </div>

      <div className="filter-section">
        <div className="filter-group">
          <span className="filter-label">状态:</span>
          <select 
            className="filter-select"
            value={filters.status}
            onChange={(e) => setFilters({...filters, status: e.target.value})}
          >
            <option value="">全部</option>
            <option value="PENDING">待处理</option>
            <option value="VERIFIED">已核验</option>
            <option value="SUSPECTED">可疑</option>
          </select>
        </div>
        {activeModel === 'modelB' && (
          <>
            <div className="filter-group">
              <span className="filter-label">入口站:</span>
              <input
                className="filter-select"
                placeholder="站点名称"
                value={filters.entry_station}
                onChange={(e) => setFilters({...filters, entry_station: e.target.value})}
              />
            </div>
            <div className="filter-group">
              <span className="filter-label">出口站:</span>
              <input
                className="filter-select"
                placeholder="站点名称"
                value={filters.exit_station}
                onChange={(e) => setFilters({...filters, exit_station: e.target.value})}
              />
            </div>
            <div className="filter-group">
              <span className="filter-label">开始时间:</span>
              <input
                type="date"
                className="filter-select"
                value={filters.start_time}
                onChange={(e) => setFilters({...filters, start_time: e.target.value})}
              />
            </div>
            <div className="filter-group">
              <span className="filter-label">结束时间:</span>
              <input
                type="date"
                className="filter-select"
                value={filters.end_time}
                onChange={(e) => setFilters({...filters, end_time: e.target.value})}
              />
            </div>
          </>
        )}
        <button className="btn btn-primary" onClick={searchTrips}>
          🔍 搜索
        </button>
        <button className="btn btn-secondary" onClick={() => {
          setFilters({passid: '', status: '', entry_station: '', exit_station: '', start_time: '', end_time: ''})
          searchTrips()
        }}>
          🔄 重置
        </button>
      </div>

      <div className="content-area">
        <div className="table-panel">
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  {columns.map(col => (
                    <th key={col.key} style={{width: col.width}}>{col.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={columns.length} style={{textAlign: 'center', padding: '2rem'}}>
                      <span className="loading-spinner"></span> 加载中...
                    </td>
                  </tr>
                ) : trips.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length}>
                      <div className="empty-state">
                        <div className="empty-state-icon">🚗</div>
                        <div className="empty-state-title">暂无数据</div>
                        <div className="empty-state-text">请先在仪表盘启动数据聚合任务</div>
                      </div>
                    </td>
                  </tr>
                ) : (
                  trips.map((trip, idx) => (
                    <tr key={trip.id || idx} onClick={() => viewDetail(trip)} style={{cursor: 'pointer'}}>
                      {columns.map(col => (
                        <td key={col.key}>
                          {activeModel === 'modelA' 
                            ? renderModelACell(trip, col.key)
                            : renderModelBCell(trip, col.key)
                          }
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          
          <div className="pagination">
            <div className="pagination-info">
              共 {total} 条，第 {page + 1} / {Math.ceil(total / limit) || 1} 页
            </div>
            <div className="pagination-controls">
              <button 
                className="btn btn-secondary btn-sm" 
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                ◀ 上一页
              </button>
              <button 
                className="btn btn-secondary btn-sm" 
                onClick={() => setPage(p => (p + 1) * limit < total ? p + 1 : p)}
                disabled={(page + 1) * limit >= total}
              >
                下一页 ▶
              </button>
            </div>
          </div>
        </div>

        {selectedTrip && (
          <div className="detail-panel">
            <div className="detail-header">
              <span className="detail-title">📋 行程详情</span>
              <button className="detail-close" onClick={() => setSelectedTrip(null)}>✕</button>
            </div>
            <div className="detail-body">
              <div className="detail-section">
                <div className="detail-section-title">基本信息</div>
                <div className="detail-grid">
                  <div className="detail-item">
                    <span className="detail-label">入口时间</span>
                    <span className="detail-value">{selectedTrip.entry_time}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">出口时间</span>
                    <span className="detail-value">{selectedTrip.exit_time}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">入口站点</span>
                    <span className="detail-value">{selectedTrip.entry_station_name}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">出口站点</span>
                    <span className="detail-value">{selectedTrip.exit_station_name}</span>
                  </div>
                </div>
              </div>

              <div className="detail-section">
                <div className="detail-section-title">入口车辆信息</div>
                <div className="detail-grid">
                  <div className="detail-item">
                    <span className="detail-label">车牌</span>
                    <span className="detail-value">{selectedTrip.entry_vehicle_id}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">交易车型</span>
                    <span className="detail-value">
                      {selectedTrip.entry_vehicle_type === 1 ? '客车' : '货车'}
                    </span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">车牌颜色</span>
                    <span className="detail-value">{selectedTrip.entry_vehicle_color}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">OBU ID</span>
                    <span className="detail-value mono">{selectedTrip.entry_obu_id}</span>
                  </div>
                </div>
              </div>

              <div className="detail-section">
                <div className="detail-section-title">出口车辆信息</div>
                <div className="detail-grid">
                  <div className="detail-item">
                    <span className="detail-label">车牌</span>
                    <span className="detail-value">{selectedTrip.exit_vehicle_id}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">交易车型</span>
                    <span className="detail-value">
                      {selectedTrip.exit_vehicle_type === 1 ? '客车' : '货车'}
                    </span>
                  </div>
                </div>
              </div>

              {activeModel === 'modelA' && (
                <div className="detail-section">
                  <div className="detail-section-title">🚛 模型A: 货车套用OBU检测</div>
                  <div style={{marginTop: '1rem'}}>
                    <div className="detail-label" style={{marginBottom: '0.5rem'}}>入口车辆图片 (_trans.jpg)</div>
                    {selectedTrip.entry_image_trans ? (
                      <img 
                        src={selectedTrip.entry_image_trans} 
                        alt="entry vehicle"
                        style={{width: '100%', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-primary)'}}
                        onError={(e) => e.target.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="150" fill="%23eee"><rect width="200" height="150"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="%23999">图片加载失败</text></svg>'}
                      />
                    ) : (
                      <div style={{padding: '2rem', textAlign: 'center', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)'}}>
                        无图片
                      </div>
                    )}
                  </div>
                </div>
              )}

              {activeModel === 'modelB' && (
                <div className="detail-section">
                  <div className="detail-section-title">🚗 模型B: 出入口比对</div>
                  <div style={{marginTop: '1rem'}}>
                    <div className="detail-label" style={{marginBottom: '0.5rem'}}>出入口图片对比 (_license.jpg)</div>
                    <div className="image-compare">
                      <div className="image-compare-item">
                        <div className="image-compare-label">入口</div>
                        {selectedTrip.entry_image_license ? (
                          <img 
                            src={selectedTrip.entry_image_license} 
                            alt="entry"
                            className="image-compare-img"
                            onError={(e) => e.target.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="150" fill="%23eee"><rect width="200" height="150"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="%23999">加载失败</text></svg>'}
                          />
                        ) : (
                          <div className="image-compare-img" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)'}}>
                            无图片
                          </div>
                        )}
                      </div>
                      <div className="image-compare-item">
                        <div className="image-compare-label">出口</div>
                        {selectedTrip.exit_image_license ? (
                          <img 
                            src={selectedTrip.exit_image_license} 
                            alt="exit"
                            className="image-compare-img"
                            onError={(e) => e.target.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="150" fill="%23eee"><rect width="200" height="150"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="%23999">加载失败</text></svg>'}
                          />
                        ) : (
                          <div className="image-compare-img" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)'}}>
                            无图片
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div className="detail-section">
                <div className="detail-section-title">风险评分</div>
                <div style={{
                  padding: '1rem',
                  background: (selectedTrip.risk_score || 0) > 0.5 ? 'var(--accent-red-bg)' : 'var(--accent-green-bg)',
                  borderRadius: 'var(--radius-md)',
                  textAlign: 'center'
                }}>
                  <div style={{
                    fontSize: '2rem',
                    fontWeight: 700,
                    color: (selectedTrip.risk_score || 0) > 0.5 ? 'var(--accent-red)' : 'var(--accent-green)'
                  }}>
                    {((selectedTrip.risk_score || 0) * 100).toFixed(1)}%
                  </div>
                  <div style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.25rem'}}>
                    {(selectedTrip.risk_score || 0) > 0.5 ? '高风险' : (selectedTrip.risk_score || 0) > 0.2 ? '中风险' : '低风险'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default TripQuery
