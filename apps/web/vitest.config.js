import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const nm = (p) => path.resolve(__dirname, 'node_modules', p)

// 允许 vitest 解析 tests/web/ 下的文件以及 web/node_modules 中的依赖
export default defineConfig({
  plugins: [react()],
  server: {
    fs: {
      allow: ['..', '../..'],
    },
  },
  resolve: {
    alias: {
      vitest: nm('vitest'),
      '@testing-library/react': nm('@testing-library/react'),
      '@testing-library/user-event': nm('@testing-library/user-event'),
      '@testing-library/jest-dom': nm('@testing-library/jest-dom'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    globals: true,
    css: false,
    include: [
      'src/**/*.{test,spec}.?(c|m)[jt]s?(x)',
      '../../tests/web/**/*.{test,spec}.?(c|m)[jt]s?(x)',
    ],
  },
})