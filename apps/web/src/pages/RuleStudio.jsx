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

const FRAUD_TYPE_GUIDE = {
  TRUCK_AS_CAR: {
    title: '货套客（TRUCK_AS_CAR）',
    desc: '货车使用客车 OBU 或套用客车车型通行，按客车费率缴费以逃避通行费差额。',
    logic: '核心思路：入口/门架采集的车辆类型与 OBU 登记车型不一致，且实际车型为货车、OBU 车型为客车。典型条件：$trip.entry_vehicle_type ≠ 1（非客车）且 $trip.obu_vehicle_type = 1（OBU 为客车）。评分可结合门架数量、路径长度等加权。',
    fields: ['entry_vehicle_type', 'obu_vehicle_type', 'gantry_count', 'actual_vehicle_type']
  },
  ENTRY_EXIT_MISMATCH: {
    title: '出入口不一致（ENTRY_EXIT_MISMATCH）',
    desc: '车辆入口站与出口站不匹配正常行驶路径，可能存在倒卡、换卡或路径造假行为。',
    logic: '核心思路：入口站与出口站之间的合理路径距离/门架序列与实际采集数据不匹配。典型条件：$trip.entry_station 与 $trip.exit_station 的拓扑距离超出阈值，或中间门架序列不在最短路径上。',
    fields: ['entry_station', 'exit_station', 'gantry_count', 'expected_gantry_count', 'path_distance']
  },
  GATEWAY_ANOMALY: {
    title: '门架异常（GATEWAY_ANOMALY）',
    desc: '门架交易数据异常，包括门架漏读、重复交易、时间倒挂或信号屏蔽等情况。',
    logic: '核心思路：门架交易数量与预期不符（过多/过少），或交易时间序列不单调递增。典型条件：$trip.gantry_count 与预期门架数偏差超过阈值，或存在时间倒挂 $trip.has_time_reversal = true。',
    fields: ['gantry_count', 'expected_gantry_count', 'has_time_reversal', 'duplicate_gantry_count', 'missing_gantry_count']
  },
  VEHICLE_TYPE_DOWNGRADE: {
    title: '大车小标（VEHICLE_TYPE_DOWNGRADE）',
    desc: '大型车辆登记为小型车辆车型，按低费率缴费，造成通行费损失。',
    logic: '核心思路：实际车辆类型（轴数/重量/外形）与 OBU 登记车型不一致，且实际车型 > 登记车型。典型条件：$trip.actual_axle_count > $trip.obu_axle_count，或 $trip.actual_weight 超出登记车型限载。',
    fields: ['actual_axle_count', 'obu_axle_count', 'actual_weight', 'obu_weight_limit', 'actual_vehicle_type', 'obu_vehicle_type']
  },
  SAME_PLATE_DIFF_VEHICLE: {
    title: '同牌不同车（SAME_PLATE_DIFF_VEHICLE）',
    desc: '同一车牌号在不同时段/站点被不同物理车辆使用，可能存在套牌或 OBU 挪用。',
    logic: '核心思路：同一车牌在不同交易中出现不同的车辆特征（颜色/车型/轴数）。典型条件：$trip.plate_color 变化 或 $trip.vehicle_fingerprint 不一致。评分可结合特征差异程度和出现频次。',
    fields: ['plate_color', 'vehicle_fingerprint', 'axle_count', 'vehicle_type', 'occurrence_count']
  },
  OBU_UNBIND: {
    title: 'OBU 借用（OBU_UNBIND）',
    desc: 'OBU 设备与登记车辆不匹配，OBU 被安装到其他车辆上使用，逃避一车一设备监管。',
    logic: '核心思路：OBU 编号对应的车辆信息与实际通行车辆不一致。典型条件：$trip.obu_registered_plate ≠ $trip.actual_plate，或 $trip.obu_vehicle_type ≠ $trip.actual_vehicle_type。评分可结合不匹配字段数量。',
    fields: ['obu_registered_plate', 'actual_plate', 'obu_vehicle_type', 'actual_vehicle_type', 'mismatch_count']
  },
  OBU_SHIELD: {
    title: 'OBU 屏蔽（OBU_SHIELD）',
    desc: 'OBU 设备信号被屏蔽或关闭，导致门架无法正常读取交易，逃避路径追踪和计费。',
    logic: '核心思路：门架漏读率异常偏高，或 OBU 在应覆盖门架区间内无交易记录。典型条件：$trip.missing_gantry_ratio > 阈值，或 $trip.obu_signal_lost = true。评分可结合漏读比例和路径长度。',
    fields: ['missing_gantry_ratio', 'obu_signal_lost', 'expected_gantry_count', 'actual_gantry_count', 'signal_strength']
  }
}

