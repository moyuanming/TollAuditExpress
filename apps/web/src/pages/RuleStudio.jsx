import React, { useState, useEffect } from 'react'
import { rulesApi } from '../api/rules'

const FRAUD_TYPE_OPTIONS = [
  { value: 'TRUCK_AS_CAR', label: '🚛 货套客' },
  { value: 'ENTRY_EXIT_MISMATCH', label: '🚗 出入口不一致' },
  { value: 'GATEWAY_ANOMALY', label: '🛣️ 门架异常' },
  { value: 'VEHICLE_TYPE_DOWNGRADE', label: '🔻 大车小标' },
  { value: 'SAME_PLATE_DIFF_VEHICLE', label: '🎭 同牌不同车' },
  { value: 'OBU_UNBIND', label: '🔁 OBU 借用' },
  { value: 'OBU_SHIELD', label: '🛡️ OBU 屏蔽' }
]

const FRAUD_TYPE_LABEL = FRAUD_TYPE_OPTIONS.reduce((m, o) => {
  m[o.value] = o.label
  return m
}, {})

const SEVERITY_LABEL = {
  1: { label: '低', color: 'badge-info' },
  2: { label: '中', color: 'badge-warning' },
  3: { label: '高', color: 'badge-danger' }
}

const RULE_EXPR_EXAMPLE = `{
  "when": ["and",
    ["gt", "$trip.gantry_count", 1],
    ["ne", "$trip.entry_vehicle_type", 1]
  ],
  "score": ["add", ["mul", "$trip.gantry_count", 0.1], 0.5]
}`

const EMPTY_FORM = {
  name: '',
  fraud_type: 'TRUCK_AS_CAR',
  severity: 2,
  description: '',
  rule_expr_json: RULE_EXPR_EXAMPLE,
  threshold: 0.5,
  dry_run: 1,
  enabled: 1
}

function formatTime(t) {
  if (!t) return '—'
  return String(t).replace('T', ' ').substring(0, 19)
}

