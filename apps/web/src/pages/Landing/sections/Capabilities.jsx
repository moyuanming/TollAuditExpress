import React from 'react'
import './Capabilities.css'

const ITEMS = [
  { id: 1, name: '货车套用客车 OBU', desc: '入口车型 vs 视觉识别' },
  { id: 2, name: '出入口车辆不一致', desc: '车牌/车型/车纹多维比对' },
  { id: 3, name: '门架路径异常', desc: '序列与拓扑不符' },
  { id: 4, name: '车型降档', desc: '交易记客,识别为货' },
  { id: 5, name: '同车牌多 OBU', desc: '历史绑定异常' },
  { id: 6, name: 'OBU 多车绑定', desc: 'OBU 短时绑多车' },
  { id: 7, name: 'OBU 屏蔽', desc: '无 OBU 但有出口图' },
  { id: 8, name: '车牌 OBU 历史异常', desc: '历史关系异常' },
]

export default function Capabilities() {
  return (
    <section className="cap" id="capabilities">
      <div className="cap-inner">
        <h2 className="cap-title">8 类逃费行为,AI 自动识别</h2>
        <p className="cap-sub">覆盖主流高速场景,持续扩展</p>
        <div className="cap-grid">
          {ITEMS.map((it) => (
            <div key={it.id} className="cap-card">
              <span className="cap-badge">{String(it.id).padStart(2, '0')}</span>
              <div className="cap-name">{it.name}</div>
              <div className="cap-desc">{it.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