const OPERATOR_GUIDE = [
  { op: 'and', args: '2+', desc: '逻辑与 — 所有子条件都为真时为真' },
  { op: 'or', args: '2+', desc: '逻辑或 — 任一子条件为真时为真' },
  { op: 'not', args: '1', desc: '逻辑非 — 取反' },
  { op: 'eq', args: '2', desc: '等于 — left == right' },
  { op: 'ne', args: '2', desc: '不等于 — left != right' },
  { op: 'gt', args: '2', desc: '大于 — left > right' },
  { op: 'lt', args: '2', desc: '小于 — left < right' },
  { op: 'gte', args: '2', desc: '大于等于 — left >= right' },
  { op: 'lte', args: '2', desc: '小于等于 — left <= right' },
  { op: 'in', args: '2', desc: '包含 — needle in haystack' },
  { op: 'add', args: '2+', desc: '加法 — 所有参数求和' },
  { op: 'sub', args: '2+', desc: '减法 — 依次相减' },
  { op: 'mul', args: '2+', desc: '乘法 — 依次相乘' },
  { op: 'div', args: '2+', desc: '除法 — 依次相除（除零报错）' },
  { op: 'count', args: '1', desc: '计数 — 返回集合长度' },
  { op: 'if', args: '3', desc: '条件 — if(条件, 真值, 假值)' }
]

const FIELD_LABEL = {
  gantry_count: '门架数量',
  entry_vehicle_type: '入口车型',
  exit_vehicle_type: '出口车型',
  obu_vehicle_type: 'OBU车型',
  actual_vehicle_type: '实际车型',
  entry_station: '入口站',
  exit_station: '出口站',
  threshold: '阈值',
  risk_score: '风险分值',
  missing_gantry_ratio: '漏读比例',
  obu_signal_lost: 'OBU信号丢失',
  has_time_reversal: '时间倒挂',
  actual_axle_count: '实际轴数',
  obu_axle_count: 'OBU轴数',
  actual_weight: '实际重量',
  obu_weight_limit: 'OBU限载',
  plate_color: '车牌颜色',
  vehicle_fingerprint: '车辆指纹',
  axle_count: '轴数',
  vehicle_type: '车型',
  occurrence_count: '出现次数',
  obu_registered_plate: 'OBU登记车牌',
  actual_plate: '实际车牌',
  mismatch_count: '不匹配数',
  expected_gantry_count: '预期门架数',
  actual_gantry_count: '实际门架数',
  duplicate_gantry_count: '重复门架数',
  missing_gantry_count: '漏读门架数',
  signal_strength: '信号强度',
  path_distance: '路径距离'
}

const OP_LABEL = {
  and: '并且', or: '或者', not: '非',
  eq: '等于', ne: '不等于', gt: '大于', lt: '小于',
  gte: '大于等于', lte: '小于等于', in: '属于',
  add: '相加', sub: '相减', mul: '相乘', div: '相除',
  count: '计数', if: '如果'
}

function humanizeField(path) {
  if (!path || typeof path !== 'string') return String(path)
  if (path.startsWith('$trip.')) {
    const key = path.slice(6)
    return FIELD_LABEL[key] || key
  }
  return path
}

