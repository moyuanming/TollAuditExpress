import React, { useState, useEffect } from 'react'
import { auditApi } from '../api/audit'

function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [aggregating, setAggregating] = useState(false)
  const [progress, setProgress] = useState(null)

  useEffect(() => {
    loadStats()
  }, [])

  async function loadStats() {
    try {
      const data = await auditApi.getStats()
      setStats(data)
    } catch (e) {
      console.error('Failed to load stats:', e)
    } finally {
      setLoading(false)
    }
  }

  async function startAggregation() {
    setAggregating(true)
    try {
      const result = await auditApi.aggregateTrips({ days: 7, limit: 100 })
      const interval = setInterval(async () => {
        try {
          const status = await fetch(`/api/audit/trips/aggregate/${result.task_id}`).then(r => r.json())
          setProgress(status)
          if (status.status === 'completed' || status.status === 'stopped') {
            clearInterval(interval)
            setAggregating(false)
            loadStats()
          }
        } catch (e) {
          clearInterval(interval)
          setAggregating(false)
        }
      }, 1000)
    } catch (e) {
      console.error('Failed to start aggregation:', e)
      setAggregating(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-group">
          <h2 className="page-title">仪表盘</h2>
          <span className="page-subtitle">实时监控高速公路收费稽核情况</span>
        </div>
        <div style={{display: 'flex', gap: '0.75rem'}}>
          <button className="btn btn-secondary" onClick={loadStats}>
            🔄 刷新
          </button>
          <button 
            className="btn btn-primary" 
            onClick={startAggregation}
            disabled={aggregating}
          >
            {aggregating ? '⏳ 聚合中...' : '🚀 启动聚合'}
          </button>
        </div>
      </div>

      <div className="stats-strip">
        <div className="stat-mini">
          <span className="stat-mini-icon">🚗</span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{stats?.total_trips || 0}</span>
            <span className="stat-mini-label">行程总量</span>
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
        <div className="table-panel" style={{flex: 1}}>
          <div style={{padding: '1rem', borderBottom: '1px solid var(--border-primary)'}}>
            <span style={{fontWeight: 600, fontSize: '0.95rem'}}>🔍 双模型检测流水线</span>
          </div>
          
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', padding: '1rem'}}>
            {/* Model A */}
            <div style={{
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-lg)',
              overflow: 'hidden'
            }}>
              <div style={{
                padding: '0.75rem 1rem',
                background: 'var(--accent-purple-bg)',
                borderBottom: '1px solid var(--border-primary)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}>
                <span style={{fontSize: '1.25rem'}}>🚛</span>
                <span style={{fontWeight: 600, color: 'var(--accent-purple)'}}>模型A: 货车套用客车OBU</span>
              </div>
              <div style={{padding: '1rem'}}>
                <div style={{marginBottom: '1rem'}}>
                  <div style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.5rem'}}>检测逻辑</div>
                  <div style={{fontSize: '0.875rem', lineHeight: 1.6}}>
                    检测交易记录为<strong style={{color: 'var(--accent-green)'}}>客车</strong>，
                    但图片视觉识别为<strong style={{color: 'var(--accent-red)'}}>货车</strong>的情况。
                  </div>
                </div>
                <div style={{display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
                  <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                    <span style={{color: 'var(--accent-purple)'}}>▸</span>
                    <span style={{fontSize: '0.85rem'}}>获取交易记录 (LANETYPE=入口)</span>
                  </div>
                  <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                    <span style={{color: 'var(--accent-purple)'}}>▸</span>
                    <span style={{fontSize: '0.85rem'}}>下载 _trans.jpg 车辆图片</span>
                  </div>
                  <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                    <span style={{color: 'var(--accent-purple)'}}>▸</span>
                    <span style={{fontSize: '0.85rem'}}>VehicleClassifier 视觉识别</span>
                  </div>
                  <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                    <span style={{color: 'var(--accent-purple)'}}>▸</span>
                    <span style={{fontSize: '0.85rem'}}>输出风险评分和稽核结果</span>
                  </div>
                </div>
                <div style={{
                  marginTop: '1rem',
                  padding: '0.75rem',
                  background: 'var(--bg-secondary)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.8rem',
                  color: 'var(--text-secondary)'
                }}>
                  <strong>判断标准:</strong> 交易车型=客车 且 视觉识别=货车 → 可疑
                </div>
              </div>
            </div>

            {/* Model B */}
            <div style={{
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-lg)',
              overflow: 'hidden'
            }}>
              <div style={{
                padding: '0.75rem 1rem',
                background: 'var(--accent-blue-bg)',
                borderBottom: '1px solid var(--border-primary)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}>
                <span style={{fontSize: '1.25rem'}}>🚗</span>
                <span style={{fontWeight: 600, color: 'var(--accent-blue)'}}>模型B: 出入口车辆比对</span>
              </div>
              <div style={{padding: '1rem'}}>
                <div style={{marginBottom: '1rem'}}>
                  <div style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.5rem'}}>检测逻辑</div>
                  <div style={{fontSize: '0.875rem', lineHeight: 1.6}}>
                    比对出入口车辆<strong style={{color: 'var(--accent-blue)'}}>颜色</strong>、
                    <strong style={{color: 'var(--accent-blue)'}}>车型</strong>和
                    <strong style={{color: 'var(--accent-blue)'}}>车纹</strong>相似度。
                  </div>
                </div>
                <div style={{display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
                  <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                    <span style={{color: 'var(--accent-blue)'}}>▸</span>
                    <span style={{fontSize: '0.85rem'}}>下载入口/出口 _license.jpg</span>
                  </div>
                  <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                    <span style={{color: 'var(--accent-blue)'}}>▸</span>
                    <span style={{fontSize: '0.85rem'}}>HSV 颜色主色调分析</span>
                  </div>
                  <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                    <span style={{color: 'var(--accent-blue)'}}>▸</span>
                    <span style={{fontSize: '0.85rem'}}>VehicleClassifier 车型比对</span>
                  </div>
                  <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                    <span style={{color: 'var(--accent-blue)'}}>▸</span>
                    <span style={{fontSize: '0.85rem'}}>ResNet50 车纹特征提取 + 余弦相似度</span>
                  </div>
                </div>
                <div style={{
                  marginTop: '1rem',
                  padding: '0.75rem',
                  background: 'var(--bg-secondary)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.8rem',
                  color: 'var(--text-secondary)'
                }}>
                  <strong>判断标准:</strong> 颜色不一致 或 车型不一致 或 车纹相似度 &lt; 60% → 可疑
                </div>
              </div>
            </div>
          </div>

          {progress && (
            <div style={{padding: '1rem', borderTop: '1px solid var(--border-primary)'}}>
              <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem'}}>
                <span style={{fontWeight: 600}}>
                  {progress.status === 'completed' ? '✅ 聚合完成' : '🔄 聚合进行中'}
                </span>
                <span style={{fontSize: '0.85rem', color: 'var(--text-secondary)'}}>
                  {progress.current || 0} / {progress.total || 0} 条
                </span>
              </div>
              <div className="progress-bar">
                <div 
                  className="progress-fill"
                  style={{ width: `${((progress.current || 0) / (progress.total || 1)) * 100}%` }}
                />
              </div>
              <div style={{marginTop: '0.75rem', display: 'flex', gap: '2rem', fontSize: '0.85rem'}}>
                <span style={{color: 'var(--accent-green)'}}>已处理: {progress.count || 0}</span>
                <span>当前: {progress.passid || '-'}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Dashboard
