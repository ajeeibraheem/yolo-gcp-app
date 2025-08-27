<script setup lang="ts">
/**
 * /images — universal viewer for ZIP, folder, or separate-image datasets
 * Uses:
 *  GET /datasets/:id/images       -> paths + optional labels
 *  GET /datasets/:id/image-urls   -> signed/proxy URLs for current page
 */

type YoloBox = { class_id:number; x_center:number; y_center:number; width:number; height:number }
type ImageDoc = {
  _id?: string
  image_path?: string
  path?: string
  file?: string
  filename?: string
  labels?: YoloBox[]
  url?: string | null
  gcs_uri?: string
}
type UrlItem = { image_path: string; url: string | null; expires_at: string | null }

const route  = useRoute()
const router = useRouter()

const cfg = useRuntimeConfig()
const API = (cfg.public.apiBase || 'http://localhost:8080').replace(/\/$/, '')

// Query params from list page
const qId           = computed(() => (route.query.id ?? '') as string)
const qName         = computed(() => (route.query.name ?? '') as string)
const qSourcePrefix = computed(() => (route.query.source_prefix ?? '') as string)
const qSourceZip    = computed(() => (route.query.source_zip ?? '') as string)

// State
const dataset   = ref<any>(null)
const images    = ref<ImageDoc[]>([])
const total     = ref(0)
const page      = ref(Number(route.query.page ?? 1))
const pageSize  = ref(Number(route.query.page_size ?? 30))
const q         = ref<string>((route.query.q as string) || '')
const loading   = ref(false)
const errorMsg  = ref<string | null>(null)
const showBoxes = ref(true)

// Track <img> failures (avoid re-looping broken src)
const imgFailed = reactive<Record<string, boolean>>({})

