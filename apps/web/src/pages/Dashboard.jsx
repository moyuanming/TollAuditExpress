import React, { useState, useEffect, useRef } from 'react'
import { auditApi } from '../api/audit'
import Icon from '../components/Icon'

function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [aggregating, setAggregating] = useState(false)
  const [progress, setProgress] = useState(null)
  const timerRef = useRef(null)

  useEffect(() => {
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [])

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
    setProgress(null)
    try {
      const result = await auditApi.aggregateTrips({ days: 7, limit: 100 })
      const poll = async () => {
        try {
          const status = await auditApi.getAggregationStatus(result.task_id)
          setProgress(status)
          if (status.status === 'completed' || status.status === 'stopped' || status.status === 'error' || status.status === 'not_found') {
            setAggregating(false)
            if (status.status === 'completed') loadStats()
          } else {
            timerRef.current = setTimeout(poll, 1000)
          }
        } catch (e) {
          setProgress({ status: 'error', message: '无法获取聚合状态' })
          setAggregating(false)
        }
      }
      poll()
    } catch (e) {
      console.error('Failed to start aggregation:', e)
      setProgress({ status: 'error', message: '启动聚合失败' })
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
        <div className="toolbar-actions">
          <button className="btn btn-secondary" onClick={loadStats}>
            <Icon name="refresh" />刷新
          </button>
          <button
            className="btn btn-primary"
            onClick={startAggregation}
            disabled={aggregating}
          >
            {aggregating ? <><Icon name="loader" className="spin" />聚合中...</> : <><Icon name="play" />启动聚合</>}
          </button>
        </div>
      </div>

      <div className="stats-strip">
        <div className="stat-mini">
          <span className="stat-mini-icon"><Icon name="route" /></span>
          <div className="stat-mini-content">
            <span className="stat-mini-value">{stats?.total_trips || 0}</span>
            <span className="stat-mini-label">行程总量</span>
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
        <div className="table-panel flex-1">
          <div className="panel-section-header">
            <Icon name="git-branch" /><span>双模型检测流水线</span>
          </div>

          <div className="pipeline-grid">
            {/* Model A */}
            <div className="pipeline-card">
              <div className="pipeline-card-header pipeline-card-header-purple">
                <Icon name="bus" size="lg" />
                <span className="pipeline-card-title">模型A: 货车套用客车OBU</span>
              </div>
              <div className="pipeline-card-body">
                <div className="mb-4">
                  <div className="pipeline-subsection-label">检测逻辑</div>
                  <div className="pipeline-subsection-text">
                    检测交易记录为<strong className="text-success">客车</strong>，
                    但图片视觉识别为<strong className="text-danger">货车</strong>的情况。
                  </div>
                </div>
                <div className="flex-col gap-2">
                  <div className="pipeline-step">
                    <Icon name="chevron-right" className="text-info" size="sm" />
                    <span>获取交易记录 (LANETYPE=入口)</span>
                  </div>
                  <div className="pipeline-step">
                    <Icon name="chevron-right" className="text-info" size="sm" />
                    <span>下载 _trans.jpg 车辆图片</span>
                  </div>
                  <div className="pipeline-step">
                    <Icon name="chevron-right" className="text-info" size="sm" />
                    <span>VehicleClassifier 视觉识别</span>
                  </div>
                  <div className="pipeline-step">
                    <Icon name="chevron-right" className="text-info" size="sm" />
                    <span>输出风险评分和稽核结果</span>
                  </div>
                </div>
                <div className="pipeline-judge">
                  <strong>判断标准:</strong> 交易车型=客车 且 视觉识别=货车 → 可疑
                </div>
              </div>
            </div>

            {/* Model B */}
            <div className="pipeline-card">
              <div className="pipeline-card-header pipeline-card-header-blue">
                <Icon name="route" size="lg" />
                <span className="pipeline-card-title">模型B: 出入口车辆比对</span>
              </div>
              <div className="pipeline-card-body">
                <div className="mb-4">
                  <div className="pipeline-subsection-label">检测逻辑</div>
                  <div className="pipeline-subsection-text">
                    比对出入口车辆<strong className="text-info">颜色</strong>、
                    <strong className="text-info">车型</strong>和
                    <strong className="text-info">车纹</strong>相似度。
                  </div>
                </div>
                <div className="flex-col gap-2">
                  <div className="pipeline-step">
                    <Icon name="chevron-right" className="text-info" size="sm" />
                    <span>下载入口/出口 _license.jpg</span>
                  </div>
                  <div className="pipeline-step">
                    <Icon name="chevron-right" className="text-info" size="sm" />
                    <span>HSV 颜色主色调分析</span>
                  </div>
                  <div className="pipeline-step">
                    <Icon name="chevron-right" className="text-info" size="sm" />
                    <span>VehicleClassifier 车型比对</span>
                  </div>
                  <div className="pipeline-step">
                    <Icon name="chevron-right" className="text-info" size="sm" />
                    <span>ResNet50 车纹特征提取 + 余弦相似度</span>
                  </div>
                </div>
                <div className="pipeline-judge">
                  <strong>判断标准:</strong> 颜色不一致 或 车型不一致 或 车纹相似度 &lt; 60% → 可疑
                </div>
              </div>
            </div>
          </div>

          {progress && (
            <div className="panel-section-body">
              {progress.status === 'error' ? (
                <div className="text-danger flex-row items-center gap-2">
                  <Icon name="x-circle" />聚合失败: {progress.message || '未知错误'}
                </div>
              ) : progress.status === 'not_found' ? (
                <div className="text-secondary">未找到聚合任务</div>
              ) : (
                <>
                  <div className="flex-row items-center justify-between mb-3">
                    <span className="font-semibold flex-row items-center gap-2">
                      {progress.status === 'completed'
                        ? <><Icon name="check" className="text-success" />聚合完成</>
                        : <><Icon name="loader" className="spin text-info" />聚合进行中</>}
                    </span>
                    <span className="text-sm text-secondary">
                      {progress.total > 0
                        ? `${progress.current || 0} / ${progress.total || 0} 条`
                        : '正在查询源数据库...'}
                    </span>
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{ width: `${((progress.current || 0) / (progress.total || 1)) * 100}%` }}
                    />
                  </div>
                  <div className="mt-3 flex-row gap-4 text-sm">
                    <span className="text-success">已处理: {progress.count || 0}</span>
                    <span>当前: {progress.passid || '-'}</span>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Dashboard
