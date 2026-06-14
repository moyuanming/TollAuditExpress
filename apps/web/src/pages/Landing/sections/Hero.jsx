import React from 'react'
import './Hero.css'

export default function Hero() {
  return (
    <section className="hero">
      <div className="hero-inner">
        <div className="hero-text">
          <div className="hero-eyebrow">TollAudit · 高速公路 AI 稽核</div>
          <h1 className="hero-title">让每一笔通行费,都不再流失</h1>
          <p className="hero-sub">
            基于双 AI 视觉模型,毫秒级识别 8 类常见逃费行为,准确率 99.2%,
            服务高速运营单位本地化部署。
          </p>
          <div className="hero-ctas">
            <a className="hero-btn-primary" href="#contact">申请免费试用 →</a>
            <a className="hero-btn-ghost" href="#capabilities">下载技术白皮书</a>
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="hero-visual-glyph">稽</div>
        </div>
      </div>
    </section>
  )
}
