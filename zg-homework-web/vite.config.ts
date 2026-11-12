import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// 本模块可独立构建，不依赖仓库内其他模块
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // 开发环境走代理规避跨域，保留服务端的路径前缀。
  const proxyTarget = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(__dirname, 'src') },
    },
    server: {
      port: 5173,
      proxy: {
        // 服务端实际路径包含 /homework_api，代理时不得剥除。
        '/homework_api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            antd: ['antd'],
          },
        },
      },
    },
  }
})