import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/system-design-lab/',
  // Scenes live in 19-diagrams/scenes so the markdown renderer and this app read
  // the SAME files. That means importing from outside the visualizer root.
  server: { fs: { allow: ['..'] } },
})
