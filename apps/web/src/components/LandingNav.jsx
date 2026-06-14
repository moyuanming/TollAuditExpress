import React, { useEffect, useState } from 'react'
import { useAuth } from './AuthContext'
import './LandingNav.css'

const SECTIONS = [
  { id: 'capabilities', label: '能力' },
  { id: 'architecture', label: '架构' },
  { id: 'stats', label: '数据' },
  { id: 'contact', label: '联系' },
]

export default function LandingNav() {
  const { isAuthenticated } = useAuth()
  const [active, setActive] = useState('capabilities')

  useEffect(() => {
    const observers = []
    for (const { id } of SECTIONS) {
      const el = document.getElementById(id)
      if (!el) continue
      const obs = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            if (e.isIntersecting) setActive(id)
          }
        },
        { rootMargin: '-40% 0px -50% 0px' }
      )
      obs.observe(el)
      observers.push(obs)
    }
    return () => observers.forEach((o) => o.disconnect())
  }, [])

  return (
    <nav className="landing-nav">
      <div className="landing-nav-inner">
        <div className="landing-brand">
          <span className="landing-brand-icon">稽</span>
          <span>高速公路收费稽核系统</span>
        </div>
        <div className="landing-nav-links">
          {SECTIONS.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className={active === s.id ? 'landing-nav-link active' : 'landing-nav-link'}
            >
              {s.label}
            </a>
          ))}
        </div>
        <a className="landing-nav-cta" href="/app">
          {isAuthenticated ? '进入后台' : '登录后台'}
        </a>
      </div>
    </nav>
  )
}
