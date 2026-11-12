import { useEffect } from 'react'
import { BrowserRouter } from 'react-router-dom'

import AppRouter from './router'
import { useAuthStore } from './store/auth'

export default function App() {
  const init = useAuthStore((s) => s.init)

  // 启动时用本地 token 恢复登录态
  useEffect(() => {
    void init()
  }, [init])

  return (
    <BrowserRouter>
      <AppRouter />
    </BrowserRouter>
  )
}