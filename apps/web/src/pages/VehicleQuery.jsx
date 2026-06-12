// 任意车辆通行信息及门架轨迹查询（数据源：Doris 原始表）
import React, { useState, useEffect, useMemo } from 'react'
import { auditApi } from '../api/audit'
import VehicleTripDetail from '../components/VehicleTripDetail'
import { formatTime } from '../components/tripDetailUtils'

const PAGE_SIZE_OPTIONS = [20, 50, 100, 200]

const VEHICLE_TYPE_LABEL = { 1: '客车', 2: '货车' }
const COLOR_LABELS = ['未识别', '蓝', '黄', '黑', '白', '其他']

function todayISO(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return d.toISOString().slice(0, 10)
}

function VehicleQuery() {
  const [filters, setFilters] = useState({
    vehicle_id: '',
    vehicle_id_match: 'exact',
    obu_id: '',
    vehicle_type: '',
    vehicle_color: '',
    entry_station_name: '',
    exit_station_name: '',
    start_time: todayISO(0),
    end_time: todayISO(0),
    date_preset: 'today',
    min_gantry_count: '',
    max_gantry_count: '',
    order_by: 'entry_time',
    order: 'desc',
  })
  const [trips, setTrips] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(0)
  const [limit, setLimit] = useState(50)
  const [selectedPassid, setSelectedPassid] = useState(null)
  const [selectedDetail, setSelectedDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  function applyDatePreset(preset) {
    if (preset === 'today') return { start_time: todayISO(0), end_time: todayISO(0) }
    if (preset === 'last7') return { start_time: todayISO(-6), end_time: todayISO(0) }
    if (preset === 'last30') return { start_time: todayISO(-29), end_time: todayISO(0) }
    return { start_time: filters.start_time, end_time: filters.end_time }
  }

  function setDatePreset(preset) {
    const next = applyDatePreset(preset)
    setFilters({ ...filters, date_preset: preset, ...next })
  }

  function buildApiParams() {
    const params = { limit, offset: page * limit }
    const v = (filters.vehicle_id || '').trim().toUpperCase()
    if (v) {
      params.vehicle_id = v
      params.vehicle_id_match = filters.vehicle_id_match
    }
    if (filters.obu_id) params.obu_id = filters.obu_id.trim()
    if (filters.vehicle_type) params.vehicle_type = Number(filters.vehicle_type)
    if (filters.vehicle_color) params.vehicle_color = Number(filters.vehicle_color)
    if (filters.entry_station_name) params.entry_station_name = filters.entry_station_name.trim()
    if (filters.exit_station_name) params.exit_station_name = filters.exit_station_name.trim()
    if (filters.start_time) params.start_time = filters.start_time
    if (filters.end_time) params.end_time = filters.end_time
    if (filters.min_gantry_count !== '') params.min_gantry_count = Number(filters.min_gantry_count)
    if (filters.max_gantry_count !== '') params.max_gantry_count = Number(filters.max_gantry_count)
    params.order_by = filters.order_by
    params.order = filters.order
    return params
  }

  async function loadTrips() {
    setLoading(true)
    setError(null)
    try {
      const data = await auditApi.getRawVehicles(buildApiParams())
      setTrips(data.trips || [])
      setTotal(data.total || 0)
    } catch (e) {
      console.error('Failed to load raw vehicles:', e)
      setError(e.message || '加载失败')
      setTrips([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTrips()
  }, [page, limit, filters])  // 添加 filters 依赖，确保筛选条件变化时重新加载

  function search() {
    // 无论 page 是否为 0，都重置到第一页并重新加载数据
    setPage(0)
  }


  function reset() {
    setFilters({
      vehicle_id: '',
      vehicle_id_match: 'exact',
      obu_id: '',
      vehicle_type: '',
      vehicle_color: '',
      entry_station_name: '',
      exit_station_name: '',
      start_time: todayISO(0),
      end_time: todayISO(0),
      date_preset: 'today',
      min_gantry_count: '',
      max_gantry_count: '',
      order_by: 'entry_time',
      order: 'desc',
    })
    setPage(0)
    setTimeout(loadTrips, 0)
  }

  useEffect(() => {
    if (selectedPassid == null) {
      setSelectedDetail(null)
      return
    }
    let cancelled = false
    setDetailLoading(true)
    auditApi.getRawVehicleFull(selectedPassid)
      .then(data => { if (!cancelled) setSelectedDetail(data) })
      .catch(err => { console.error('Failed to load raw vehicle detail:', err) })
      .finally(() => { if (!cancelled) setDetailLoading(false) })
    return () => { cancelled = true }
  }, [selectedPassid])

  function toggleSort(col) {
    if (filters.order_by === col) {
      setFilters({ ...filters, order: filters.order === 'asc' ? 'desc' : 'asc' })
    } else {
      setFilters({ ...filters, order_by: col, order: 'desc' })
    }
    setPage(0)
    setTimeout(loadTrips, 0)
  }

  const stats = useMemo(() => {
    const withGantries = trips.filter(t => t.gantry_count > 0).length
    return { withGantries }
  }, [trips])

  function exportCSV() {
    const headerKeys = [
      'passid', 'entry_vehicle_id', 'entry_station_name', 'entry_time',
      'exit_vehicle_id', 'exit_station_name', 'exit_time',
      'entry_vehicle_type', 'gantry_count'
    ]
    const headerLabel = [
      'PASSID', '入口车牌', '入口站', '入口时间',
      '出口车牌', '出口站', '出口时间',
      '入口车型', '门架数'
    ]
    const escape = (v) => {
      const s = v == null ? '' : String(v)
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
    }
    const lines = [headerLabel.join(',')]
    for (const t of trips) {
      lines.push(headerKeys.map(k => escape(t[k])).join(','))
    }
    const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `vehicle-query-${todayISO(0)}.csv`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  const pageCount = Math.ceil(total / limit) || 1
  const sortIndicator = (col) => {
    if (filters.order_by !== col) return ''
    return filters.order === 'asc' ? ' ↑' : ' ↓'
  }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-group">
          <h2 className="page-title">车辆查询</h2>
          <span className="page-subtitle">原始通行数据 · 来源 Doris</span>
        </div>
        <div className="stats-strip">
          <div className="stat-mini">
            <span className="stat-mini-icon">📊</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{total}</span>
              <span className="stat-mini-label">命中数</span>
            </div>
          </div>
          <div className="stat-mini">
            <span className="stat-mini-icon">🛣️</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{stats.withGantries}</span>
              <span className="stat-mini-label">含门架数</span>
            </div>
          </div>
        </div>
      </div>

      <div className="filter-section">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', width: '100%' }}>
          <div className="filter-group">
            <span className="filter-label">车牌:</span>
            <input
              className="filter-select"
              placeholder="如 川A00001"
              value={filters.vehicle_id}
              onChange={(e) => setFilters({ ...filters, vehicle_id: e.target.value })}
              style={{ minWidth: 140 }}
            />
          </div>
          <div className="filter-group">
            <span className="filter-label">匹配:</span>
            <select
              className="filter-select"
              value={filters.vehicle_id_match}
              onChange={(e) => setFilters({ ...filters, vehicle_id_match: e.target.value })}
            >
              <option value="exact">精确</option>
              <option value="prefix">前缀</option>
              <option value="contains">包含</option>
            </select>
          </div>
          <div className="filter-group">
            <span className="filter-label">OBU ID:</span>
            <input
              className="filter-select"
              placeholder="OBU编号"
              value={filters.obu_id}
              onChange={(e) => setFilters({ ...filters, obu_id: e.target.value })}
              style={{ minWidth: 140 }}
            />
          </div>
          <div className="filter-group">
            <span className="filter-label">车型:</span>
            <select
              className="filter-select"
              value={filters.vehicle_type}
              onChange={(e) => setFilters({ ...filters, vehicle_type: e.target.value })}
            >
              <option value="">全部</option>
              <option value="1">客车</option>
              <option value="2">货车</option>
            </select>
          </div>
          <div className="filter-group">
            <span className="filter-label">颜色:</span>
            <select
              className="filter-select"
              value={filters.vehicle_color}
              onChange={(e) => setFilters({ ...filters, vehicle_color: e.target.value })}
            >
              <option value="">全部</option>
              {COLOR_LABELS.map((label, i) => (
                <option key={i} value={i}>{label}</option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            <span className="filter-label">入口站:</span>
            <input
              className="filter-select"
              placeholder="站点名称"
              value={filters.entry_station_name}
              onChange={(e) => setFilters({ ...filters, entry_station_name: e.target.value })}
            />
          </div>
          <div className="filter-group">
            <span className="filter-label">出口站:</span>
            <input
              className="filter-select"
              placeholder="站点名称"
              value={filters.exit_station_name}
              onChange={(e) => setFilters({ ...filters, exit_station_name: e.target.value })}
            />
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', width: '100%', marginTop: '0.5rem', alignItems: 'center' }}>
          <div className="filter-group">
            <span className="filter-label">日期:</span>
            {['today', 'last7', 'last30', 'custom'].map(p => (
              <button
                key={p}
                type="button"
                className={`btn btn-sm ${filters.date_preset === p ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setDatePreset(p)}
                style={{ marginRight: 4, padding: '0.2rem 0.6rem', fontSize: '0.75rem' }}
              >
                {p === 'today' ? '今天' : p === 'last7' ? '近7天' : p === 'last30' ? '近30天' : '自定义'}
              </button>
            ))}
          </div>
          <div className="filter-group">
            <input
              type="date"
              className="filter-select"
              value={filters.start_time}
              onChange={(e) => setFilters({ ...filters, start_time: e.target.value, date_preset: 'custom' })}
            />
            <span style={{ margin: '0 0.25rem', color: 'var(--text-tertiary)' }}>~</span>
            <input
              type="date"
              className="filter-select"
              value={filters.end_time}
              onChange={(e) => setFilters({ ...filters, end_time: e.target.value, date_preset: 'custom' })}
            />
          </div>
          <div className="filter-group">
            <span className="filter-label">门架数:</span>
            <input
              type="number" min="0" step="1"
              className="filter-select" style={{ width: 70 }}
              placeholder="min" value={filters.min_gantry_count}
              onChange={(e) => setFilters({ ...filters, min_gantry_count: e.target.value })}
            />
            <span style={{ margin: '0 0.25rem', color: 'var(--text-tertiary)' }}>~</span>
            <input
              type="number" min="0" step="1"
              className="filter-select" style={{ width: 70 }}
              placeholder="max" value={filters.max_gantry_count}
              onChange={(e) => setFilters({ ...filters, max_gantry_count: e.target.value })}
            />
          </div>
          <div className="filter-group">
            <span className="filter-label">排序:</span>
            <select
              className="filter-select"
              value={filters.order_by}
              onChange={(e) => { setFilters({ ...filters, order_by: e.target.value }); setPage(0); setTimeout(loadTrips, 0) }}
            >
              <option value="entry_time">入口时间</option>
              <option value="exit_time">出口时间</option>
              <option value="gantry_count">门架数</option>
            </select>
            <select
              className="filter-select"
              value={filters.order}
              onChange={(e) => { setFilters({ ...filters, order: e.target.value }); setPage(0); setTimeout(loadTrips, 0) }}
              style={{ marginLeft: 4 }}
            >
              <option value="desc">降序</option>
              <option value="asc">升序</option>
            </select>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
            <button className="btn btn-primary" onClick={search} disabled={loading}>
              🔍 搜索
            </button>
            <button className="btn btn-secondary" onClick={reset} disabled={loading}>
              🔄 重置
            </button>
            <button className="btn btn-secondary" onClick={exportCSV} disabled={loading || trips.length === 0}>
              📥 导出 CSV
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: 12 }}>
          加载失败：{error} <button className="btn btn-sm btn-secondary" onClick={loadTrips}>重试</button>
        </div>
      )}

      <div className="content-area">
        <div className="table-panel" style={{ flex: selectedDetail ? 2 : 1 }}>
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th style={{width: '120px'}}>PASSID</th>
                  <th style={{width: '90px'}}>入口车牌</th>
                  <th style={{width: '80px'}}>入口站</th>
                  <th style={{width: '130px', cursor: 'pointer'}} onClick={() => toggleSort('entry_time')}>
                    入口时间{sortIndicator('entry_time')}
                  </th>
                  <th style={{width: '90px'}}>出口车牌</th>
                  <th style={{width: '80px'}}>出口站</th>
                  <th style={{width: '130px', cursor: 'pointer'}} onClick={() => toggleSort('exit_time')}>
                    出口时间{sortIndicator('exit_time')}
                  </th>
                  <th style={{width: '70px'}}>车型</th>
                  <th style={{width: '80px', cursor: 'pointer'}} onClick={() => toggleSort('gantry_count')}>
                    门架数{sortIndicator('gantry_count')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={9} style={{textAlign: 'center', padding: '2rem'}}>
                      <span className="loading-spinner"></span> 加载中...
                    </td>
                  </tr>
                ) : trips.length === 0 ? (
                  <tr>
                    <td colSpan={9}>
                      <div className="empty-state">
                        <div className="empty-state-icon">🔎</div>
                        <div className="empty-state-title">无匹配结果</div>
                        <div className="empty-state-text">请调整筛选条件或扩大日期范围</div>
                      </div>
                    </td>
                  </tr>
                ) : (
                  trips.map(t => (
                    <tr
                      key={t.passid}
                      onClick={() => setSelectedPassid(t.passid)}
                      style={{
                        cursor: 'pointer',
                        background: selectedPassid === t.passid ? 'var(--accent-blue-bg)' : undefined
                      }}
                    >
                      <td><span className="mono">{t.passid}</span></td>
                      <td><span style={{fontWeight: 500}}>{t.entry_vehicle_id || '-'}</span></td>
                      <td><span style={{fontSize: '0.75rem'}}>{t.entry_station_name || '-'}</span></td>
                      <td><span className="mono" style={{fontSize: '0.7rem'}}>{formatTime(t.entry_time)}</span></td>
                      <td><span style={{fontWeight: 500}}>{t.exit_vehicle_id || '-'}</span></td>
                      <td><span style={{fontSize: '0.75rem'}}>{t.exit_station_name || '-'}</span></td>
                      <td><span className="mono" style={{fontSize: '0.7rem'}}>{formatTime(t.exit_time)}</span></td>
                      <td>
                        <span style={{
                          padding: '0.2rem 0.5rem',
                          borderRadius: 4,
                          fontSize: '0.75rem',
                          background: t.entry_vehicle_type === 1 ? 'var(--accent-green-bg)' : 'var(--accent-amber-bg)',
                          color: t.entry_vehicle_type === 1 ? 'var(--accent-green)' : 'var(--accent-amber)'
                        }}>
                          {VEHICLE_TYPE_LABEL[t.entry_vehicle_type] || t.entry_vehicle_type || '-'}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${t.gantry_count > 0 ? 'badge-info' : ''}`} style={{
                          background: t.gantry_count > 0 ? 'var(--accent-blue-bg)' : 'var(--bg-tertiary)',
                          color: t.gantry_count > 0 ? 'var(--accent-blue)' : 'var(--text-tertiary)',
                          fontSize: '0.7rem'
                        }}>
                          {t.gantry_count || 0}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <div className="pagination-info">
              共 {total} 条，第 {page + 1} / {pageCount} 页
              <select
                className="filter-select"
                style={{ marginLeft: 12, padding: '0.2rem 0.4rem' }}
                value={limit}
                onChange={(e) => { setLimit(Number(e.target.value)); setPage(0) }}
              >
                {PAGE_SIZE_OPTIONS.map(n => <option key={n} value={n}>{n}/页</option>)}
              </select>
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
                onClick={() => setPage(p => (p + 1) < pageCount ? p + 1 : p)}
                disabled={(page + 1) >= pageCount}
              >
                下一页 ▶
              </button>
            </div>
          </div>
        </div>

        {selectedPassid != null && (
          <div className="detail-panel" style={{ width: 480 }}>
            <div className="detail-header">
              <div>
                <div className="detail-title">行程详情</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginTop: 2 }}>
                  {selectedPassid}
                </div>
              </div>
              <button className="detail-close" onClick={() => setSelectedPassid(null)}>✕</button>
            </div>
            <div className="detail-body">
              {detailLoading ? (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                  <span className="loading-spinner"></span> 加载详情中...
                </div>
              ) : !selectedDetail ? (
                <div className="empty-state">未找到详情</div>
              ) : (
                <VehicleTripDetail trip={selectedDetail} />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default VehicleQuery