// Hints (for header)
const seedDataset = computed(() => ({
  _id: qId.value || undefined,
  name: qName.value || undefined,
  source_prefix: qSourcePrefix.value || undefined,
  source_zip: qSourceZip.value || undefined,
}))
const datasetType = computed<'prefix'|'zip'|'unknown'>(() => {
  if (dataset.value?.source_prefix) return 'prefix'
  if (dataset.value?.source_zip)    return 'zip'
  return 'unknown'
})
const usingSigned = computed(() => images.value.some(i => i.url && /^https?:\/\//i.test(i.url)))

function syncQuery() {
  router.replace({
    query: {
      id: qId.value,
      ...(qName.value ? { name: qName.value } : {}),
      ...(qSourcePrefix.value ? { source_prefix: qSourcePrefix.value } : {}),
      ...(qSourceZip.value ? { source_zip: qSourceZip.value } : {}),
      ...(q.value ? { q: q.value } : {}),
      page: String(page.value),
      page_size: String(pageSize.value),
    },
  })
}

async function $get<T>(p: string, params?: Record<string, any>) {
  return await $fetch<T>(`${API}${p}`, { params })
}

async function ensureDataset() {
  dataset.value = { ...seedDataset.value }
  if (!qId.value) { errorMsg.value = 'Missing dataset id (?id=...)'; return }
  try {
    const d = await $get(`/datasets/${qId.value}`)
    dataset.value = d
  } catch (e:any) {
    errorMsg.value = e?.data?.detail || e?.message || String(e)
  }
}

async function loadImages() {
  if (!qId.value) return
  loading.value = true; errorMsg.value = null
  try {
    // Fetch metadata+labels and signed/proxy URLs in parallel
    const params = { page: page.value, page_size: pageSize.value, q: q.value || undefined }
    const [meta, urls] = await Promise.allSettled([
      $get<{items:ImageDoc[], total:number, page:number, page_size:number}>(`/datasets/${qId.value}/images`, params),
      $get<{items:UrlItem[], total:number, page:number, page_size:number}>(`/datasets/${qId.value}/image-urls`, params),
    ])

    // images metadata
    if (meta.status === 'fulfilled') {
      total.value = meta.value.total
      images.value = meta.value.items
    } else {
      throw meta.reason
    }

    // merge URLs by image_path (if available)
    if (urls.status === 'fulfilled') {
      const map = new Map<string,string | null>()
      for (const it of urls.value.items) map.set(it.image_path, it.url)
      images.value = images.value.map(i => {
        const key = i.image_path || i.path || i.file || i.filename || ''
        const mergedUrl = map.get(key) ?? i.url ?? null
        return { ...i, url: mergedUrl }
      })
    } else {
      // If the URL endpoint failed (e.g., no signer locally), we just fall back to proxy route.
      // No throw here; page still works via /datasets/:id/image?path=...
    }

    // reset per-item failures
    for (const k of Object.keys(imgFailed)) delete imgFailed[k]
  } catch (e:any) {
    errorMsg.value = e?.data?.detail || e?.message || String(e)
  } finally { loading.value = false }
}

watch([page, pageSize], () => { syncQuery(); loadImages() })
watch(q, () => { page.value = 1; syncQuery(); loadImages() })
watch(() => route.query.id, async () => { page.value = 1; await ensureDataset(); await loadImages() })
onMounted(async () => { await ensureDataset(); await loadImages() })

/** Display src preference:
 *  - If `url` is an http(s) (signed/proxy), use it (no backend proxy per image).
 *  - Otherwise fallback to backend proxy /datasets/:id/image?path=...
 */
function srcFor(img: ImageDoc) {
  if (img.url && /^https?:\/\//i.test(img.url)) return img.url
  const p = img.image_path || img.path || img.file || img.filename || ''
  return `${API}/datasets/${qId.value}/image?path=${encodeURIComponent(p)}`
}

function yoloStyle(b: YoloBox) {
  return {
    left:   ((b.x_center - b.width / 2) * 100) + '%',
    top:    ((b.y_center - b.height / 2) * 100) + '%',
    width:  (b.width * 100) + '%',
    height: (b.height * 100) + '%',
  }
}

// Lightbox
const modalOpen = ref(false)
const active = ref<ImageDoc | null>(null)
function openModal(img: ImageDoc) { active.value = img; modalOpen.value = true }
function closeModal() { modalOpen.value = false; active.value = null }
</script>

<template>
  <div class="max-w-7xl mx-auto p-6 space-y-5">
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold">Dataset images</h1>
        <p class="text-sm text-gray-500">
          <span v-if="dataset?.name">Name: <span class="font-medium">{{ dataset.name }}</span></span>
          <span v-if="datasetType==='prefix'" class="ml-2 px-2 py-0.5 text-xs rounded bg-emerald-50 text-emerald-700">GCS prefix</span>
          <span v-else-if="datasetType==='zip'" class="ml-2 px-2 py-0.5 text-xs rounded bg-sky-50 text-sky-700">ZIP (on-demand)</span>
          <span v-if="usingSigned" class="ml-2 px-2 py-0.5 text-xs rounded bg-indigo-50 text-indigo-700">signed URLs</span>
        </p>
      </div>
      <NuxtLink to="/datasets" class="text-blue-600 hover:underline">← Back</NuxtLink>
    </div>

    <!-- Controls -->
    <div class="flex flex-wrap items-center gap-3 bg-white rounded-xl shadow-sm p-3">
      <div class="flex items-center gap-2">
        <label class="text-sm text-gray-500">Search</label>
        <input v-model.trim="q" type="search" placeholder="filename contains…" class="border rounded px-2 py-1 w-64" />
      </div>
      <div class="flex items-center gap-2">
        <label class="text-sm text-gray-500">Page size</label>
        <select v-model.number="pageSize" class="border rounded px-2 py-1">
          <option :value="30">30</option><option :value="60">60</option><option :value="90">90</option>
        </select>
      </div>
      <div class="flex items-center gap-2 ml-auto">
        <label class="text-sm text-gray-500">Boxes</label>
        <button class="px-3 py-1.5 rounded-lg text-sm" :class="showBoxes ? 'bg-emerald-600 text-white' : 'bg-gray-100'"
                @click="showBoxes = !showBoxes">
          {{ showBoxes ? 'On' : 'Off' }}
        </button>
      </div>
    </div>

    <!-- Errors / loading -->
    <div v-if="errorMsg" class="p-3 rounded bg-red-50 text-red-700">{{ errorMsg }}</div>
    <div v-if="loading" class="text-gray-500">Loading…</div>

    <!-- Grid -->
    <div v-if="!loading" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
      <div v-for="img in images" :key="img._id || img.image_path || img.path || img.file || img.filename"
           class="bg-white rounded-xl shadow-sm p-3">
        <div class="relative rounded overflow-hidden bg-gray-50 cursor-zoom-in" @click="openModal(img)">
          <img
            v-if="!imgFailed[img.image_path || img.path || img.file || img.filename || img.url || '']"
            :src="srcFor(img)"
            :alt="img.image_path || img.path || img.file || img.filename || 'image'"
            class="w-full h-auto"
            loading="lazy"
            @error="imgFailed[img.image_path || img.path || img.file || img.filename || img.url || ''] = true"
          />
          <div v-else class="w-full aspect-[4/3] grid place-items-center text-gray-500">
            Preview not available
          </div>

          <div v-if="showBoxes && img.labels?.length" class="absolute inset-0 pointer-events-none">
            <div v-for="(b, i) in img.labels" :key="i" class="absolute border-2 border-emerald-500/80 rounded" :style="yoloStyle(b)"/>
          </div>
        </div>
        <div class="mt-2 text-sm">
          <div class="truncate" :title="img.image_path || img.path || img.file || img.filename || img.url">{{ img.image_path || img.path || img.file || img.filename || img.url }}</div>
          <div class="text-gray-500">{{ img.labels?.length || 0 }} label(s)</div>
        </div>
      </div>

      <div v-if="!images.length" class="col-span-full text-center text-gray-500 py-10">No images found.</div>
    </div>

    <!-- Pagination -->
    <div class="flex items-center justify-center gap-2">
      <button class="px-3 py-2 rounded bg-white shadow disabled:opacity-50" :disabled="page <= 1" @click="page--">Prev</button>
      <span class="text-sm">Page {{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }}</span>
      <button class="px-3 py-2 rounded bg-white shadow disabled:opacity-50" :disabled="page * pageSize >= total" @click="page++">Next</button>
    </div>

    <!-- Lightbox -->
    <div v-if="modalOpen" class="fixed inset-0 bg-black/70 z-50 grid place-items-center p-4" @click.self="closeModal">
      <div class="bg-white rounded-2xl max-w-6xl w-full overflow-hidden">
        <div class="flex items-center justify-between px-4 py-3 border-b">
          <div class="truncate text-sm text-gray-600">{{ (active?.image_path || active?.path || active?.file || active?.filename || active?.url) }}</div>
          <div class="flex items-center gap-3">
            <label class="text-sm text-gray-500">Boxes</label>
            <input type="checkbox" v-model="showBoxes" />
            <button class="px-3 py-1 rounded bg-gray-100" @click="closeModal">Close</button>
          </div>
        </div>
        <div class="p-4">
          <div class="relative">
            <img v-if="active && !imgFailed[active.image_path || active.path || active.file || active.filename || active.url || '']"
                 :src="srcFor(active)" class="w-full h-auto rounded" />
            <div v-else class="w-full aspect-[4/3] bg-gray-100 grid place-items-center rounded text-gray-500">No preview</div>
            <div v-if="active && showBoxes && active.labels?.length" class="absolute inset-0 pointer-events-none">
              <div v-for="(b, i) in active.labels" :key="i" class="absolute border-2 border-emerald-500/80 rounded" :style="yoloStyle(b)" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
