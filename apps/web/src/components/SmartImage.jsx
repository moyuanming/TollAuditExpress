import { useState, useEffect, useRef } from 'react'
import Icon from './Icon'

// Always go through the same-origin proxy. The proxy is reachable from any
// client that can reach the app, regardless of the client's network. Skipping
// the direct phase entirely removes the "browser sits on unreachable IP" hang.
function proxyUrlFor(imageUrl, attempt) {
  const ts = attempt ? `&_t=${Date.now()}` : ''
  return `/api/audit/image-proxy?url=${encodeURIComponent(imageUrl)}${ts}`
}

// Hard ceiling: an image that hasn't loaded or errored within this many ms
// is treated as failed. Prevents one slow upstream from making the whole
// detail panel feel "stuck".
const LOAD_TIMEOUT_MS = 5000

function SmartImage({ imageUrl, alt = '', style, onLoaded }) {
  const [status, setStatus] = useState('loading') // loading | loaded | error
  const [attempt, setAttempt] = useState(0)
  const timerRef = useRef(null)

  useEffect(() => {
    if (status !== 'loading' || !imageUrl) return undefined
    timerRef.current = setTimeout(() => {
      setStatus('error')
    }, LOAD_TIMEOUT_MS)
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [status, attempt, imageUrl])

  if (!imageUrl) {
    return (
      <div className="image-fallback-box" style={style}>
        <Icon name="image" size="xl" />
        <span>无图像</span>
      </div>
    )
  }

  const handleError = () => {
    setStatus('error')
  }

  const handleLoad = () => {
    setStatus('loaded')
    if (onLoaded) onLoaded()
  }

  const handleRetry = (e) => {
    e.stopPropagation()
    setAttempt((a) => a + 1)
    setStatus('loading')
  }

  if (status === 'error') {
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
      {status === 'loading' && (
        <div className="image-loading-box">
          <span className="loading-spinner" />
          <span className="text-0p75 text-secondary">加载中</span>
        </div>
      )}
      <img
        src={proxyUrlFor(imageUrl, attempt)}
        alt={alt}
        className="smart-image"
        style={status === 'loading' ? { opacity: 0 } : undefined}
        onLoad={handleLoad}
        onError={handleError}
      />
    </div>
  )
}

export default SmartImage
