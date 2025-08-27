export default defineNuxtConfig({
  devtools: { enabled: true },
  modules: ['@nuxtjs/tailwindcss'],
  runtimeConfig: { public: { apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://localhost:8080' } },
  app: { head: { title: 'YOLO11n Dataset Importer', meta: [{ name: 'viewport', content: 'width=device-width, initial-scale=1' }] } }
})
