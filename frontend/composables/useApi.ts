export function useApi() {
  const config = useRuntimeConfig()
  const base = config.public.apiBase.replace(/\/$/, '')
  const $post = async <T>(path: string, body: any): Promise<T> =>
    await $fetch<T>(`${base}${path}`, { method: 'POST', body, headers: { 'Content-Type': 'application/json' } })
  const $get  = async <T>(path: string, params?: Record<string, any>): Promise<T> =>
    await $fetch<T>(`${base}${path}`, { method: 'GET', params })
  return { $post, $get, base }
}
