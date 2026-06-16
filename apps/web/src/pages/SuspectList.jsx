import React, { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { auditApi } from '../api/audit'
import VehicleTripDetail from '../components/VehicleTripDetail'
import { formatTime } from '../components/tripDetailUtils'

const FRAUD_TYPE_LABEL = {
  PASSENGER_USES_TRUCK_OBU_NON_NEW_A: '客车套货OBU',
  TRUCK_AS_CAR: '货套客',
  ENTRY_EXIT_MISMATCH: '出入口不一致',
  GATEWAY_ANOMALY: '门架异常',
  VEHICLE_TYPE_DOWNGRADE: '大车小标',
  SAME_PLATE_DIFF_VEHICLE: '同牌不同车',
  OBU_UNBIND: 'OBU 借用',
  OBU_SHIELD: 'OBU 屏蔽'
}

const FRAUD_TYPE_FILTER_OPTIONS = [
  { value: 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A', label: '客套货OBU' },
  { value: 'TRUCK_AS_CAR', label: '货套客' },
  { value: 'ENTRY_EXIT_MISMATCH', label: '出入口' },
  { value: 'GATEWAY_ANOMALY', label: '门架异常' },
  { value: 'VEHICLE_TYPE_DOWNGRADE', label: '大车小标' },
  { value: 'SAME_PLATE_DIFF_VEHICLE', label: '同牌不同车' },
  { value: 'OBU_UNBIND', label: 'OBU 借用' },
  { value: 'OBU_SHIELD', label: 'OBU 屏蔽' }
]

const FRAUD_TYPE_BADGE_CLASS = {
  PASSENGER_USES_TRUCK_OBU_NON_NEW_A: 'badge-purple',
  TRUCK_AS_CAR: 'badge-purple',
  GATEWAY_ANOMALY: 'badge-warning',
  VEHICLE_TYPE_DOWNGRADE: 'badge-danger',
  SAME_PLATE_DIFF_VEHICLE: 'badge-danger',
  OBU_UNBIND: 'badge-warning',
  OBU_SHIELD: 'badge-info'
}

const STATUS_LABEL = {
  UNPROCESSED: '待处理',
  CONFIRMED: '已确认',
  REJECTED: '已排除'
}

function SuspectList() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialId = searchParams.get('id') ? Number(searchParams.get('id')) : null

  const [suspects, setSuspects] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState(initialId)
  const [selectedDetail, setSelectedDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [filters, setFilters] = useState({ fraudTypes: [], status: '', llmResult: '' })
  const [actionOperator, setActionOperator] = useState('admin')
  const [actionComment, setActionComment] = useState('')

  useEffect(() => {
    loadSuspects()
  }, [filters])

  useEffect(() => {
    if (selectedId == null) {
      setSelectedDetail(null)
      return
    }
    let cancelled = false
    setDetailLoading(true)
    auditApi.getSuspect(selectedId)
      .then(data => { if (!cancelled) setSelectedDetail(data) })
      .catch(err => { console.error('Failed to load suspect detail:', err) })
      .finally(() => { if (!cancelled) setDetailLoading(false) })
    return () => { cancelled = true }
  }, [selectedId])

  function selectRow(id) {
    setSelectedId(id)
    setSearchParams(id ? { id: String(id) } : {})
  }

  async function loadSuspects() {
    setLoading(true)
    try {
      const params = { limit: 200 }
      if (filters.fraudTypes.length > 0) params.fraud_types = filters.fraudTypes
      if (filters.status) params.process_status = filters.status
      if (filters.llmResult) params.llm_result = filters.llmResult
      const data = await auditApi.getSuspects(params)
      setSuspects(data.suspects || [])
    } catch (e) {
      console.error('Failed to load suspects:', e)
    } finally {
      setLoading(false)
    }
  }

  function toggleFraudType(value) {
    setFilters(prev => {
      const exists = prev.fraudTypes.includes(value)
      return {
        ...prev,
        fraudTypes: exists ? prev.fraudTypes.filter(t => t !== value) : [...prev.fraudTypes, value]
      }
    })
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
      
      // 立即更新 selectedDetail 的状态，避免重新获取数据的延迟
      if (selectedId === id && selectedDetail) {
        setSelectedDetail({
          ...selectedDetail,
          process_status: action === 'CONFIRMED' ? 'CONFIRMED' : 'REJECTED'
        })
      }
      
      await loadSuspects()
    } catch (e) {
      console.error('Failed to process:', e)
      alert('操作失败: ' + e.message)
    }
  }

  // 把单条 suspect 包装为 VehicleTripDetail 期望的 trip 形状：
  // audit_results = [selectedDetail] 触发"决策依据"区复用
  const tripForDetail = selectedDetail
    ? { ...selectedDetail, audit_results: [selectedDetail] }
    : null

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

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-group">
          <h2 className="page-title">可疑记录</h2>
          <span className="page-subtitle">点击行查看详情，帮助判断是否真正可疑</span>
        </div>
        <div className="stats-strip">
          <div className="stat-mini">
            <span className="stat-mini-icon"></span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{suspects.length}</span>
              <span className="stat-mini-label">当前显示</span>
            </div>
          </div>
          <div className="stat-mini">
            <span className="stat-mini-icon">⏳</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{suspects.filter(s => s.process_status === 'UNPROCESSED').length}</span>
              <span className="stat-mini-label">待处理</span>
            </div>
          </div>
        </div>
      </div>

      <div className="filter-section">
        <div className="filter-group">
          <span className="filter-label">欺诈类型:</span>
          <div className="multi-select-chips">
            {FRAUD_TYPE_FILTER_OPTIONS.map(opt => {
              const active = filters.fraudTypes.includes(opt.value)
              return (
                <button
                  key={opt.value}
                  type="button"
                  className={`chip ${active ? 'chip-active' : ''}`}
                  onClick={() => toggleFraudType(opt.value)}
                >
                  {opt.label}
                </button>
              )
            })}
            {filters.fraudTypes.length > 0 && (
              <button
                type="button"
                className="chip chip-clear"
                onClick={() => setFilters({ ...filters, fraudTypes: [] })}
              >
                清除
              </button>
            )}
          </div>
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
        <div className="filter-group">
          <span className="filter-label">LLM 结果:</span>
          <select
            className="filter-select"
            value={filters.llmResult}
            onChange={(e) => setFilters({...filters, llmResult: e.target.value})}
          >
            <option value="">全部</option>
            <option value="pending">未判定</option>
            <option value="same">同一辆车</option>
            <option value="different">不同车</option>
          </select>
        </div>
        <div className="filter-group ml-auto muted text-0p75">
          提示: 点击 chip 多选；点击表格行查看详情
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
                  <th className="col-fraud-type">欺诈类型</th>
                  <th className="w-90">入口车辆</th>
                  <th className="w-80">入口站</th>
                  <th className="col-time">入口时间</th>
                  <th className="w-90">出口车辆</th>
                  <th className="w-80">出口站</th>
                  <th className="col-time">出口时间</th>
                  <th className="w-80">入口视觉</th>
                  <th className="w-80">出口视觉</th>
                  <th className="col-narrow">风险评分</th>
                  <th className="w-100px">LLM 结果</th>
                  <th className="w-80">状态</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={14} className="text-center p-4">
                      <span className="loading-spinner"></span> 加载中...
                    </td>
                  </tr>
                ) : suspects.length === 0 ? (
                  <tr>
                    <td colSpan={14}>
                      <div className="empty-state">
                        <div className="empty-state-icon"></div>
                        <div className="empty-state-title">暂无可疑记录</div>
                        <div className="empty-state-text">系统运行正常，未检测到异常</div>
                      </div>
                    </td>
                  </tr>
                ) : (
                  suspects.map(s => (
                    <tr
                      key={s.id}
                      onClick={() => selectRow(s.id)}
                      className="cursor-pointer"
                      data-selected={selectedId === s.id ? 'true' : undefined}
                    >
                      <td><span className="mono">#{s.id}</span></td>
                      <td><span className="mono">{s.passid}</span></td>
                      <td>
                        <span className={`badge ${FRAUD_TYPE_BADGE_CLASS[s.fraud_type] || 'badge-info'}`}>
                          {FRAUD_TYPE_LABEL[s.fraud_type] || s.fraud_type}
                        </span>
                      </td>
                      <td><span className="font-medium">{s.entry_vehicle_id || '-'}</span></td>
                      <td><span className="text-sm">{s.entry_station_name || '-'}</span></td>
                      <td><span className="mono text-xs">{formatTime(s.entry_time)}</span></td>
                      <td><span className="font-medium">{s.exit_vehicle_id || '-'}</span></td>
                      <td><span className="text-sm">{s.exit_station_name || '-'}</span></td>
                      <td><span className="mono text-xs">{formatTime(s.exit_time)}</span></td>
                      <td>
                        <span
                          className="pill text-0p75"
                          data-risk={s.entry_visual_type === 'truck' ? 'high' : 'low'}
                        >
                          {s.entry_visual_type === 'truck' ? '货车' : s.entry_visual_type === 'car' ? '客车' : '-'}
                        </span>
                      </td>
                      <td>
                        <span
                          className="pill text-0p75"
                          data-risk={s.exit_visual_type === 'truck' ? 'high' : 'low'}
                        >
                          {s.exit_visual_type === 'truck' ? '货车' : s.exit_visual_type === 'car' ? '客车' : '-'}
                        </span>
                      </td>
                      <td>
                        <span
                          className="font-bold"
                          data-risk={(s.risk_score || 0) > 0.7 ? 'high' : 'medium'}
                        >
                          {(s.risk_score || 0).toFixed(2)}
                        </span>
                      </td>
                      <td>
                        {s.llm_checked_at == null ? (
                          <span className="badge badge-info" title="待 LLM 判定">未判定</span>
                        ) : s.llm_is_same_vehicle === 1 ? (
                          <span className="badge badge-success" title={`置信度 ${((s.llm_confidence || 0) * 100).toFixed(0)}%`}>
                            同一辆
                          </span>
                        ) : s.llm_is_same_vehicle === 0 ? (
                          <span className="badge badge-danger" title={`置信度 ${((s.llm_confidence || 0) * 100).toFixed(0)}%`}>
                            不同车
                          </span>
                        ) : (
                          <span className="badge badge-warning">—</span>
                        )}
                      </td>
                      <td>
                        <span className={`badge badge-${s.process_status === 'CONFIRMED' ? 'danger' : s.process_status === 'REJECTED' ? 'success' : 'warning'}`}>
                          {STATUS_LABEL[s.process_status] || s.process_status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {selectedId != null && (
          <div className="detail-panel w-480">
            <div className="detail-header">
              <div>
                <div className="detail-title">
                  可疑记录 #{selectedId}
                </div>
                {selectedDetail && (
                  <div className="text-0p75 text-secondary mt-1">
                    {FRAUD_TYPE_LABEL[selectedDetail.fraud_type] || selectedDetail.fraud_type}
                    {selectedDetail.process_status !== 'UNPROCESSED' && (
                      <> · <span className={`badge badge-${selectedDetail.process_status === 'CONFIRMED' ? 'danger' : 'success'} text-0p65`}>
                        {STATUS_LABEL[selectedDetail.process_status]}
                      </span></>
                    )}
                  </div>
                )}
              </div>
              <button className="detail-close" onClick={() => selectRow(null)}></button>
            </div>

            <div className="detail-body">
              {detailLoading ? (
                <div className="text-center p-4">
                  <span className="loading-spinner"></span> 加载详情中...
                </div>
              ) : !tripForDetail ? (
                <div className="empty-state">未找到详情</div>
              ) : (
                <VehicleTripDetail trip={tripForDetail} actions={actionForm} />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default SuspectList
