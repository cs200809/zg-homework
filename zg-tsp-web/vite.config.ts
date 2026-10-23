import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// 本模块可独立构建，不依赖仓库内其他模块
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // 开发环境走代理规避跨域；生产由 .env.production 指定直连地址
  const proxyTarget = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(__dirname, 'src') },
    },
    server: {
      port: 5173,
      proxy: {
        // 前端统一请求 /api/xxx，服务端实际路径是 /xxx（无 /api 前缀），
        // 因此必须 rewrite 去掉 /api，否则服务端返回 404。
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
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