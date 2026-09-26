<template>
  <section class="page" data-module="road">
    <header class="page-head">
      <div>
        <h2>道路设施管理</h2>
        <p class="page-desc">维护道路设施，围绕设施编码、道路名称、道路等级、起止桩号做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记道路设施</button>
        <button class="btn" type="button" @click="exportRows">导出道路设施清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length && !errorMessage">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span v-if="!errorMessage">共 {{ total }} 条道路设施记录</span>
      <div class="pagination">
        <button class="btn" type="button" :disabled="page <= 1" @click="goToPage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ pageCount }} 页</span>
        <button class="btn" type="button" :disabled="page >= pageCount" @click="goToPage(page + 1)">下一页</button>
      </div>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { LocationQuery } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/road'
const columns = ["设施编码", "道路名称", "道路等级", "起止桩号", "路面结构", "管养单位", "建成年份", "设施状态"]
const actions = ["办理移交", "标记观测", "封闭设施"]
const stats = [{"label": "在养道路", "value": 0}, {"label": "重点观测道路", "value": 0}, {"label": "管养里程", "value": 0}]

const PAGE_SIZE = 20
const STORAGE_KEY = 'road-list-query'
// 筛选框与接口参数的对应关系：界面用中文字段名，接口用英文参数名
const FILTER_PARAMS: Record<string, string> = { "设施编码": "code", "道路名称": "name", "道路等级": "level" }
const filterFields = columns.slice(0, 3)

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const errorMessage = ref('')
// filters 是输入框草稿，applied 是已生效的条件；列表、翻页、导出都以 applied 为准
const filters = ref<Record<string, string>>({})
const applied = ref<Record<string, string>>({})

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const hasConditions = computed(() => filterFields.some((field) => (applied.value[field] ?? '').trim() !== ''))
const emptyText = computed(() =>
  hasConditions.value
    ? '没有符合当前筛选条件的道路设施，可调整条件后重新查询'
    : '暂无道路设施数据，可先登记道路设施',
)

function buildQuery(source: Record<string, string>, targetPage: number): Record<string, string> {
  const query: Record<string, string> = {}
  for (const field of filterFields) {
    const value = (source[field] ?? '').trim()
    if (value) {
      query[FILTER_PARAMS[field]] = value
    }
  }
  if (targetPage > 1) {
    query.page = String(targetPage)
  }
  return query
}

function isEmptyQuery(query: LocationQuery): boolean {
  if (query.page != null) {
    return false
  }
  return filterFields.every((field) => query[FILTER_PARAMS[field]] == null)
}

function sameQuery(a: Record<string, string>, b: LocationQuery): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  for (const key of keys) {
    if (String(a[key] ?? '') !== String(b[key] ?? '')) {
      return false
    }
  }
  return true
}

function saveState() {
  try {
    const query = buildQuery(applied.value, page.value)
    if (Object.keys(query).length === 0) {
      sessionStorage.removeItem(STORAGE_KEY)
      return
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(query))
  } catch {
    /* 隐私模式等场景下写不进存储，跳过即可 */
  }
}

function readSavedState(): Record<string, string> | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return null
    }
    const parsed: unknown = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && Object.keys(parsed).length > 0) {
      return parsed as Record<string, string>
    }
  } catch {
    /* 存储内容损坏时当作没有保存过 */
  }
  return null
}

function clearSavedState() {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    /* 与 saveState 同理，静默跳过 */
  }
}

function applyFilters() {
  const query = buildQuery(filters.value, 1)
  if (sameQuery(query, route.query)) {
    page.value = 1
    void reload()
    return
  }
  void router.push({ query })
}

function resetFilters() {
  filters.value = {}
  clearSavedState()
  if (isEmptyQuery(route.query)) {
    applied.value = {}
    page.value = 1
    void reload()
    return
  }
  void router.push({ query: {} })
}

function goToPage(target: number) {
  void router.push({ query: buildQuery(applied.value, target) })
}

function exportRows() {
  // 导出跟随已生效的筛选条件，保证清单条数与屏幕上的总数一致
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = (applied.value[field] ?? '').trim()
    if (value) {
      params.set(FILTER_PARAMS[field], value)
    }
  }
  const suffix = params.toString()
  window.open(`${ENDPOINT}/export${suffix ? `?${suffix}` : ''}`, '_blank')
}

function openCreate() {
  errorMessage.value = '道路设施登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('道路设施动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '道路设施操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = (applied.value[field] ?? '').trim()
    if (value) {
      params.set(FILTER_PARAMS[field], value)
    }
  }
  params.set('page', String(page.value))
  params.set('size', String(PAGE_SIZE))
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    const payload: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      const detail = (payload as { detail?: unknown } | null)?.detail
      throw new Error(typeof detail === 'string' ? detail : '道路设施列表读取失败')
    }
    const data = payload as { items?: Row[]; total?: number } | null
    rows.value = data?.items ?? []
    total.value = data?.total ?? rows.value.length
  } catch (error) {
    rows.value = []
    total.value = 0
    errorMessage.value = error instanceof Error ? error.message : '道路设施列表读取失败'
  }
}

// 筛选条件与页码都落在地址栏：翻页、来回切换页面、浏览器前进后退后都能原样恢复
watch(
  () => route.query,
  (query) => {
    if (isEmptyQuery(query)) {
      const saved = readSavedState()
      if (saved) {
        void router.replace({ query: saved })
        return
      }
    }
    const next: Record<string, string> = {}
    for (const field of filterFields) {
      const raw = query[FILTER_PARAMS[field]]
      next[field] = typeof raw === 'string' ? raw : ''
    }
    filters.value = next
    applied.value = next
    const rawPage = Number(query.page)
    page.value = Number.isInteger(rawPage) && rawPage >= 1 ? rawPage : 1
    saveState()
    void reload()
  },
  { immediate: true },
)
</script>

<style scoped>
.pagination { display: flex; align-items: center; gap: 8px; }
.pagination .btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
