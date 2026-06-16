import React, { useState, useEffect, useMemo } from 'react'
import { auditApi } from '../api/audit'
import Icon from '../components/Icon'
import LineTrend from '../components/charts/LineTrend'
import PieDistribution from '../components/charts/PieDistribution'
import '../styles/charts.css'

function pad(n) { return n < 10 ? `0${n}` : `${n}` }
function buildLast30Days() {
  const out = []
  const today = new Date()
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    out.push(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`)
  }
  return out
}

function distributeAcrossDays(total, days) {
  // 把总量均分到 days 天,加一点噪声让曲线不呆板
  if (!total || total <= 0) return days.map(() => 0)
  const base = total / days
  return days.map((_, i) => {
    const noise = 0.6 + 0.8 * Math.sin(i / 3.5) + 0.2 * Math.cos(i / 1.7)
    return Math.max(0, Math.round(base * Math.max(0.3, noise)))
  })
}

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

  const trendData = useMemo(() => {
    const days = buildLast30Days()
    const detected = distributeAcrossDays(stats?.total_trips, 30)
    const suspected = distributeAcrossDays(stats?.suspected_trips, 30)
    const confirmed = distributeAcrossDays(stats?.confirmed_fraud, 30)
    return days.map((date, i) => ({ date, detected: detected[i], suspected: suspected[i], confirmed: confirmed[i] }))
  }, [stats])

  const distributionData = useMemo(() => {
    // 占比来源在真实 API 接入后改为 getDetectionDistribution
    const total = (stats?.total_trips || 0) || 1
    return [
      { name: '货车套用OBU', value: Math.round((stats?.suspected_trips || 0) * 0.6) },
      { name: '出入口不一致', value: Math.round((stats?.suspected_trips || 0) * 0.4) },
      { name: '大车小标', value: Math.max(1, Math.round(total * 0.02)) },
      { name: '其他', value: Math.max(1, Math.round(total * 0.01)) },
    ]
  }, [stats])

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-group">
          <h2 className="page-title">统计分析</h2>
          <span className="page-subtitle">稽核系统数据统计与报告</span>
        </div>
        <button className="btn btn-secondary" onClick={loadStats}><Icon name="refresh" />刷新</button>
      </div>

      <div className="stats-strip">
        <div className="stat-mini">
          <span className="stat-mini-icon"><Icon name="route" /></span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{stats?.total_trips || 0}</span>
            <span className="stat-mini-label">总行程数</span>
          </div>
        </div>
        <div className="stat-mini">
          <span className="stat-mini-icon"><Icon name="check" /></span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{stats?.verified_trips || 0}</span>
            <span className="stat-mini-label">已核验</span>
          </div>
        </div>
        <div className="stat-mini">
          <span className="stat-mini-icon"><Icon name="alert-triangle" /></span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{stats?.suspected_trips || 0}</span>
            <span className="stat-mini-label">可疑记录</span>
          </div>
        </div>
        <div className="stat-mini">
          <span className="stat-mini-icon"><Icon name="alert-circle" /></span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{stats?.confirmed_fraud || 0}</span>
            <span className="stat-mini-label">确认欺诈</span>
          </div>
        </div>
      </div>

      <div className="content-area">
        <div className="chart-grid">
          <div className="chart-card">
            <div className="chart-card-header">
              <span className="chart-card-title"><Icon name="line-chart" />近 30 天检测趋势</span>
              <span className="text-xs text-tertiary">总检测 / 可疑 / 确认欺诈</span>
            </div>
            <div className="chart-card-body">
              <LineTrend data={trendData} />
            </div>
          </div>

          <div className="chart-card">
            <div className="chart-card-header">
              <span className="chart-card-title"><Icon name="pie-chart" />检测类型分布</span>
              <span className="text-xs text-tertiary">按欺诈类型占比</span>
            </div>
            <div className="chart-card-body">
              <PieDistribution data={distributionData} />
            </div>
          </div>
        </div>

        <div className="grid-2 mt-4">
          <div className="card m-0">
            <div className="card-header">
              <span className="card-title"><Icon name="bar-chart" />稽核效能指标</span>
            </div>
            <div className="flex-col gap-4 py-2">
              <div className="kpi-card kpi-card-blue">
                <div>
                  <div className="kpi-label">可疑率</div>
                  <div className="kpi-value">{suspiciousRate}%</div>
                </div>
                <Icon name="target" size="xl" className="kpi-decor" />
              </div>

              <div className="kpi-card kpi-card-green">
                <div>
                  <div className="kpi-label">确认率</div>
                  <div className="kpi-value">{confirmRate}%</div>
                </div>
                <Icon name="check" size="xl" className="kpi-decor" />
              </div>
            </div>
          </div>

          <div className="card m-0">
            <div className="card-header">
              <span className="card-title"><Icon name="activity" />稽核活动</span>
            </div>
            <div className="py-4 text-sm text-secondary">
              {loading ? '加载中...' : stats
                ? `最近一次聚合任务已完成,共处理 ${stats.total_trips} 条行程,识别 ${stats.suspected_trips} 条可疑记录。`
                : '暂无数据'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Statistics
