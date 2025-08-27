<script setup lang="ts">
/**
 * Dataset Images Page
 * - GET  /datasets/:id
 * - GET  /datasets/:id/images?page=&page_size=&q=
 * - GET  /datasets/:id/image?path=...   (proxy to GCS for previews)
 */

type YoloBox = { class_id:number; x_center:number; y_center:number; width:number; height:number }
type ImageDoc = { _id?:string; image_path:string; labels?:YoloBox[] }

const route = useRoute()
const router = useRouter()
const id = computed(() => route.params.id as string)

const cfg = useRuntimeConfig()
const API = (cfg.public.apiBase || 'http://localhost:8080').replace(/\/$/, '')

const dataset   = ref<any>(null)
const images    = ref<ImageDoc[]>([])
const total     = ref(0)
const page      = ref(Number(route.query.page ?? 1))
const pageSize  = ref(Number(route.query.page_size ?? 30))
const q         = ref<string>((route.query.q as string) || '')
const loading   = ref(false)
const errorMsg  = ref<string | null>(null)
const showBoxes = ref(true)
const canPreview = computed(() => Boolean(dataset.value?.source_prefix))

function syncQuery() {
  router.replace({
    query: {
      ...(q.value ? { q: q.value } : {}),
      page: String(page.value),
      page_size: String(pageSize.value),
    },
  })
}

async function $get<T>(p: string, params?: Record<string, any>) {
  return await $fetch<T>(`${API}${p}`, { method: 'GET', params })
}

async function loadDataset() {
  dataset.value = await $get(`/datasets/${id.value}`)
}

async function loadImages() {
  loading.value = true; errorMsg.value = null
  try {
    const resp = await $get<{ items: ImageDoc[]; total: number; page: number; page_size: number }>(
      `/datasets/${id.value}/images`,
      { page: page.value, page_size: pageSize.value, q: q.value || undefined }
    )
    images.value = resp.items
    total.value = resp.total
  } catch (e: any) {
    errorMsg.value = e?.data?.detail || e?.message || String(e)
  } finally {
    loading.value = false
  }
}

watch([page, pageSize], () => { syncQuery(); loadImages() })
watch(q, () => { page.value = 1; syncQuery(); loadImages() })
onMounted(async () => { await loadDataset(); await loadImages() })

function imgUrl(p: string) {
  return `${API}/datasets/${id.value}/image?path=${encodeURIComponent(p)}`
}

// Lightbox
const modalOpen = ref(false)
const active = ref<ImageDoc | null>(null)
function openModal(img: ImageDoc) { if (!canPreview.value) return; active.value = img; modalOpen.value = true }
function closeModal() { modalOpen.value = false; active.value = null }

// computed helpers
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
function yoloStyle(b: YoloBox) {
  return {
    left:   ((b.x_center - b.width / 2) * 100) + '%',
    top:    ((b.y_center - b.height / 2) * 100) + '%',
    width:  (b.width * 100) + '%',
    height: (b.height * 100) + '%',
  }
}
</script>

