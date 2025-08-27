<script setup lang="ts">
import { useApi } from '~/composables/useApi'
import { resumableUpload } from '~/composables/useResumable'
const dataset = ref(''); const files = ref<FileList | null>(null); const busy = ref(false); const progress = ref(0); const status = ref<string| null>(null)
const { $post } = useApi()
function pathFor(file: File){ const anyFile=file as any; return (anyFile.webkitRelativePath && anyFile.webkitRelativePath.length>0)? anyFile.webkitRelativePath : file.name }
function contentType(file: File){ return file.type || (file.name.endsWith('.txt') ? 'text/plain' : 'application/octet-stream') }
async function start(){
  status.value=null; if(!dataset.value||!files.value||files.value.length===0) return; busy.value=true; progress.value=0
  try{
    const specs = Array.from(files.value).map(f=>({ path: pathFor(f), content_type: contentType(f) }))
    const init = await $post<{ prefix: string, items: { path: string, upload_url: string }[] }>('/imports/folder/initiate', { dataset_name: dataset.value, files: specs })
    const total = files.value.length; let done=0
    for(let i=0;i<total;i++){ const f=files.value[i]; const item=init.items[i]; await resumableUpload(f, item.upload_url, {}); done++; progress.value = Math.round((done/total)*100) }
    await $post('/imports/complete', { dataset_name: dataset.value, gcs_uri: init.prefix }); status.value='Folder upload queued for ingestion.'
  }catch(e:any){ status.value=e.message||String(e) }finally{ busy.value=false }
}
</script>
<template>
  <div class="bg-white rounded-2xl p-6 shadow-sm">
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div><label class="block text-sm font-medium mb-1">Dataset name</label><input v-model="dataset" class="w-full border rounded-xl px-3 py-2" placeholder="e.g., animals" /></div>
      <div class="md:col-span-2"><label class="block text-sm font-medium mb-1">Choose folder</label><input type="file" webkitdirectory directory multiple @change="(e:any)=> files = e.target.files" class="w-full" /><p class="text-xs text-gray-500 mt-1">Chromium-based browsers preserve folder structure.</p></div>
    </div>
    <div class="mt-4 flex items-center gap-3">
      <button @click="start" :disabled="busy || !dataset || !files" class="px-4 py-2 rounded-xl bg-black text-white disabled:opacity-50">{{ busy ? 'Uploading…' : 'Start Upload' }}</button>
      <div v-if="busy" class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden"><div class="h-full bg-gray-800" :style="{ width: progress + '%' }"></div></div>
      <span v-if="busy">{{ progress }}%</span>
    </div>
    <p v-if="status" class="mt-3 text-sm">{{ status }}</p>
  </div>
</template>
