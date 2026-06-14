import React from 'react'
import './Architecture.css'

const FEATURES = [
  { icon: '🏢', title: '本地化部署', desc: '支持私有化部署,数据不出本单位内网' },
  { icon: '🔌', title: '源库直连', desc: '对接 Doris 源库只读,业务零侵入' },
  { icon: '🤖', title: 'AI 模型分离', desc: '视觉模型独立公共服务,可独立升级' },
]

export default function Architecture() {
  return (
    <section className="arch" id="architecture">
      <div className="arch-inner">
        <h2 className="arch-title">为高速运营方而生 · 安全可控</h2>
        <p className="arch-sub">支持本地化部署,数据不出域</p>
        <div className="arch-grid">
          {FEATURES.map((f) => (
            <div key={f.title} className="arch-card">
              <div className="arch-icon">{f.icon}</div>
              <div className="arch-card-title">{f.title}</div>
              <div className="arch-card-desc">{f.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
