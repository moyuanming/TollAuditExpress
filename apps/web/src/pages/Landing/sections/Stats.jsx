import React from 'react'
import './Stats.css'

const STATS = [
  { num: '8', label: '逃费类型' },
  { num: '99.2%', label: '识别准确率' },
  { num: '<200ms', label: '单次识别' },
  { num: '3 机', label: '部署拓扑' },
]

export default function Stats() {
  return (
    <section className="stats" id="stats">
      <div className="stats-inner">
        <div className="stats-grid">
          {STATS.map((s) => (
            <div key={s.label} className="stats-item">
              <div className="stats-num">{s.num}</div>
              <div className="stats-label">{s.label}</div>
            </div>
          ))}
        </div>
        <p className="stats-foot">
          数据来源于内部测试环境,实际值以部署报告为准
        </p>
      </div>
    </section>
  )
}
