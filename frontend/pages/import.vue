<script setup lang="ts">
const tab = ref<'zip' | 'folder' | 'images'>('zip')
</script>
<template>
  <div class="max-w-6xl mx-auto p-8">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-semibold">Import Datasets</h1>
      <NuxtLink to="/datasets" class="px-3 py-2 rounded-xl bg-white shadow">View datasets</NuxtLink>
    </div>
    <div class="flex gap-2 mb-6">
      <button class="px-4 py-2 rounded-xl shadow-sm" :class="tab==='zip' ? 'bg-black text-white' : 'bg-white'" @click="tab='zip'">Upload ZIP</button>
      <button class="px-4 py-2 rounded-xl shadow-sm" :class="tab==='folder' ? 'bg-black text-white' : 'bg-white'" @click="tab='folder'">Upload Folder</button>
      <button class="px-4 py-2 rounded-xl shadow-sm" :class="tab==='images' ? 'bg-black text-white' : 'bg-white'" @click="tab='images'">Upload Separate Images</button>
    </div>
    <div v-if="tab==='zip'"><UploadZip/></div>
    <div v-else-if="tab==='folder'"><UploadFolder/></div>
    <div v-else><UploadImages/></div>
  </div>
</template>
