import React, { useState, useEffect, useRef } from 'react'
import { auditApi } from '../api/audit'
import VehicleTripDetail from '../components/VehicleTripDetail'
import { formatTime } from '../components/tripDetailUtils'

const STATUS_LABEL = {
  UNPROCESSED: '待处理',
  CONFIRMED: '已确认',
  REJECTED: '已排除'
}

const SOURCE_SIDE_BADGE = {
  ENTRY: { className: 'badge badge-info', label: '入口' },
  EXIT: { className: 'badge badge-warning', label: '出口' },
  BOTH: { className: 'badge badge-danger', label: '两侧' }
}

const POLL_INTERVAL_MS = 30_000

function TruckOBUMonitor() {
  const [overview, setOverview] = useState(null)
  const [daily, setDaily] = useState([])
  const [anomalies, setAnomalies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({
    from_date: '',
    to_date: '',
    process_status: ''
  })
  const [selectedDetail, setSelectedDetail] = useState(null)
  const [actionOperator, setActionOperator] = useState('admin')
  const [actionComment, setActionComment] = useState('')
  const pollTimerRef = useRef(null)

  useEffect(() => {
    loadAll()
    pollTimerRef.current = setInterval(loadAll, POLL_INTERVAL_MS)
    return () => { if (pollTimerRef.current) clearInterval(pollTimerRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters])

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [ov, ds, an] = await Promise.all([
        auditApi.getTruckObuOverview(),
        auditApi.getTruckObuDailyStats({
          from_date: filters.from_date || undefined,
          to_date: filters.to_date || undefined,
          fraud_type: 'TRUCK_USES_TRUCK_OBU_NON_NEW_A'
        }),
        auditApi.getTruckObuAnomalies({
          process_status: filters.process_status || undefined,
          limit: 100
        })
      ])
      setOverview(ov)
      setDaily(ds.stats || [])
      setAnomalies(an.anomalies || [])
    } catch (e) {
      setError(e.message || '加载失败')
      console.error('Failed to load truck-obu monitor data:', e)
    } finally {
      setLoading(false)
    }
  }

  async function handleProcess(id, action) {
    if (!actionOperator.trim()) {
      alert('请填写操作员')
      return
    }
    try {
      await auditApi.processSuspect(id, {
        action,
        operator: actionOperator.trim(),
        comments: actionComment.trim() || null
      })
      setActionComment('')
      if (selectedDetail?.id === id) {
        setSelectedDetail({
          ...selectedDetail,
          process_status: action === 'CONFIRMED' ? 'CONFIRMED' : 'REJECTED'
        })
      }
      await loadAll()
    } catch (e) {
      console.error('Failed to process:', e)
      alert('操作失败: ' + e.message)
    }
  }

  function selectRow(anomaly) {
    setSelectedDetail(anomaly)
  }

  function closeDetail() {
    setSelectedDetail(null)
  }

  // 趋势柱状图 max 计算
  const maxScanned = daily.length > 0
    ? Math.max(...daily.map(d => d.scanned_count || 0), 1)
    : 1

  // 把单条 anomaly 包装为 VehicleTripDetail 期望的 trip 形状
  const tripForDetail = selectedDetail
    ? { ...selectedDetail, audit_results: [selectedDetail] }
    : null

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-group">
          <h2 className="page-title">🚛 货车 OBU 监测</h2>
          <span className="page-subtitle">非新A开头货车使用 OBU 介质的实时监测（2026-06-01 起持续）</span>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            className="form-input"
            type="text"
            placeholder="操作员"
            value={actionOperator}
            onChange={e => setActionOperator(e.target.value)}
            style={{ width: 100 }}
          />
          <button className="btn btn-secondary" onClick={loadAll}>🔄 刷新</button>
        </div>
      </div>

      {error && (
        <div className="error-banner" style={{ margin: '0 1rem 0.5rem' }}>{error}</div>
      )}

      <div className="stats-strip">
        <div className="stat-mini">
          <span className="stat-mini-icon">🔍</span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{overview?.total_scanned || 0}</span>
            <span className="stat-mini-label">累计扫描</span>
          </div>
        </div>
        <div className="stat-mini">
          <span className="stat-mini-icon">⚠️</span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{overview?.total_suspicious || 0}</span>
            <span className="stat-mini-label">异常记录</span>
          </div>
        </div>
        <div className="stat-mini" style={{ background: 'var(--accent-yellow-bg, rgba(255, 193, 7, 0.1))' }}>
          <span className="stat-mini-icon">⏳</span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{overview?.total_pending || 0}</span>
            <span className="stat-mini-label">待处理</span>
          </div>
        </div>
        <div className="stat-mini" style={{ background: 'var(--accent-green-bg, rgba(40, 167, 69, 0.1))' }}>
          <span className="stat-mini-icon">✅</span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{overview?.total_confirmed || 0}</span>
            <span className="stat-mini-label">已确认</span>
          </div>
        </div>
      </div>

      <div className="content-area" style={{ flexDirection: 'column', gap: '1rem' }}>
        <div className="card">
          <div className="card-header">
            <span className="card-title">📈 每日趋势（最近 30 天）</span>
            {overview?.last_run_at && (
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                最近执行：{overview.last_run_at}
              </span>
            )}
          </div>
          {daily.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
              暂无统计数据
            </div>
          ) : (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end', height: 180, padding: '0.5rem 0', overflowX: 'auto' }}>
              {daily.map(d => {
                const h = Math.max(((d.scanned_count || 0) / maxScanned) * 140, 2)
                return (
                  <div key={d.date} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 36 }} title={`${d.date} 扫描 ${d.scanned_count} 异常 ${d.suspicious_count}`}>
                    <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)' }}>{d.suspicious_count || 0}</span>
                    <div style={{
                      width: 16, height: h,
                      background: (d.suspicious_count || 0) > 0 ? 'var(--accent-red, #dc3545)' : 'var(--accent-blue, #007bff)',
                      borderRadius: '3px 3px 0 0',
                      transition: 'height 0.2s'
                    }} />
                    <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', marginTop: 4 }}>
                      {d.date.slice(5)}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="filter-section" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <label>从：</label>
          <input
            className="form-input"
            type="date"
            value={filters.from_date}
            onChange={e => setFilters({ ...filters, from_date: e.target.value })}
          />
          <label>至：</label>
          <input
            className="form-input"
            type="date"
            value={filters.to_date}
            onChange={e => setFilters({ ...filters, to_date: e.target.value })}
          />
          <label>状态：</label>
          <select
            className="form-input"
            value={filters.process_status}
            onChange={e => setFilters({ ...filters, process_status: e.target.value })}
          >
            <option value="">全部</option>
            <option value="UNPROCESSED">待处理</option>
            <option value="CONFIRMED">已确认</option>
            <option value="REJECTED">已排除</option>
          </select>
          <button className="btn btn-secondary" onClick={loadAll}>应用</button>
        </div>

        <div className="table-panel">
          {loading ? (
            <div style={{ padding: '2rem', textAlign: 'center' }}>加载中…</div>
          ) : anomalies.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
              暂无异常记录
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>PASSID</th>
                  <th>车牌</th>
                  <th>入口车型</th>
                  <th>出口车型</th>
                  <th>入口介质</th>
                  <th>出口介质</th>
                  <th>命中侧</th>
                  <th>入口时间</th>
                  <th>出口时间</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.map(a => {
                  const side = SOURCE_SIDE_BADGE[a.source_side] || SOURCE_SIDE_BADGE.BOTH
                  return (
                    <tr key={a.id} onClick={() => selectRow(a)} style={{ cursor: 'pointer' }}>
                      <td>{a.id}</td>
                      <td><code>{a.passid || '-'}</code></td>
                      <td>{a.entry_vehicle_id || a.exit_vehicle_id || '-'}</td>
                      <td>{a.entry_vehicle_type ?? '-'}</td>
                      <td>{a.exit_vehicle_type ?? '-'}</td>
                      <td>{a.entry_media_type === 1 ? 'OBU' : a.entry_media_type === 2 ? 'MTC' : a.entry_media_type ?? '-'}</td>
                      <td>{a.exit_media_type === 1 ? 'OBU' : a.exit_media_type === 2 ? 'MTC' : a.exit_media_type ?? '-'}</td>
                      <td><span className={side.className}>{side.label}</span></td>
                      <td>{formatTime(a.entry_time) || '-'}</td>
                      <td>{formatTime(a.exit_time) || '-'}</td>
                      <td>
                        <span className={`badge badge-${a.process_status === 'CONFIRMED' ? 'danger' : a.process_status === 'REJECTED' ? 'success' : 'warning'}`}>
                          {STATUS_LABEL[a.process_status] || a.process_status}
                        </span>
                      </td>
                      <td onClick={e => e.stopPropagation()}>
                        <button className="btn btn-secondary" style={{ marginRight: 4 }} onClick={() => selectRow(a)}>详情</button>
                        {a.process_status === 'UNPROCESSED' && (
                          <>
                            <button className="btn btn-danger" style={{ marginRight: 4 }} onClick={() => handleProcess(a.id, 'CONFIRMED')}>确认</button>
                            <button className="btn btn-success" onClick={() => handleProcess(a.id, 'REJECTED')}>排除</button>
                          </>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {selectedDetail && (
        <div className="modal-overlay" onClick={closeDetail}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 900, width: '90%' }}>
            <div className="modal-header">
              <h3>异常详情 #{selectedDetail.id}</h3>
              <button className="btn btn-secondary" onClick={closeDetail}>关闭</button>
            </div>
            <div className="modal-body" style={{ maxHeight: '70vh', overflow: 'auto' }}>
              {detailLoading ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>加载中…</div>
              ) : tripForDetail && (selectedDetail.passid || selectedDetail.audit_trip_id) ? (
                <VehicleTripDetail trip={tripForDetail} />
              ) : (
                <div style={{ padding: '1rem' }}>
                  <p>该异常关联的 trip 不可用,请通过 passid 跳转。</p>
                  <code>{selectedDetail.passid || `audit_trip_id=${selectedDetail.audit_trip_id}`}</code>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default TruckOBUMonitor
