<script setup lang="ts">
const { $get } = useApi()
const items = ref<any[]>([]); const loading = ref(false)
async function load(){ loading.value=true; try{ const resp = await $get<{items:any[],count:number}>('/datasets'); items.value = resp.items } finally { loading.value=false } }
onMounted(load)
</script>
<template>
  <div class="max-w-6xl mx-auto p-8">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-semibold">Datasets</h1>
      <NuxtLink to="/import" class="px-3 py-2 rounded-xl bg-black text-white">Import more</NuxtLink>
    </div>
    <div class="bg-white rounded-2xl shadow-sm">
      <table class="w-full text-left">
        <thead class="text-xs uppercase text-gray-500"><tr><th class="p-3">Name</th><th class="p-3">Created</th><th class="p-3">Updated</th><th class="p-3">Source</th><th class="p-3"></th></tr></thead>
        <tbody>
          <tr v-for="d in items" :key="d._id" class="border-t">
            <td class="p-3 font-medium">{{ d.name }}</td>
            <td class="p-3">{{ d.created_at ? new Date(d.created_at).toLocaleString() : '—' }}</td>
            <td class="p-3">{{ d.updated_at ? new Date(d.updated_at).toLocaleString() : '—' }}</td>
            <td class="p-3 text-xs">
              <div v-if="d.source_prefix">prefix: {{ d.source_prefix }}</div>
              <div v-else-if="d.source_zip">zip: {{ d.source_zip }}</div>
              <div v-else>—</div>
            </td>
            <td class="p-3"><NuxtLink
  class="text-blue-600 hover:underline"
  :to="{
    path: '/images',
    query: {
      id: d._id,
      name: d.name,
      ...(d.source_prefix ? { source_prefix: d.source_prefix } : {}),
      ...(d.source_zip ? { source_zip: d.source_zip } : {}),
    }
  }"
>
  View images
</NuxtLink></td>
          </tr>
          <tr v-if="!items.length && !loading"><td colspan="5" class="p-6 text-center text-gray-500">No datasets yet.</td></tr>
        </tbody>
      </table>
      <div v-if="loading" class="p-6 text-center">Loading…</div>
    </div>
  </div>
</template>
