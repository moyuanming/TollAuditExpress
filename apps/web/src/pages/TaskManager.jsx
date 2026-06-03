import React, { useState, useEffect, useRef } from 'react'
import { taskApi } from '../api/audit'

const TASK_TYPES = {
  aggregate_detect: '聚合+检测',
  detect_only: '仅检测',
  re_detect: '补检测'
}

function TaskManager() {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingTask, setEditingTask] = useState(null)
  const [expandedTask, setExpandedTask] = useState(null)
  const [executions, setExecutions] = useState({})
  const [executingTasks, setExecutingTasks] = useState({})
  const pollTimerRef = useRef(null)
  const [form, setForm] = useState({
    name: '',
    description: '',
    task_type: 'aggregate_detect',
    filter_rules: { exit_station: '', entry_station: '', days: 3, limit: 500 },
    schedule_type: 'interval',
    schedule_config: { minutes: 60 }
  })

  useEffect(() => {
    loadTasks()
    return () => { if (pollTimerRef.current) clearTimeout(pollTimerRef.current) }
  }, [])

  async function loadTasks() {
    try {
      const data = await taskApi.getTasks()
      setTasks(data.tasks || [])
    } catch (e) {
      console.error('Failed to load tasks:', e)
    } finally {
      setLoading(false)
    }
  }

  function openCreateForm() {
    setEditingTask(null)
    setForm({
      name: '',
      description: '',
      task_type: 'aggregate_detect',
      filter_rules: { exit_station: '', entry_station: '', days: 3, limit: 500 },
      schedule_type: 'interval',
      schedule_config: { minutes: 60 }
    })
    setShowForm(true)
  }

  function openEditForm(task) {
    setEditingTask(task)
    let rules = {}
    try {
      rules = typeof task.filter_rules === 'string' ? JSON.parse(task.filter_rules) : (task.filter_rules || {})
    } catch (e) {}
    let config = {}
    try {
      config = typeof task.schedule_config === 'string' ? JSON.parse(task.schedule_config) : (task.schedule_config || {})
    } catch (e) {}
    setForm({
      name: task.name,
      description: task.description || '',
      task_type: task.task_type,
      filter_rules: {
        exit_station: rules.exit_station || '',
        entry_station: rules.entry_station || '',
        days: rules.days || 3,
        limit: rules.limit || 500
      },
      schedule_type: task.schedule_type || 'interval',
      schedule_config: {
        minutes: config.minutes || 60
      }
    })
    setShowForm(true)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const data = {
      name: form.name,
      description: form.description || null,
      task_type: form.task_type,
      filter_rules: form.filter_rules,
      schedule_type: form.schedule_type,
      schedule_config: form.schedule_config
    }

    try {
      if (editingTask) {
        await taskApi.updateTask(editingTask.id, data)
      } else {
        await taskApi.createTask(data)
      }
      setShowForm(false)
      loadTasks()
    } catch (e) {
      console.error('Failed to save task:', e)
    }
  }

  async function handleDelete(taskId) {
    if (!confirm('确定删除此任务？')) return
    try {
      await taskApi.deleteTask(taskId)
      loadTasks()
    } catch (e) {
      console.error('Failed to delete task:', e)
    }
  }

  async function handleExecute(taskId) {
    try {
      const result = await taskApi.executeTask(taskId)
      // Automatically expand execution history & mark as executing
      setExpandedTask(taskId)
      setExecutingTasks(prev => ({ ...prev, [taskId]: true }))
      // Load executions to show the new "运行中" row
      const data = await taskApi.getTaskExecutions(taskId)
      setExecutions(prev => ({ ...prev, [taskId]: data.executions || [] }))
      // Start polling for completion
      pollExecution(taskId)
      loadTasks()
    } catch (e) {
      console.error('Failed to execute task:', e)
    }
  }

  function pollExecution(taskId) {
    pollTimerRef.current = setTimeout(async () => {
      try {
        const data = await taskApi.getTaskExecutions(taskId)
        setExecutions(prev => ({ ...prev, [taskId]: data.executions || [] }))
        // Check if latest execution is still running
        const latest = (data.executions || [])[0]
        if (latest && latest.status === 'running') {
          pollExecution(taskId)
        } else {
          setExecutingTasks(prev => ({ ...prev, [taskId]: false }))
          loadTasks()
        }
      } catch (e) {
        setExecutingTasks(prev => ({ ...prev, [taskId]: false }))
      }
    }, 2000)
  }

  async function handleToggleEnabled(task) {
    try {
      await taskApi.updateTask(task.id, { enabled: !task.enabled })
      loadTasks()
    } catch (e) {
      console.error('Failed to toggle task:', e)
    }
  }

  async function toggleExecutions(taskId) {
    if (expandedTask === taskId) {
      setExpandedTask(null)
      return
    }
    setExpandedTask(taskId)
    try {
      const data = await taskApi.getTaskExecutions(taskId)
      setExecutions(prev => ({ ...prev, [taskId]: data.executions || [] }))
    } catch (e) {
      console.error('Failed to load executions:', e)
    }
  }

  function formatTime(t) {
    if (!t) return '—'
    return t.replace('T', ' ').substring(0, 19)
  }

  function describeSchedule(task) {
    let config = {}
    try {
      config = typeof task.schedule_config === 'string' ? JSON.parse(task.schedule_config) : task.schedule_config
    } catch (e) {}
    if (task.schedule_type === 'interval') {
      const m = config.minutes || 60
      if (m < 60) return `每${m}分钟`
      return `每${m / 60}小时`
    }
    return config.cron || '自定义'
  }

  function describeFilter(task) {
    let rules = {}
    try {
      rules = typeof task.filter_rules === 'string' ? JSON.parse(task.filter_rules) : (task.filter_rules || {})
    } catch (e) {}
    const parts = []
    if (rules.exit_station) parts.push(`出口:${rules.exit_station}`)
    if (rules.entry_station) parts.push(`入口:${rules.entry_station}`)
    if (rules.days) parts.push(`${rules.days}天`)
    if (rules.limit) parts.push(`限${rules.limit}条`)
    return parts.length > 0 ? parts.join(' ') : '默认'
  }

  if (loading) return <div className="page"><div className="loading">加载中...</div></div>

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h2>定时任务</h2>
          <p className="page-subtitle">管理自动化监测任务</p>
        </div>
        <button className="btn btn-primary" onClick={openCreateForm}>+ 新建任务</button>
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>{editingTask ? '编辑任务' : '新建任务'}</h3>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>任务名称 *</label>
                <input
                  type="text"
                  className="input"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder="例如：甘泉堡每日监测"
                  required
                />
              </div>
              <div className="form-group">
                <label>描述</label>
                <input
                  type="text"
                  className="input"
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="任务用途说明"
                />
              </div>
              <div className="form-group">
                <label>任务类型</label>
                <select
                  className="input"
                  value={form.task_type}
                  onChange={e => setForm({ ...form, task_type: e.target.value })}
                >
                  <option value="aggregate_detect">聚合+检测</option>
                  <option value="detect_only">仅检测</option>
                  <option value="re_detect">补检测</option>
                </select>
              </div>

              <h4 className="form-section-title">筛选规则</h4>
              <div className="form-row">
                <div className="form-group">
                  <label>出口站</label>
                  <input
                    type="text"
                    className="input"
                    value={form.filter_rules.exit_station}
                    onChange={e => setForm({ ...form, filter_rules: { ...form.filter_rules, exit_station: e.target.value } })}
                    placeholder="如：甘泉堡匝道站"
                  />
                </div>
                <div className="form-group">
                  <label>入口站</label>
                  <input
                    type="text"
                    className="input"
                    value={form.filter_rules.entry_station}
                    onChange={e => setForm({ ...form, filter_rules: { ...form.filter_rules, entry_station: e.target.value } })}
                    placeholder="如：乌拉泊"
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>天数</label>
                  <input
                    type="number"
                    className="input"
                    value={form.filter_rules.days}
                    onChange={e => setForm({ ...form, filter_rules: { ...form.filter_rules, days: parseInt(e.target.value) || 3 } })}
                    min="1"
                    max="30"
                  />
                </div>
                <div className="form-group">
                  <label>条数限制</label>
                  <input
                    type="number"
                    className="input"
                    value={form.filter_rules.limit}
                    onChange={e => setForm({ ...form, filter_rules: { ...form.filter_rules, limit: parseInt(e.target.value) || 500 } })}
                    min="10"
                    max="5000"
                  />
                </div>
              </div>

              <h4 className="form-section-title">调度设置</h4>
              <div className="form-group">
                <label>调度类型</label>
                <select
                  className="input"
                  value={form.schedule_type}
                  onChange={e => setForm({ ...form, schedule_type: e.target.value })}
                >
                  <option value="interval">间隔执行</option>
                </select>
              </div>
              {form.schedule_type === 'interval' && (
                <div className="form-group">
                  <label>间隔（分钟）</label>
                  <input
                    type="number"
                    className="input"
                    value={form.schedule_config.minutes}
                    onChange={e => setForm({ ...form, schedule_config: { minutes: parseInt(e.target.value) || 60 } })}
                    min="5"
                    max="1440"
                  />
                  <span className="form-hint">最小5分钟，最大1440分钟（24小时）</span>
                </div>
              )}

              <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>取消</button>
                <button type="submit" className="btn btn-primary">{editingTask ? '保存' : '创建'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {tasks.length === 0 ? (
        <div className="empty-state">
          <p>暂无定时任务</p>
          <p className="text-secondary">点击"新建任务"创建第一个监测任务</p>
        </div>
      ) : (
        <div className="task-list">
          {tasks.map(task => (
            <div key={task.id} className={`task-card ${!task.enabled ? 'task-disabled' : ''}`}>
              <div className="task-card-header">
                <div className="task-card-title">
                  <span className={`task-type-badge type-${task.task_type}`}>
                    {TASK_TYPES[task.task_type] || task.task_type}
                  </span>
                  <strong>{task.name}</strong>
                  {task.description && <span className="task-desc">{task.description}</span>}
                </div>
                <div className="task-card-actions">
                  <button
                    className={`btn btn-sm ${task.enabled ? 'btn-success' : 'btn-secondary'}`}
                    onClick={() => handleToggleEnabled(task)}
                  >
                    {task.enabled ? '已启用' : '已停用'}
                  </button>
                  <button className="btn btn-sm btn-primary" onClick={() => handleExecute(task.id)}>
                    立即执行
                  </button>
                  <button className="btn btn-sm btn-secondary" onClick={() => openEditForm(task)}>
                    编辑
                  </button>
                  <button className="btn btn-sm btn-danger" onClick={() => handleDelete(task.id)}>
                    删除
                  </button>
                </div>
              </div>
              <div className="task-card-meta">
                <span>筛选: {describeFilter(task)}</span>
                <span>调度: {describeSchedule(task)}</span>
                <span>上次: {formatTime(task.last_run_at)}</span>
                <span>下次: {formatTime(task.next_run_at)}</span>
              </div>
              <button
                className="btn btn-link btn-sm"
                onClick={() => toggleExecutions(task.id)}
              >
                {expandedTask === task.id ? '收起执行历史 ▲' : '查看执行历史 ▼'}
              </button>
              {expandedTask === task.id && (
                <div className="execution-list">
                  {(!executions[task.id] || executions[task.id].length === 0) ? (
                    <p className="text-secondary">暂无执行记录</p>
                  ) : (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>ID</th>
                          <th>状态</th>
                          <th>开始时间</th>
                          <th>完成时间</th>
                          <th>结果</th>
                          <th>错误</th>
                        </tr>
                      </thead>
                      <tbody>
                        {executions[task.id].map(ex => (
                          <tr key={ex.id}>
                            <td>{ex.id}</td>
                            <td>
                              <span className={`status-badge status-${ex.status}`}>
                                {ex.status === 'completed' ? '已完成' : ex.status === 'running' ? '运行中' : '失败'}
                              </span>
                            </td>
                            <td>{formatTime(ex.started_at)}</td>
                            <td>{formatTime(ex.completed_at)}</td>
                            <td className="exec-result">
                              {ex.result_summary ? (() => {
                                try {
                                  const s = typeof ex.result_summary === 'string' ? JSON.parse(ex.result_summary) : ex.result_summary
                                  return `聚合${s.aggregated} 检测${s.detected} 可疑${s.suspected}`
                                } catch (e) { return ex.result_summary }
                              })() : '—'}
                            </td>
                            <td className="exec-error">{ex.error_message || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default TaskManager