function humanizeValue(v) {
  if (v === true || v === 'true') return '真'
  if (v === false || v === 'false') return '假'
  if (v === null || v === undefined) return '空'
  if (typeof v === 'string' && v.startsWith('$trip.')) return humanizeField(v)
  return String(v)
}

function exprToChinese(expr, indent = 0) {
  const pad = '  '.repeat(indent)
  if (typeof expr === 'boolean') return `${pad}${expr ? '真' : '假'}`
  if (typeof expr === 'number') return `${pad}${expr}`
  if (typeof expr === 'string') {
    if (expr.startsWith('$trip.')) return `${pad}${humanizeField(expr)}`
    return `${pad}${expr}`
  }
  if (!Array.isArray(expr) || expr.length === 0) return `${pad}???`

  const [op, ...args] = expr
  const opName = OP_LABEL[op] || op

  if (op === 'and' || op === 'or') {
    const lines = args.map((a, i) => {
      const child = exprToChinese(a, indent + 1).trim()
      return `${'  '.repeat(indent + 1)}(${i + 1}) ${child}`
    })
    return `${pad}${opName}:\n${lines.join('\n')}`
  }

  if (op === 'not') {
    return `${pad}非(${exprToChinese(args[0], 0).trim()})`
  }

  if (['eq', 'ne', 'gt', 'lt', 'gte', 'lte'].includes(op)) {
    const left = exprToChinese(args[0], 0).trim()
    const right = exprToChinese(args[1], 0).trim()
    return `${pad}${left} ${opName} ${right}`
  }

  if (op === 'in') {
    const needle = exprToChinese(args[0], 0).trim()
    const haystack = args[1]
    let setStr
    if (Array.isArray(haystack)) {
      setStr = haystack.map(v => humanizeValue(v)).join(', ')
    } else {
      setStr = exprToChinese(haystack, 0).trim()
    }
    return `${pad}${needle} ${opName} [${setStr}]`
  }

  if (['add', 'sub', 'mul', 'div'].includes(op)) {
    const parts = args.map(a => exprToChinese(a, 0).trim())
    const symbol = { add: '+', sub: '-', mul: '×', div: '÷' }[op]
    return `${pad}${parts.join(` ${symbol} `)}`
  }

  if (op === 'count') {
    return `${pad}计数(${exprToChinese(args[0], 0).trim()})`
  }

  if (op === 'if') {
    const cond = exprToChinese(args[0], 0).trim()
    const yes = exprToChinese(args[1], 0).trim()
    const no = exprToChinese(args[2], 0).trim()
    return `${pad}如果(${cond}) 则 ${yes} 否则 ${no}`
  }

  return `${pad}${opName}(${args.map(a => exprToChinese(a, 0).trim()).join(', ')})`
}

