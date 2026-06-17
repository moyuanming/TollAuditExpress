import { useState, useEffect, useRef } from 'react'
import Icon from './Icon'

const LOAD_TIMEOUT_MS = 6000

function SmartImage({ imageUrl, alt = '', style, onLoaded }) {
  const [phase, setPhase] = useState('direct') // direct | proxy | error
  const [attempt, setAttempt] = useState(0)
  const timerRef = useRef(null)

  useEffect(() => {
    if (phase === 'error' || !imageUrl) return undefined
    timerRef.current = setTimeout(() => {
      if (phase === 'direct') setPhase('proxy')
      else if (phase === 'proxy') setPhase('error')
    }, LOAD_TIMEOUT_MS)
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [phase, attempt, imageUrl])

  if (!imageUrl) {
    return (
      <div className="image-fallback-box" style={style}>
        <Icon name="image" size="xl" />
        <span>无图像</span>
      </div>
    )
  }

  const proxyUrl = `/api/audit/image-proxy?url=${encodeURIComponent(imageUrl)}${attempt ? `&_t=${Date.now()}` : ''}`
  const src = phase === 'direct' ? imageUrl : phase === 'proxy' ? proxyUrl : null

  const handleDirectError = () => {
    if (phase === 'direct') {
      setPhase('proxy')
    } else if (phase === 'proxy') {
      setPhase('error')
    }
  }

  const handleRetry = (e) => {
    e.stopPropagation()
    setAttempt(a => a + 1)
    setPhase('direct')
  }

  if (phase === 'error') {
    return (
      <div className="smart-image-wrap" style={style}>
        <div className="image-error-box">
          <Icon name="alert-triangle" size="xl" />
          <span className="text-sm text-secondary">加载失败</span>
          <button
            type="button"
            className="btn btn-link btn-sm text-0p75 mt-1 p-0"
            onClick={handleRetry}
          >
            <Icon name="refresh" size="sm" />重试
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="smart-image-wrap" style={style}>
      <img
        src={src}
        alt={alt}
        className="smart-image"
        onLoad={() => onLoaded && onLoaded()}
        onError={handleDirectError}
      />
    </div>
  )
}

export default SmartImage
