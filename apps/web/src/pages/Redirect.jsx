import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useAuth } from '../components/AuthContext'

export default function Redirect() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { login } = useAuth()
  const [error, setError] = useState(null)

  useEffect(() => {
    const code = searchParams.get('code')
    if (!code) {
      setError('缺少授权码')
      return
    }

    fetch(`/api/oauth/callback?code=${encodeURIComponent(code)}`, { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.code === 200 && data.data?.accessToken) {
          login(data.data.accessToken)
          navigate('/', { replace: true })
        } else {
          setError(data.msg || '登录失败')
        }
      })
      .catch(err => {
        setError(err.message || '网络请求失败')
      })
  }, [])

  if (error) {
    return (
      <div className="redirect-error">
        <h2>登录失败</h2>
        <p>{error}</p>
        <button onClick={() => navigate('/', { replace: true })}>返回首页</button>
      </div>
    )
  }

  return (
    <div className="redirect-loading">
      <h2>正在登录...</h2>
      <p>请稍候，页面即将跳转</p>
    </div>
  )
}
