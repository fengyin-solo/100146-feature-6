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

    <form class="filter-bar" @submit.prevent="applySearch">
      <label class="filter-item">
        <span>设施编码</span>
        <input v-model.trim="filters.code" placeholder="如 ROAD-0001，可省略连字符" />
      </label>
      <label class="filter-item">
        <span>道路名称</span>
        <input v-model.trim="filters.name" placeholder="按道路名称关键字检索" />
      </label>
      <label class="filter-item">
        <span>道路等级</span>
        <input
          v-model.trim="filters.level"
          list="road-level-options"
          placeholder="如 快速路、主干路、次干路、支路"
        />
        <datalist id="road-level-options">
          <option v-for="option in roadLevels" :key="option" :value="option" />
        </datalist>
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
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条道路设施记录</span>
      <div class="pagination">
        <button class="btn" type="button" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ totalPages }} 页</span>
        <button
          class="btn"
          type="button"
          :disabled="page >= totalPages"
          @click="goPage(page + 1)"
        >
          下一页
        </button>
      </div>
    </footer>
    <p v-if="errorMessage" class="foot-error error-text">{{ errorMessage }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/road'
const PAGE_SIZE = 10
const columns = ["设施编码", "道路名称", "道路等级", "起止桩号", "路面结构", "管养单位", "建成年份", "设施状态"]
const actions = ["办理移交", "标记观测", "封闭设施"]
const statuses = ["待移交", "正常养护", "重点观测", "封闭施工"]
const roadLevels = ["快速路", "主干路", "次干路", "支路"]
const stats = [{"label": "在养道路", "value": 0}, {"label": "重点观测道路", "value": 0}, {"label": "管养里程", "value": 0}]

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const errorMessage = ref('')
// 输入框里的条件（编辑中）；applied 记录上次实际参与查询的条件，导出与翻页都用它
const filters = ref({ code: '', name: '', level: '' })
const applied = ref({ code: '', name: '', level: '' })

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const hasAppliedFilters = computed(() =>
  Boolean(applied.value.code || applied.value.name || applied.value.level),
)
const emptyText = computed(() =>
  errorMessage.value
    ? '道路设施列表读取失败'
    : hasAppliedFilters.value
      ? '没有符合当前条件的道路设施，请调整筛选条件后重试'
      : '暂无道路设施数据，可先登记道路设施',
)

/**
 * 校验设施编码写法，并归一化成 ROAD-0001 形式。
 * 允许的写法：ROAD-1、road 1、ROAD_0001、ROAD0001 等；不合法时讲清原因。
 */
function normalizeCode(raw: string): { code: string } | { error: string } {
  const value = raw.trim()
  if (!value) return { code: '' }
  if (/^ROAD-\d{4}$/.test(value)) return { code: value }
  const matched = value.match(/^ROAD[-_－— \t]*(\d{1,4})$/i)
  if (!matched) {
    if (!value.toUpperCase().startsWith('ROAD')) {
      return { error: '设施编码需以 ROAD 开头，例如 ROAD-0001' }
    }
    if (!value.includes('-') && !/\d/.test(value)) {
      return { error: '设施编码缺少编号部分，正确写法如 ROAD-0001' }
    }
    return { error: '设施编码格式不正确，应为 ROAD- 加 4 位数字，例如 ROAD-0001' }
  }
  return { code: `ROAD-${Number(matched[1]).toString().padStart(4, '0')}` }
}

function queryParam(name: string): string {
  const value = route.query[name]
  return Array.isArray(value) ? String(value[0] ?? '') : String(value ?? '')
}

/**
 * 把当前条件与页码写进地址栏：离开页面再返回时条件和页码都还在。
 * 地址栏真的发生变化时，由 route 侦听器统一触发加载；没有变化（例如重复查询）则直接加载。
 */
function syncToUrl(targetPage = page.value) {
  const query: Record<string, string> = {}
  if (applied.value.code) query.code = applied.value.code
  if (applied.value.name) query.name = applied.value.name
  if (applied.value.level) query.level = applied.value.level
  if (targetPage > 1) query.page = String(targetPage)
  const signature = new URLSearchParams(query).toString()
  const current = new URLSearchParams(
    Object.entries(route.query)
      .filter(([, value]) => value !== undefined && value !== null)
      .map(([key, value]) => [key, Array.isArray(value) ? String(value[0]) : String(value)]),
  ).toString()
  if (signature === current) {
    void reload()
  } else {
    void router.replace({ query })
  }
}

function restoreFromRoute() {
  filters.value = {
    code: queryParam('code'),
    name: queryParam('name'),
    level: queryParam('level'),
  }
  applied.value = { ...filters.value }
  const parsedPage = Number.parseInt(queryParam('page'), 10)
  page.value = Number.isFinite(parsedPage) && parsedPage >= 1 ? parsedPage : 1
}

let requestSeq = 0

async function reload() {
  errorMessage.value = ''
  const requestedPage = page.value
  const seq = ++requestSeq
  const params = new URLSearchParams({ page: String(requestedPage), size: String(PAGE_SIZE) })
  if (applied.value.code) params.set('code', applied.value.code)
  if (applied.value.name) params.set('name', applied.value.name)
  if (applied.value.level) params.set('level', applied.value.level)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      const detail = await readErrorDetail(response)
      throw new Error(detail || '道路设施列表读取失败')
    }
    const payload = await response.json()
    if (seq !== requestSeq) return // 期间已发起更新的查询，丢弃这份过期结果
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    page.value = payload.page ?? requestedPage
  } catch (error) {
    if (seq !== requestSeq) return
    rows.value = []
    total.value = 0
    // 请求的页码不存在时，页码指示回到第 1 页；地址栏保留原页码，返回场景仍能看到原因
    page.value = 1
    errorMessage.value = error instanceof Error ? error.message : '道路设施列表读取失败'
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown }
    if (typeof payload.detail === 'string') return payload.detail
  } catch {
    // 后端没返回 JSON 时退回通用说明
  }
  return ''
}

