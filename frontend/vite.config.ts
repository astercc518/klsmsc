import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const buildStamp = new Date().toISOString()

// https://vitejs.dev/config/
export default defineConfig({
  define: {
    __APP_BUILD_STAMP__: JSON.stringify(buildStamp),
  },
  plugins: [
    vue(),
    {
      name: 'inject-build-meta',
      transformIndexHtml(html) {
        return html.replace(
          '</head>',
          `  <meta name="app-build-stamp" content="${buildStamp}" />\n</head>`,
        )
      },
    },
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('element-plus')) {
              return 'element-plus';
            }
            if (id.includes('echarts')) {
              return 'echarts';
            }
            if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) {
              return 'vue-vendor';
            }
            return 'vendor';
          }
        }
      }
    }
  },
  server: {
    port: 5173,  // 使用Vite默认端口，避免与Grafana(3000)冲突
    host: '0.0.0.0',  // 允许外部访问
    proxy: {
      '/api': {
        // 根据实际部署情况修改
        // 如果前后端在同一服务器，使用 localhost
        // 如果前后端在不同服务器，使用实际IP或域名
        target: process.env.VITE_API_TARGET || 'http://103.246.244.237:8000',
        changeOrigin: true,
        secure: false,
        // 不重写路径，保持 /api 前缀
      },
    },
  },
})

