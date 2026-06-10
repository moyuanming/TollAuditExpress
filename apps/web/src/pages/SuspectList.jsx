import React, { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { auditApi } from '../api/audit'
import VehicleTripDetail from '../components/VehicleTripDetail'
import { formatTime } from '../components/tripDetailUtils'

const FRAUD_TYPE_LABEL = {
  TRUCK_USES_PASSENGER_OBU: '货车套用客车OBU',
  ENTRY_EXIT_MISMATCH: '出入口车辆不一致'
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
  const [filters, setFilters] = useState({ fraudType: '', status: '', llmResult: '' })
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
      if (filters.fraudType) params.fraud_type = filters.fraudType
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
        <div className="detail-section-title">✍️ 稽核判定</div>
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
        <div className="form-actions" style={{ marginTop: 12 }}>
          <button
            className="btn btn-secondary"
            onClick={() => handleProcess(selectedDetail.id, 'REJECTED')}
          >
            ✗ 排除（误报）
          </button>
          <button
            className="btn btn-danger"
            onClick={() => handleProcess(selectedDetail.id, 'CONFIRMED')}
          >
            ✓ 确认逃费
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
            <span className="stat-mini-icon">📊</span>
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
        <div className="filter-group" style={{ marginLeft: 'auto', color: 'var(--text-tertiary)', fontSize: '0.75rem' }}>
          💡 提示: 点击表格行查看详情
        </div>
      </div>

      <div className="content-area">
        <div className="table-panel" style={{ flex: selectedDetail ? 2 : 1 }}>
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th style={{width: '60px'}}>ID</th>
                  <th style={{width: '110px'}}>PASSID</th>
                  <th style={{width: '120px'}}>欺诈类型</th>
                  <th style={{width: '90px'}}>入口车辆</th>
                  <th style={{width: '80px'}}>入口站</th>
                  <th style={{width: '110px'}}>入口时间</th>
                  <th style={{width: '90px'}}>出口车辆</th>
                  <th style={{width: '80px'}}>出口站</th>
                  <th style={{width: '110px'}}>出口时间</th>
                  <th style={{width: '80px'}}>入口视觉</th>
                  <th style={{width: '80px'}}>出口视觉</th>
                  <th style={{width: '70px'}}>风险评分</th>
                  <th style={{width: '100px'}}>LLM 结果</th>
                  <th style={{width: '80px'}}>状态</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={14} style={{textAlign: 'center', padding: '2rem'}}>
                      <span className="loading-spinner"></span> 加载中...
                    </td>
                  </tr>
                ) : suspects.length === 0 ? (
                  <tr>
                    <td colSpan={14}>
                      <div className="empty-state">
                        <div className="empty-state-icon">✅</div>
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
                      style={{
                        cursor: 'pointer',
                        background: selectedId === s.id ? 'var(--accent-blue-bg)' : undefined
                      }}
                    >
                      <td><span className="mono">#{s.id}</span></td>
                      <td><span className="mono">{s.passid}</span></td>
                      <td>
                        <span className={`badge ${s.fraud_type === 'TRUCK_USES_PASSENGER_OBU' ? 'badge-purple' : 'badge-info'}`}>
                          {s.fraud_type === 'TRUCK_USES_PASSENGER_OBU' ? '🚛 货车套OBU' : '🚗 出入口'}
                        </span>
                      </td>
                      <td><span style={{fontWeight: 500}}>{s.entry_vehicle_id || '-'}</span></td>
                      <td><span style={{fontSize: '0.75rem'}}>{s.entry_station_name || '-'}</span></td>
                      <td><span className="mono" style={{fontSize: '0.7rem'}}>{formatTime(s.entry_time)}</span></td>
                      <td><span style={{fontWeight: 500}}>{s.exit_vehicle_id || '-'}</span></td>
                      <td><span style={{fontSize: '0.75rem'}}>{s.exit_station_name || '-'}</span></td>
                      <td><span className="mono" style={{fontSize: '0.7rem'}}>{formatTime(s.exit_time)}</span></td>
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
                        {s.llm_checked_at == null ? (
                          <span className="badge badge-info" title="待 LLM 判定">未判定</span>
                        ) : s.llm_is_same_vehicle === 1 ? (
                          <span className="badge badge-success" title={`置信度 ${((s.llm_confidence || 0) * 100).toFixed(0)}%`}>
                            ✅ 同一辆
                          </span>
                        ) : s.llm_is_same_vehicle === 0 ? (
                          <span className="badge badge-danger" title={`置信度 ${((s.llm_confidence || 0) * 100).toFixed(0)}%`}>
                            ❌ 不同车
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
          <div className="detail-panel" style={{ width: 480 }}>
            <div className="detail-header">
              <div>
                <div className="detail-title">
                  可疑记录 #{selectedId}
                </div>
                {selectedDetail && (
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: 4 }}>
                    {FRAUD_TYPE_LABEL[selectedDetail.fraud_type] || selectedDetail.fraud_type}
                    {selectedDetail.process_status !== 'UNPROCESSED' && (
                      <> · <span className={`badge badge-${selectedDetail.process_status === 'CONFIRMED' ? 'danger' : 'success'}`} style={{ fontSize: '0.65rem' }}>
                        {STATUS_LABEL[selectedDetail.process_status]}
                      </span></>
                    )}
                  </div>
                )}
              </div>
              <button className="detail-close" onClick={() => selectRow(null)}>✕</button>
            </div>

            <div className="detail-body">
              {detailLoading ? (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
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
