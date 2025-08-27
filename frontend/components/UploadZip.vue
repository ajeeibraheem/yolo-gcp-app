<script setup lang="ts">
import { useApi } from '~/composables/useApi'
import { resumableUpload } from '~/composables/useResumable'
const dataset = ref(''); const file = ref<File | null>(null); const busy = ref(false); const progress = ref(0); const message = ref<string| null>(null)
const { $post } = useApi()
async function start() {
  message.value=null; if (!dataset.value || !file.value) return; busy.value=true
  try {
    const init = await $post<{ upload_url: string, gcs_uri: string }>('/imports/zip/initiate', { dataset_name: dataset.value, filename: file.value.name, content_type: file.value.type || 'application/zip' })
    await resumableUpload(file.value, init.upload_url, { onProgress: (u,t)=> progress.value = Math.round((u/t)*100) })
    await $post('/imports/complete', { dataset_name: dataset.value, gcs_uri: init.gcs_uri })
    message.value='Upload queued for ingestion.'
  } catch (e:any) { message.value = e.message || String(e) } finally { busy.value=false }
}
</script>
<template>
  <div class="bg-white rounded-2xl p-6 shadow-sm">
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div><label class="block text-sm font-medium mb-1">Dataset name</label><input v-model="dataset" class="w-full border rounded-xl px-3 py-2" placeholder="e.g., animals" /></div>
      <div class="md:col-span-2"><label class="block text-sm font-medium mb-1">ZIP file</label><input type="file" accept=".zip" @change="(e:any)=> file = e.target.files?.[0] || null" class="w-full" /></div>
    </div>
    <div class="mt-4 flex items-center gap-3">
      <button @click="start" :disabled="busy || !dataset || !file" class="px-4 py-2 rounded-xl bg-black text-white disabled:opacity-50">{{ busy ? 'Uploading…' : 'Start Upload' }}</button>
      <div v-if="busy" class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden"><div class="h-full bg-gray-800" :style="{ width: progress + '%' }"></div></div>
      <span v-if="busy">{{ progress }}%</span>
    </div>
    <p v-if="message" class="mt-3 text-sm">{{ message }}</p>
  </div>
</template>
