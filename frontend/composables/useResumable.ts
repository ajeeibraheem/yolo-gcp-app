type ProgressCallback = (uploaded: number, total: number) => void
export async function resumableUpload(file: File, sessionUrl: string, { chunkSize = 8 * 1024 * 1024, onProgress }: { chunkSize?: number, onProgress?: ProgressCallback } = {}) {
  const total = file.size
  let offset = await queryUploadedBytes(sessionUrl, total)
  while (offset < total) {
    const end = Math.min(offset + chunkSize, total)
    const chunk = file.slice(offset, end)
    const res = await fetch(sessionUrl, { method: 'PUT', headers: { 'Content-Length': String(end - offset), 'Content-Range': `bytes ${offset}-${end - 1}/${total}` }, body: chunk })
    if (res.status === 308) {
      const range = res.headers.get('Range'); if (range) { const m = range.match(/bytes=\d+-(\d+)/); offset = m ? parseInt(m[1], 10) + 1 : end } else { offset = end }
    } else if (res.ok) { offset = total } else { throw new Error(`Upload failed (${res.status})`) }
    onProgress?.(offset, total)
  }
}
async function queryUploadedBytes(sessionUrl: string, total: number): Promise<number> {
  const res = await fetch(sessionUrl, { method: 'PUT', headers: { 'Content-Range': `bytes */${total}` } })
  if (res.status === 308) { const range = res.headers.get('Range'); if (!range) return 0; const m = range.match(/bytes=\d+-(\d+)/); return m ? parseInt(m[1], 10) + 1 : 0 }
  if (res.ok) return total; return 0
}