<template>
  <div class="max-w-7xl mx-auto p-6 space-y-5">
    <!-- Header -->
    <div class="flex flex-wrap items-center gap-3 justify-between">
      <div>
        <h1 class="text-2xl font-semibold">Dataset images</h1>
        <p class="text-sm text-gray-500">
          <span v-if="dataset?.name">Name: <span class="font-medium">{{ dataset.name }}</span></span>
          <span
            v-if="canPreview"
            class="ml-2 inline-block px-2 py-0.5 text-xs rounded bg-emerald-50 text-emerald-700"
          >Preview enabled</span>
          <span
            v-else
            class="ml-2 inline-block px-2 py-0.5 text-xs rounded bg-amber-50 text-amber-700"
            title="This dataset came from a ZIP; previews need a GCS prefix."
          >Preview unavailable</span>
        </p>
      </div>
      <NuxtLink to="/datasets" class="text-blue-600 hover:underline">← Back to datasets</NuxtLink>
    </div>

    <!-- Controls -->
    <div class="flex flex-wrap items-center gap-3 bg-white rounded-xl shadow-sm p-3">
      <div class="flex items-center gap-2">
        <label class="text-sm text-gray-500">Search</label>
        <input
          v-model.trim="q"
          type="search"
          placeholder="filename contains…"
          class="border rounded px-2 py-1 w-64"
        />
      </div>

      <div class="flex items-center gap-2">
        <label class="text-sm text-gray-500">Page size</label>
        <select v-model.number="pageSize" class="border rounded px-2 py-1">
          <option :value="30">30</option>
          <option :value="60">60</option>
          <option :value="90">90</option>
        </select>
      </div>

      <div class="flex items-center gap-2 ml-auto">
        <label class="text-sm text-gray-500">Boxes</label>
        <button
          class="px-3 py-1.5 rounded-lg text-sm"
          :class="showBoxes ? 'bg-emerald-600 text-white' : 'bg-gray-100'"
          @click="showBoxes = !showBoxes"
        >{{ showBoxes ? 'On' : 'Off' }}</button>
      </div>
    </div>

    <!-- Errors & loading -->
    <div v-if="errorMsg" class="p-3 rounded bg-red-50 text-red-700">{{ errorMsg }}</div>
    <div v-if="loading" class="text-gray-500">Loading…</div>

    <!-- Grid -->
    <div
      v-if="!loading"
      class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4"
    >
      <div
        v-for="img in images"
        :key="img._id || img.image_path"
        class="bg-white rounded-xl shadow-sm p-3"
      >
        <div
          class="relative rounded overflow-hidden cursor-zoom-in bg-gray-50"
          @click="openModal(img)"
        >
          <img
            v-if="canPreview"
            :src="imgUrl(img.image_path)"
            :alt="img.image_path"
            class="w-full h-auto"
            loading="lazy"
            referrerpolicy="no-referrer"
          />
          <div
            v-else
            class="w-full aspect-[4/3] grid place-items-center text-gray-500"
          >No preview</div>

          <!-- YOLO boxes overlay (normalized 0..1) -->
          <div
            v-if="canPreview && showBoxes && img.labels?.length"
            class="absolute inset-0 pointer-events-none"
          >
            <div
              v-for="(b, i) in img.labels"
              :key="i"
              class="absolute border-2 border-emerald-500/80 rounded"
              :style="yoloStyle(b)"
            />
          </div>
        </div>

        <div class="mt-2 text-sm">
          <div class="truncate" :title="img.image_path">{{ img.image_path }}</div>
          <div class="text-gray-500">{{ img.labels?.length || 0 }} label(s)</div>
        </div>
      </div>

      <div v-if="!images.length" class="col-span-full text-center text-gray-500 py-10">
        No images found.
      </div>
    </div>

    <!-- Pagination -->
    <div class="flex items-center justify-center gap-2">
      <button
        class="px-3 py-2 rounded bg-white shadow disabled:opacity-50"
        :disabled="page <= 1"
        @click="page--"
      >Prev</button>
      <span class="text-sm">Page {{ page }} / {{ pageCount }}</span>
      <button
        class="px-3 py-2 rounded bg-white shadow disabled:opacity-50"
        :disabled="page >= pageCount"
        @click="page++"
      >Next</button>
    </div>

    <!-- Lightbox -->
    <div
      v-if="modalOpen"
      class="fixed inset-0 bg-black/70 z-50 grid place-items-center p-4"
      @click.self="closeModal"
    >
      <div class="bg-white rounded-2xl max-w-6xl w-full overflow-hidden">
        <div class="flex items-center justify-between px-4 py-3 border-b">
          <div class="truncate text-sm text-gray-600">{{ active?.image_path }}</div>
          <div class="flex items-center gap-3">
            <label class="text-sm text-gray-500">Boxes</label>
            <input type="checkbox" v-model="showBoxes" />
            <button class="px-3 py-1 rounded bg-gray-100" @click="closeModal">Close</button>
          </div>
        </div>
        <div class="p-4">
          <div class="relative">
            <img
              v-if="active && canPreview"
              :src="imgUrl(active.image_path)"
              class="w-full h-auto rounded"
              loading="eager"
            />
            <div
              v-else
              class="w-full aspect-[4/3] bg-gray-100 grid place-items-center rounded text-gray-500"
            >No preview</div>

            <div
              v-if="active && canPreview && showBoxes && active.labels?.length"
              class="absolute inset-0 pointer-events-none"
            >
              <div
                v-for="(b, i) in active.labels"
                :key="i"
                class="absolute border-2 border-emerald-500/80 rounded"
                :style="yoloStyle(b)"
              />
            </div>
          </div>

          <div class="mt-4">
            <h3 class="font-medium mb-2">Labels</h3>
            <div v-if="active?.labels?.length" class="grid sm:grid-cols-2 md:grid-cols-3 gap-2">
              <div v-for="(b, i) in active.labels" :key="i" class="text-sm bg-gray-50 rounded p-2">
                <div>class_id: <span class="font-mono">{{ b.class_id }}</span></div>
                <div class="text-xs text-gray-500">
                  x={{ b.x_center.toFixed(3) }},
                  y={{ b.y_center.toFixed(3) }},
                  w={{ b.width.toFixed(3) }},
                  h={{ b.height.toFixed(3) }}
                </div>
              </div>
            </div>
            <div v-else class="text-sm text-gray-500">No labels</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
