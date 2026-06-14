import React, { useEffect } from 'react'
import LandingNav from '../../components/LandingNav'
import Hero from './sections/Hero'
import Capabilities from './sections/Capabilities'
import Architecture from './sections/Architecture'
import Stats from './sections/Stats'
import CTA from './sections/CTA'
import './Landing.css'

export default function Landing() {
  useEffect(() => {
    document.title = 'TollAudit Express · 高速公路 AI 稽核'
    const meta = document.querySelector('meta[name="description"]')
    if (meta) {
      meta.setAttribute('content', 'TollAudit Express 高速公路 AI 稽核系统,识别 8 类逃费行为,服务高速运营单位本地化部署。')
    } else {
      const m = document.createElement('meta')
      m.name = 'description'
      m.content = 'TollAudit Express 高速公路 AI 稽核系统,识别 8 类逃费行为,服务高速运营单位本地化部署。'
      document.head.appendChild(m)
    }
  }, [])

  return (
    <div className="landing">
      <LandingNav />
      <main>
        <Hero />
        <Capabilities />
        <Architecture />
        <Stats />
        <CTA />
        <footer className="landing-footer">
          <p>© TollAudit Express · 高速公路收费稽核系统</p>
        </footer>
      </main>
    </div>
  )
}
