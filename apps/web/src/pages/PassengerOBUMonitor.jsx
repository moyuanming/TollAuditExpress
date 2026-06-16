import React, { useState, useEffect } from 'react'
import { auditApi } from '../api/audit'
import VehicleTripDetail from '../components/VehicleTripDetail'
import { formatTime } from '../components/tripDetailUtils'
import Icon from '../components/Icon'
import DailyScanBar from '../components/charts/DailyScanBar'

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

const VEHICLE_TYPE_LABEL = { 1: '客车', 2: '货车', 14: '货车', 15: '货车', 16: '货车' }

function declaredVehicleTypeLabel(t) {
  return VEHICLE_TYPE_LABEL[t] || (t == null ? '—' : String(t))
}

function PassengerOBUMonitor() {
  const [overview, setOverview] = useState(null)
  const [daily, setDaily] = useState([])
  const [anomalies, setAnomalies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({
    process_status: '',
    llm_result: ''
  })
  const [selectedDetail, setSelectedDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [actionOperator, setActionOperator] = useState('admin')
  const [actionComment, setActionComment] = useState('')

  useEffect(() => {
    loadAll()
    // 不做定时刷新 — 列表/详情数据需结合人工判定,定时刷新会打断操作并造成重复请求
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters])

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [ov, ds, an] = await Promise.all([
        auditApi.getPassengerObuOverview(),
        auditApi.getPassengerObuDailyStats({
          fraud_type: 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A'
        }),
        auditApi.getPassengerObuAnomalies({
          process_status: filters.process_status || undefined,
          llm_result: filters.llm_result || undefined,
          limit: 200
        })
      ])
      setOverview(ov)
      setDaily(ds.stats || [])
      setAnomalies(an.anomalies || [])
    } catch (e) {
      setError(e.message || '加载失败')
      console.error('Failed to load passenger-obu monitor data:', e)
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

  useEffect(() => {
    if (selectedDetail == null) return
    if (selectedDetail.id && selectedDetail.gantry_records !== undefined) return
    let cancelled = false
    setDetailLoading(true)
    auditApi.getSuspect(selectedDetail.id)
      .then(data => { if (!cancelled) setSelectedDetail(data) })
      .catch(err => { console.error('Failed to load anomaly detail:', err) })
      .finally(() => { if (!cancelled) setDetailLoading(false) })
    return () => { cancelled = true }
  }, [selectedDetail?.id])

  function selectRow(anomaly) {
    setSelectedDetail(anomaly)
  }

  function closeDetail() {
    setSelectedDetail(null)
  }

  const pendingCount = anomalies.filter(a => a.process_status === 'UNPROCESSED').length

  const actionForm = selectedDetail && (
    selectedDetail.process_status === 'UNPROCESSED' ? (
      <div className="detail-section">
        <div className="detail-section-title">稽核判定</div>
        <div className="form-group">
          <label>操作员</label>
          <input
            type="text"
            className="input"
            value={actionOperator}
            onChange={e => setActionOperator(e.target.value)}
            placeholder="操作员姓名"
          />
        </div>
        <div className="form-group">
          <label>备注（可选）</label>
          <textarea
            className="input"
            value={actionComment}
            onChange={e => setActionComment(e.target.value)}
            placeholder="判定依据或说明..."
            rows={2}
          />
        </div>
        <div className="form-actions mt-3">
          <button
            className="btn btn-secondary"
            onClick={() => handleProcess(selectedDetail.id, 'REJECTED')}
          >
            排除（误报）
          </button>
          <button
            className="btn btn-danger"
            onClick={() => handleProcess(selectedDetail.id, 'CONFIRMED')}
          >
            确认逃费
          </button>
        </div>
      </div>
    ) : (
      <div className="detail-section">
        <div className="alert alert-info">
          <span>此记录已{STATUS_LABEL[selectedDetail.process_status]}。</span>
        </div>
      </div>
    )
  )

  const tripForDetail = selectedDetail
    ? { ...selectedDetail, audit_results: [selectedDetail] }
    : null

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-group">
          <h2 className="page-title"><Icon name="bus" /> 客车 OBU 监测</h2>
          <span className="page-subtitle">非新A 客车使用 OBU 介质,入口或出口图片识别为货车且 LLM 复核通过</span>
        </div>
        <div className="stats-strip">
          <div className="stat-mini">
            <span className="stat-mini-icon"></span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{anomalies.length}</span>
              <span className="stat-mini-label">当前显示</span>
            </div>
          </div>
          <div className="stat-mini">
            <span className="stat-mini-icon">⏳</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{pendingCount}</span>
              <span className="stat-mini-label">待处理</span>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="error-banner mx-3 mb-2">{error}</div>
      )}

      <div className="filter-section">
        <div className="filter-group">
          <span className="filter-label">处理状态:</span>
          <select
            className="filter-select"
            value={filters.process_status}
            onChange={e => setFilters({ ...filters, process_status: e.target.value })}
          >
            <option value="">全部</option>
            <option value="UNPROCESSED">待处理</option>
            <option value="CONFIRMED">已确认</option>
            <option value="REJECTED">已排除</option>
          </select>
        </div>
        <div className="filter-group">
          <span className="filter-label">LLM 结果:</span>
          <select
            className="filter-select"
            value={filters.llm_result}
            onChange={e => setFilters({ ...filters, llm_result: e.target.value })}
          >
            <option value="">全部</option>
            <option value="pending">未判定</option>
            <option value="same">同一辆车</option>
            <option value="different">不同车</option>
          </select>
        </div>
        <div className="filter-group ml-auto">
          <button className="btn btn-secondary btn-sm" onClick={loadAll}>刷新</button>
        </div>
      </div>

      <div className="content-area">
        <div className="table-panel" style={{ flex: selectedDetail ? 2 : 1 }}>
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th className="col-id">ID</th>
                  <th className="w-110">PASSID</th>
                  <th className="w-90">入口车辆</th>
                  <th className="w-90">入口车型</th>
                  <th className="w-80">入口站</th>
                  <th className="col-time">入口时间</th>
                  <th className="w-90">出口车辆</th>
                  <th className="w-90">出口车型</th>
                  <th className="w-80">出口站</th>
                  <th className="col-time">出口时间</th>
                  <th className="w-80">命中侧</th>
                  <th className="w-90">视觉车型</th>
                  <th className="col-narrow">风险评分</th>
                  <th className="w-100px">LLM</th>
                  <th className="w-80">状态</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={15} className="text-center p-4">
                      <span className="loading-spinner"></span> 加载中...
                    </td>
                  </tr>
                ) : anomalies.length === 0 ? (
                  <tr>
                    <td colSpan={15}>
                      <div className="empty-state">
                        <div className="empty-state-icon"></div>
                        <div className="empty-state-title">暂无异常记录</div>
                        <div className="empty-state-text">系统运行正常，未检测到异常</div>
                      </div>
                    </td>
                  </tr>
                ) : (
                  anomalies.map(a => {
                    const side = SOURCE_SIDE_BADGE[a.source_side] || SOURCE_SIDE_BADGE.BOTH
                    return (
                      <tr
                        key={a.id}
                        onClick={() => selectRow(a)}
                        className="cursor-pointer"
                        data-selected={selectedDetail?.id === a.id ? 'true' : undefined}
                      >
                        <td><span className="mono">#{a.id}</span></td>
                        <td><span className="mono">{a.passid || '-'}</span></td>
                        <td><span className="font-medium">{a.entry_vehicle_id || '-'}</span></td>
                        <td><span className="text-sm">{declaredVehicleTypeLabel(a.entry_vehicle_type)}</span></td>
                        <td><span className="text-sm">{a.entry_station_name || '-'}</span></td>
                        <td><span className="mono text-xs">{formatTime(a.entry_time)}</span></td>
                        <td><span className="font-medium">{a.exit_vehicle_id || '-'}</span></td>
                        <td><span className="text-sm">{declaredVehicleTypeLabel(a.exit_vehicle_type)}</span></td>
                        <td><span className="text-sm">{a.exit_station_name || '-'}</span></td>
                        <td><span className="mono text-xs">{formatTime(a.exit_time)}</span></td>
                        <td><span className={side.className}>{side.label}</span></td>
                        <td>
                          <span
                            className="pill text-0p75"
                            data-risk={a.visual_vehicle_type === 'truck' ? 'high' : 'low'}
                          >
                            {a.visual_vehicle_type === 'truck' ? '货车' : a.visual_vehicle_type === 'car' ? '客车' : a.visual_vehicle_type || '-'}
                          </span>
                        </td>
                        <td>
                          <span
                            className="font-bold"
                            data-risk={(a.risk_score || 0) > 0.7 ? 'high' : 'medium'}
                          >
                            {(a.risk_score || 0).toFixed(2)}
                          </span>
                        </td>
                        <td>
                          {a.llm_call_status === 'called_confirmed' ? (
                            <span
                              className="badge badge-success"
                              title={`LLM 调用: 已通过 (${((a.llm_confidence || 0) * 100).toFixed(0)}%)`}
                            >通过</span>
                          ) : a.llm_call_status === 'called_rejected' ? (
                            <span
                              className="badge badge-warning"
                              title={`LLM 调用: 判定不是货车 (${((a.llm_confidence || 0) * 100).toFixed(0)}%)`}
                            >未通过</span>
                          ) : a.llm_call_status === 'not_called' ? (
                            <span
                              className="badge badge-secondary"
                              title="LLM 未调用(ML 视觉已高自信)"
                            >未调LLM</span>
                          ) : a.llm_call_status === 'service_error' ? (
                            <span
                              className="badge badge-danger"
                              title="vehicle-ai-service 不可达或超时,LLM 未实际执行"
                            >服务异常</span>
                          ) : a.llm_verified === true ? (
                            <span
                              className="badge badge-success"
                              title={`置信度 ${((a.llm_confidence || 0) * 100).toFixed(0)}% (老数据)`}
                            >通过</span>
                          ) : a.llm_verified === false ? (
                            <span
                              className="badge badge-warning"
                              title="未通过 (老数据,详细调用状态未知)"
                            >未通过</span>
                          ) : (
                            <span className="badge badge-info" title="LLM 状态未知">—</span>
                          )}
                        </td>
                        <td>
                          <span className={`badge badge-${a.process_status === 'CONFIRMED' ? 'danger' : a.process_status === 'REJECTED' ? 'success' : 'warning'}`}>
                            {STATUS_LABEL[a.process_status] || a.process_status}
                          </span>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {selectedDetail && (
          <div className="detail-panel w-480">
            <div className="detail-header">
              <div>
                <div className="detail-title">
                  异常详情 #{selectedDetail.id}
                </div>
                {selectedDetail.process_status !== 'UNPROCESSED' && (
                  <div className="text-0p75 text-secondary mt-1">
                    <span className={`badge badge-${selectedDetail.process_status === 'CONFIRMED' ? 'danger' : 'success'} text-0p65`}>
                      {STATUS_LABEL[selectedDetail.process_status]}
                    </span>
                  </div>
                )}
              </div>
              <button className="detail-close" onClick={closeDetail}></button>
            </div>

            <div className="detail-body">
              {detailLoading ? (
                <div className="text-center p-4">
                  <span className="loading-spinner"></span> 加载详情中...
                </div>
              ) : tripForDetail && (selectedDetail.passid || selectedDetail.audit_trip_id) ? (
                <VehicleTripDetail trip={tripForDetail} actions={actionForm} />
              ) : (
                <div className="p-4">
                  <p>该异常关联的 trip 不可用,请通过 passid 跳转。</p>
                  <code>{selectedDetail.passid || `audit_trip_id=${selectedDetail.audit_trip_id}`}</code>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default PassengerOBUMonitor