function RuleStudio() {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({ fraudType: '', enabled: '' })
  const [showForm, setShowForm] = useState(false)
  const [editingRule, setEditingRule] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadRules()
  }, [filters])

  async function loadRules() {
    setLoading(true)
    try {
      const params = {}
      if (filters.fraudType) params.fraud_type = filters.fraudType
      if (filters.enabled !== '') params.enabled = filters.enabled
      const data = await rulesApi.listRules(params)
      setRules(data.rules || [])
    } catch (e) {
      console.error('Failed to load rules:', e)
    } finally {
      setLoading(false)
    }
  }

  function openCreate() {
    setEditingRule(null)
    setForm(EMPTY_FORM)
    setFormError(null)
    setShowForm(true)
  }

  function openEdit(rule) {
    setEditingRule(rule)
    const expr = rule.rule_expr
    const exprText = expr == null
      ? ''
      : typeof expr === 'string'
        ? expr
        : JSON.stringify(expr, null, 2)
    setForm({
      name: rule.name || '',
      fraud_type: rule.fraud_type || 'TRUCK_AS_CAR',
      severity: rule.severity ?? 2,
      description: rule.description || '',
      rule_expr_json: exprText,
      threshold: rule.threshold ?? 0.5,
      dry_run: rule.dry_run ?? 1,
      enabled: rule.enabled ?? 1
    })
    setFormError(null)
    setShowForm(true)
  }

  function closeForm() {
    setShowForm(false)
    setEditingRule(null)
    setFormError(null)
  }

  function formatJson() {
    try {
      const parsed = JSON.parse(form.rule_expr_json || '{}')
      setForm({ ...form, rule_expr_json: JSON.stringify(parsed, null, 2) })
      setFormError(null)
    } catch (e) {
      setFormError('JSON 解析失败: ' + e.message)
    }
  }

  function loadExample() {
    setForm({ ...form, rule_expr_json: RULE_EXPR_EXAMPLE })
    setFormError(null)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError(null)

    let parsedExpr
    try {
      parsedExpr = JSON.parse(form.rule_expr_json || '{}')
    } catch (err) {
      setFormError('rule_expr 不是合法 JSON: ' + err.message)
      return
    }

    if (!form.name.trim()) {
      setFormError('请填写规则名称')
      return
    }
    const threshold = Number(form.threshold)
    if (Number.isNaN(threshold) || threshold < 0 || threshold > 1) {
      setFormError('threshold 必须是 0~1 之间的小数')
      return
    }

    const payload = {
      name: form.name.trim(),
      fraud_type: form.fraud_type,
      severity: Number(form.severity),
      description: form.description.trim() || null,
      rule_expr: parsedExpr,
      threshold,
      dry_run: form.dry_run ? 1 : 0,
      ...(editingRule ? { enabled: form.enabled ? 1 : 0 } : { source: 'manual' })
    }

    setSaving(true)
    try {
      if (editingRule) {
        await rulesApi.updateRule(editingRule.id, payload)
      } else {
        await rulesApi.createRule(payload)
      }
      closeForm()
      loadRules()
    } catch (err) {
      setFormError('保存失败: ' + (err.message || '未知错误'))
    } finally {
      setSaving(false)
    }
  }

  async function handleToggle(rule) {
    try {
      await rulesApi.toggleRule(rule.id, !rule.enabled)
      loadRules()
    } catch (e) {
      alert('切换失败: ' + e.message)
    }
  }

  async function handleDryRun(rule) {
    try {
      await rulesApi.setDryRun(rule.id, !rule.dry_run)
      loadRules()
    } catch (e) {
      alert('切换 dry-run 失败: ' + e.message)
    }
  }

  async function handleDelete(rule) {
    if (!confirm(`确定删除规则 "${rule.name}" ？`)) return
    try {
      await rulesApi.deleteRule(rule.id)
      loadRules()
    } catch (e) {
      alert('删除失败: ' + e.message)
    }
  }

  const enabledCount = rules.filter(r => r.enabled === 1 || r.enabled === true).length
  const dryRunCount = rules.filter(r => r.dry_run === 1 || r.dry_run === true).length

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-group">
          <h2 className="page-title">规则管理</h2>
          <span className="page-subtitle">管理检测规则表达式、阈值、试运行状态</span>
        </div>
        <div className="stats-strip" style={{ marginLeft: 'auto' }}>
          <div className="stat-mini">
            <span className="stat-mini-icon">📋</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{rules.length}</span>
              <span className="stat-mini-label">规则总数</span>
            </div>
          </div>
          <div className="stat-mini">
            <span className="stat-mini-icon">✅</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{enabledCount}</span>
              <span className="stat-mini-label">已启用</span>
            </div>
          </div>
          <div className="stat-mini">
            <span className="stat-mini-icon">🧪</span>
            <div className="stat-mini-content">
              <span className="stat-mini-value">{dryRunCount}</span>
              <span className="stat-mini-label">试运行中</span>
            </div>
          </div>
        </div>
        <button className="btn btn-primary" onClick={openCreate} style={{ marginLeft: 12 }}>
          + 新建规则
        </button>
      </div>

      <div className="filter-section">
        <div className="filter-group">
          <span className="filter-label">欺诈类型:</span>
          <select
            className="filter-select"
            value={filters.fraudType}
            onChange={(e) => setFilters({ ...filters, fraudType: e.target.value })}
          >
            <option value="">全部</option>
            {FRAUD_TYPE_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="filter-group">
          <span className="filter-label">状态:</span>
          <select
            className="filter-select"
            value={filters.enabled}
            onChange={(e) => setFilters({ ...filters, enabled: e.target.value })}
          >
            <option value="">全部</option>
            <option value="1">已启用</option>
            <option value="0">已停用</option>
          </select>
        </div>
        <div className="filter-group" style={{ marginLeft: 'auto', color: 'var(--text-tertiary)', fontSize: '0.75rem' }}>
          💡 DSL 操作符白名单：eq ne gt lt gte lte and or not in add sub mul div count if
        </div>
      </div>

      <div className="table-panel">
        <div className="table-wrapper">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 60 }}>ID</th>
                <th>名称</th>
                <th style={{ width: 140 }}>欺诈类型</th>
                <th style={{ width: 70 }}>严重度</th>
                <th style={{ width: 80 }}>阈值</th>
                <th style={{ width: 90 }}>Dry Run</th>
                <th style={{ width: 90 }}>启用</th>
                <th style={{ width: 140 }}>更新时间</th>
                <th style={{ width: 220 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '2rem' }}>
                    <span className="loading-spinner"></span> 加载中...
                  </td>
                </tr>
              ) : rules.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <div className="empty-state">
                      <div className="empty-state-icon">📋</div>
                      <div className="empty-state-title">暂无规则</div>
                      <div className="empty-state-text">点击右上角"新建规则"创建第一条检测规则</div>
                    </div>
                  </td>
                </tr>
              ) : rules.map(r => {
                const sev = SEVERITY_LABEL[r.severity] || { label: r.severity, color: 'badge-info' }
                const isEnabled = r.enabled === 1 || r.enabled === true
                const isDryRun = r.dry_run === 1 || r.dry_run === true
                return (
                  <tr key={r.id}>
                    <td><span className="mono">#{r.id}</span></td>
                    <td>
                      <div style={{ fontWeight: 500 }}>{r.name}</div>
                      {r.description && (
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginTop: 2 }}>
                          {r.description}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="badge badge-info">
                        {FRAUD_TYPE_LABEL[r.fraud_type] || r.fraud_type}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${sev.color}`}>{sev.label}</span>
                    </td>
                    <td>
                      <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>
                        {Number(r.threshold).toFixed(2)}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${isDryRun ? 'badge-warning' : 'badge-danger'}`}>
                        {isDryRun ? '试运行' : '正式'}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${isEnabled ? 'badge-success' : 'badge-info'}`}>
                        {isEnabled ? '已启用' : '已停用'}
                      </span>
                    </td>
                    <td>
                      <span className="mono" style={{ fontSize: '0.7rem' }}>
                        {formatTime(r.updated_at)}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        <button
                          className="btn btn-sm btn-secondary"
                          onClick={() => openEdit(r)}
                        >
                          编辑
                        </button>
                        <button
                          className={`btn btn-sm ${isEnabled ? 'btn-secondary' : 'btn-success'}`}
                          onClick={() => handleToggle(r)}
                          title={isEnabled ? '停用规则' : '启用规则'}
                        >
                          {isEnabled ? '停用' : '启用'}
                        </button>
                        <button
                          className={`btn btn-sm ${isDryRun ? 'btn-danger' : 'btn-secondary'}`}
                          onClick={() => handleDryRun(r)}
                          title={isDryRun ? '切换为正式' : '切换为试运行'}
                        >
                          {isDryRun ? '→正式' : '→试跑'}
                        </button>
                        <button
                          className="btn btn-sm btn-secondary"
                          onClick={() => handleDelete(r)}
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={closeForm}>
          <div className="modal modal-lg" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editingRule ? `编辑规则 #${editingRule.id}` : '新建规则'}</h3>
              <button className="btn btn-link btn-sm" onClick={closeForm}>关闭 ✕</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-row">
                  <div className="form-group" style={{ flex: 2 }}>
                    <label>规则名称 *</label>
                    <input
                      type="text"
                      className="input"
                      value={form.name}
                      onChange={e => setForm({ ...form, name: e.target.value })}
                      placeholder="例如：门架跳点-中度"
                      required
                    />
                  </div>
                  <div className="form-group" style={{ flex: 1 }}>
                    <label>欺诈类型 *</label>
                    <select
                      className="input"
                      value={form.fraud_type}
                      onChange={e => setForm({ ...form, fraud_type: e.target.value })}
                    >
                      {FRAUD_TYPE_OPTIONS.map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>严重度</label>
                    <select
                      className="input"
                      value={form.severity}
                      onChange={e => setForm({ ...form, severity: parseInt(e.target.value) })}
                    >
                      <option value={1}>低 (1)</option>
                      <option value={2}>中 (2)</option>
                      <option value={3}>高 (3)</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>阈值 (0~1)</label>
                    <input
                      type="number"
                      className="input"
                      value={form.threshold}
                      onChange={e => setForm({ ...form, threshold: e.target.value })}
                      min="0"
                      max="1"
                      step="0.05"
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label>描述</label>
                  <input
                    type="text"
                    className="input"
                    value={form.description}
                    onChange={e => setForm({ ...form, description: e.target.value })}
                    placeholder="规则用途说明（可选）"
                  />
                </div>

                <div className="form-group">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <label>规则表达式 (JSON) *</label>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button type="button" className="btn btn-sm btn-secondary" onClick={loadExample}>
                        加载示例
                      </button>
                      <button type="button" className="btn btn-sm btn-secondary" onClick={formatJson}>
                        格式化 JSON
                      </button>
                    </div>
                  </div>
                  <textarea
                    className="input"
                    value={form.rule_expr_json}
                    onChange={e => setForm({ ...form, rule_expr_json: e.target.value })}
                    rows={12}
                    style={{ fontFamily: 'monospace', fontSize: '0.8rem', lineHeight: 1.5 }}
                    spellCheck={false}
                  />
                  <span className="form-hint">
                    字段访问以 <code>$trip.</code> 开头；仅支持白名单操作符（eq ne gt lt gte lte and or not in add sub mul div count if）
                  </span>
                </div>

                <div className="form-row">
                  <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="checkbox"
                      id="rule-dry-run"
                      checked={form.dry_run === 1}
                      onChange={e => setForm({ ...form, dry_run: e.target.checked ? 1 : 0 })}
                    />
                    <label htmlFor="rule-dry-run" style={{ marginBottom: 0, cursor: 'pointer' }}>
                      🧪 试运行 (dry-run，不写入正式可疑队列)
                    </label>
                  </div>
                  {editingRule && (
                    <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <input
                        type="checkbox"
                        id="rule-enabled"
                        checked={form.enabled === 1}
                        onChange={e => setForm({ ...form, enabled: e.target.checked ? 1 : 0 })}
                      />
                      <label htmlFor="rule-enabled" style={{ marginBottom: 0, cursor: 'pointer' }}>
                        ✅ 启用规则
                      </label>
                    </div>
                  )}
                </div>

                {formError && (
                  <div className="alert alert-warning" style={{ marginTop: 12 }}>
                    {formError}
                  </div>
                )}
              </div>
              <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={closeForm}>取消</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? '保存中...' : (editingRule ? '保存' : '创建')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default RuleStudio