function applySearch() {
  const result = normalizeCode(filters.value.code)
  if ('error' in result) {
    errorMessage.value = result.error
    return
  }
  errorMessage.value = ''
  applied.value = {
    code: result.code,
    name: filters.value.name.trim(),
    level: filters.value.level.trim(),
  }
  page.value = 1
  syncToUrl(1)
}

function resetFilters() {
  filters.value = { code: '', name: '', level: '' }
  applied.value = { code: '', name: '', level: '' }
  page.value = 1
  errorMessage.value = ''
  syncToUrl(1)
}

function goPage(target: number) {
  if (target < 1 || target > totalPages.value) return
  page.value = target
  syncToUrl(target)
}

function exportRows() {
  // 导出与列表共用同一套筛选条件，保证导出清单条数与页脚总数一致
  const params = new URLSearchParams()
  if (applied.value.code) params.set('code', applied.value.code)
  if (applied.value.name) params.set('name', applied.value.name)
  if (applied.value.level) params.set('level', applied.value.level)
  const suffix = params.toString()
  window.open(suffix ? `${ENDPOINT}/export?${suffix}` : `${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '道路设施登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json().catch(() => null)) as { message?: string } | null
    if (!response.ok || payload === null) {
      throw new Error(payload?.message || '道路设施动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '道路设施操作失败'
  }
}

let lastLoadedSignature = ''

watch(
  () => route.fullPath,
  () => {
    // 浏览器前进/后退、从其他页面返回，或本页写入条件后，按地址栏恢复条件与页码
    restoreFromRoute()
    // 同步写入（replace）造成的地址变化会再次触发本侦听器，用签名去重避免重复请求
    const signature = route.fullPath
    if (signature !== lastLoadedSignature) {
      lastLoadedSignature = signature
      void reload()
    }
  },
)

onMounted(() => {
  restoreFromRoute()
  lastLoadedSignature = route.fullPath
  void reload()
})
</script>
