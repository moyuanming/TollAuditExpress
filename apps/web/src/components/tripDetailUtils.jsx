// 详情面板共享工具：被 SuspectList / VehicleQuery 共用
import React from 'react'
import SmartImage from './SmartImage'

export function formatTime(t) {
  if (!t) return '—'
  return String(t).replace('T', ' ').substring(0, 19)
}

export function buildDecisionSummary(suspect) {
  const points = []
  if (suspect.fraud_type === 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A') {
    const registered = suspect.entry_vehicle_type === 1 ? '客车' : suspect.entry_vehicle_type === 2 ? '货车' : `类型${suspect.entry_vehicle_type}`
    const visual = suspect.entry_visual_type || suspect.exit_visual_type || '未识别'
    const llmVerified = suspect.llm_verified === true ? '已通过' : suspect.llm_verified === false ? '未通过' : '未复核'
    points.push({ label: '车型登记', value: registered, status: 'normal' })
    points.push({ label: 'AI 视觉识别', value: visual, status: visual && visual !== '未识别' ? 'abnormal' : 'normal' })
    points.push({ label: 'LLM 复核', value: llmVerified, status: llmVerified === '已通过' ? 'abnormal' : 'normal' })
    if (suspect.risk_score != null) {
      points.push({
        label: 'AI 置信度',
        value: suspect.risk_score.toFixed(2),
        status: suspect.risk_score > 0.8 ? 'abnormal' : suspect.risk_score > 0.6 ? 'warning' : 'normal'
      })
    }
  } else if (suspect.fraud_type === 'ENTRY_EXIT_MISMATCH') {
    points.push({ label: '入口视觉类型', value: suspect.entry_visual_type || '—', status: 'normal' })
    points.push({ label: '出口视觉类型', value: suspect.exit_visual_type || '—', status: 'normal' })
    if (suspect.entry_color || suspect.exit_color) {
      const same = suspect.entry_color === suspect.exit_color
      points.push({
        label: '车辆颜色',
        value: `${suspect.entry_color || '?'} → ${suspect.exit_color || '?'}`,
        status: same ? 'normal' : 'abnormal'
      })
    }
    if (suspect.risk_score != null) {
      points.push({
        label: '指纹相似度',
        value: suspect.risk_score.toFixed(2),
        status: suspect.risk_score < 0.6 ? 'abnormal' : suspect.risk_score < 0.8 ? 'warning' : 'normal'
      })
    }
  }
  return points
}

export function DecisionTable({ suspect }) {
  const points = buildDecisionSummary(suspect)
  if (points.length === 0) return null
  return (
    <table className="table text-0p8">
      <tbody>
        {points.map((p, i) => (
          <tr key={i}>
            <td className="colgroup-w-40 text-secondary">{p.label}</td>
            <td>
              <span className={`result-tag ${p.status}`}>{p.value}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function JsonView({ data }) {
  if (!data) return <span className="text-tertiary">—</span>
  let obj = data
  if (typeof data === 'string') {
    try { obj = JSON.parse(data) } catch (e) { return <pre className="code-block-json">{data}</pre> }
  }
  return (
    <pre className="code-block-json">
      {JSON.stringify(obj, null, 2)}
    </pre>
  )
}

export function ImageBox({ label, imageUrl, status, badge }) {
  return (
    <div className="image-compare-item">
      <div className="image-compare-label">{label}</div>
      <SmartImage
        imageUrl={imageUrl}
        alt={label}
        style={{ aspectRatio: '4/3', width: '100%' }}
      />
      {badge && <div className={`image-compare-status ${status}`}>{badge}</div>}
    </div>
  )
}
