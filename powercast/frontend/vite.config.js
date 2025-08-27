import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

//Izvoz konfiguracije za Vite

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 }
})