function ruleExprToReadable(ruleExprStr) {
  let expr
  try {
    expr = typeof ruleExprStr === 'string' ? JSON.parse(ruleExprStr) : ruleExprStr
  } catch {
    return { whenText: '（表达式解析失败）', scoreText: '' }
  }
  const whenText = expr.when ? exprToChinese(expr.when) : '（无条件，始终触发）'
  const scoreText = expr.score ? exprToChinese(expr.score) : '（无评分，默认 0）'
  return { whenText, scoreText }
}

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
  const [showGuide, setShowGuide] = useState(false)
  const [expandedRule, setExpandedRule] = useState(null)

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
        <button
          className={`btn btn-sm ${showGuide ? 'btn-secondary' : 'btn-secondary'}`}
          onClick={() => setShowGuide(!showGuide)}
          style={{ marginLeft: 6 }}
        >
          {showGuide ? '收起说明' : '📖 规则说明'}
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
          💡 点击"规则说明"查看欺诈类型定义与 DSL 语法
        </div>
      </div>

      {showGuide && (
        <div className="rule-guide-panel" style={{
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-primary)',
          borderRadius: 'var(--radius-md)',
          padding: '1.25rem 1.5rem',
          marginBottom: '1rem'
        }}>
          <h4 style={{ marginBottom: '0.75rem', fontSize: '0.95rem', color: 'var(--text-primary)' }}>
            📖 欺诈类型定义与检测逻辑
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '0.75rem' }}>
            {Object.entries(FRAUD_TYPE_GUIDE).map(([key, guide]) => (
              <div key={key} style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.75rem 1rem'
              }}>
                <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: 4, color: 'var(--text-primary)' }}>
                  {guide.title}
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: 6 }}>
                  {guide.desc}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--accent-blue)', marginBottom: 4, lineHeight: 1.5 }}>
                  <strong>检测逻辑：</strong>{guide.logic}
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>
                  常用字段：{guide.fields.map(f => `$trip.${f}`).join('、')}
                </div>
              </div>
            ))}
          </div>

          <h4 style={{ margin: '1rem 0 0.5rem', fontSize: '0.95rem', color: 'var(--text-primary)' }}>
            🔧 DSL 操作符参考
          </h4>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: '0.25rem 1rem',
            fontSize: '0.75rem'
          }}>
            {OPERATOR_GUIDE.map(item => (
              <div key={item.op} style={{ display: 'flex', gap: 6, padding: '2px 0' }}>
                <code style={{
                  background: 'var(--bg-tertiary)',
                  padding: '1px 6px',
                  borderRadius: 3,
                  fontFamily: 'monospace',
                  fontWeight: 600,
                  color: 'var(--accent-purple)',
                  whiteSpace: 'nowrap'
                }}>
                  {item.op}
                </code>
                <span style={{ color: 'var(--text-tertiary)' }}>({item.args})</span>
                <span style={{ color: 'var(--text-secondary)' }}>{item.desc}</span>
              </div>
            ))}
          </div>

          <h4 style={{ margin: '1rem 0 0.5rem', fontSize: '0.95rem', color: 'var(--text-primary)' }}>
            📐 规则求值流程
          </h4>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            <ol style={{ paddingLeft: '1.2rem' }}>
              <li><strong>when 条件求值</strong> — 对行程数据 ($trip) 执行 when 表达式，返回 true/false</li>
              <li><strong>score 评分求值</strong> — when 为 true 时，执行 score 表达式计算风险分值 (0~1)</li>
              <li><strong>限幅</strong> — 风险分值限制在 [0, 1] 区间</li>
              <li><strong>阈值比对</strong> — risk_score ≥ threshold 则标记为可疑 (is_suspicious=1)</li>
              <li><strong>dry-run</strong> — 试运行模式下不写入正式可疑队列 (is_suspicious=0)</li>
            </ol>
          </div>
        </div>
      )}

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
                <th style={{ width: 260 }}>操作</th>
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
              ) : rules.flatMap(r => {
                const sev = SEVERITY_LABEL[r.severity] || { label: r.severity, color: 'badge-info' }
                const isEnabled = r.enabled === 1 || r.enabled === true
                const isDryRun = r.dry_run === 1 || r.dry_run === true
                const isExpanded = expandedRule === r.id
                const { whenText, scoreText } = ruleExprToReadable(r.rule_expr)
                const guide = FRAUD_TYPE_GUIDE[r.fraud_type]

                const mainRow = (
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
                          className={`btn btn-sm ${isExpanded ? 'btn-primary' : 'btn-secondary'}`}
                          onClick={() => setExpandedRule(isExpanded ? null : r.id)}
                          title="查看规则逻辑详情"
                        >
                          {isExpanded ? '收起' : '详情'}
                        </button>
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

                const detailRow = isExpanded ? (
                  <tr key={`${r.id}-detail`}>
                    <td colSpan={9} style={{ padding: 0 }}>
                      <div style={{
                        background: 'var(--bg-secondary)',
                        borderTop: '2px solid var(--accent-blue)',
                        padding: '1rem 1.5rem',
                        fontSize: '0.8rem'
                      }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem 2rem' }}>
                          <div>
                            <div style={{ fontWeight: 600, color: 'var(--accent-blue)', marginBottom: 6 }}>
                              📋 欺诈类型说明
                            </div>
                            {guide ? (
                              <div style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                <div style={{ marginBottom: 4 }}>{guide.desc}</div>
                                <div style={{ color: 'var(--accent-purple)', fontSize: '0.75rem' }}>
                                  {guide.logic}
                                </div>
                                <div style={{ color: 'var(--text-tertiary)', fontSize: '0.7rem', marginTop: 4 }}>
                                  常用字段：{guide.fields.map(f => (
                                    <code key={f} style={{ background: 'var(--bg-tertiary)', padding: '0 3px', borderRadius: 2, margin: '0 2px' }}>
                                      ${`{trip.${f}}`}
                                    </code>
                                  ))}
                                </div>
                              </div>
                            ) : (
                              <div style={{ color: 'var(--text-tertiary)' }}>无说明</div>
                            )}
                          </div>
                          <div>
                            <div style={{ fontWeight: 600, color: 'var(--accent-blue)', marginBottom: 6 }}>
                              🔍 规则逻辑解读
                            </div>
                            <div style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                              <div style={{ marginBottom: 8 }}>
                                <strong style={{ color: 'var(--text-primary)' }}>触发条件 (when)：</strong>
                                <pre style={{
                                  margin: '4px 0',
                                  padding: '6px 10px',
                                  background: 'var(--bg-primary)',
                                  border: '1px solid var(--border-primary)',
                                  borderRadius: 'var(--radius-sm)',
                                  fontFamily: 'inherit',
                                  fontSize: '0.78rem',
                                  whiteSpace: 'pre-wrap',
                                  color: 'var(--text-primary)'
                                }}>
                                  {whenText}
                                </pre>
                              </div>
                              <div>
                                <strong style={{ color: 'var(--text-primary)' }}>评分公式 (score)：</strong>
                                <pre style={{
                                  margin: '4px 0',
                                  padding: '6px 10px',
                                  background: 'var(--bg-primary)',
                                  border: '1px solid var(--border-primary)',
                                  borderRadius: 'var(--radius-sm)',
                                  fontFamily: 'inherit',
                                  fontSize: '0.78rem',
                                  whiteSpace: 'pre-wrap',
                                  color: 'var(--text-primary)'
                                }}>
                                  {scoreText}
                                </pre>
                              </div>
                              <div style={{ marginTop: 6, fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                                当评分 ≥ 阈值 ({Number(r.threshold).toFixed(2)}) 时标记为可疑
                                {r.dry_run ? '（当前为试运行，不写入正式队列）' : '（正式模式，写入可疑队列）'}
                              </div>
                            </div>
                          </div>
                        </div>
                        <div style={{ marginTop: '0.75rem', paddingTop: '0.5rem', borderTop: '1px solid var(--border-primary)' }}>
                          <div style={{ fontWeight: 600, color: 'var(--accent-blue)', marginBottom: 4, fontSize: '0.78rem' }}>
                            💻 原始表达式 (JSON)
                          </div>
                          <pre style={{
                            margin: 0,
                            padding: '6px 10px',
                            background: 'var(--bg-primary)',
                            border: '1px solid var(--border-primary)',
                            borderRadius: 'var(--radius-sm)',
                            fontFamily: 'monospace',
                            fontSize: '0.72rem',
                            whiteSpace: 'pre-wrap',
                            color: 'var(--text-tertiary)',
                            maxWidth: '100%',
                            overflow: 'auto'
                          }}>
                            {typeof r.rule_expr === 'string' ? r.rule_expr : JSON.stringify(r.rule_expr, null, 2)}
                          </pre>
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : null

                return [mainRow, detailRow]
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
                    字段访问以 <code>$trip.</code> 开头；点击页面上方"规则说明"查看操作符与字段说明
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
