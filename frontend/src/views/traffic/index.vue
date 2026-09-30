<template>
  <section class="page" data-module="traffic">
    <header class="page-head">
      <div>
        <h2>占道许可管理</h2>
        <p class="page-desc">维护占道许可，围绕许可编号、申请单位、占道位置、占道面积做登记、筛选、整表导入与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记占道许可</button>
        <button class="btn" type="button" :disabled="importing" @click="pickFile">
          {{ importing ? '导入中…' : '整表导入' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出占道许可清单</button>
        <input
          ref="fileInput"
          type="file"
          accept=".xlsx,.xlsm,.csv"
          hidden
          @change="onFilePicked"
        />
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>许可编号</span>
        <input v-model="keyword" placeholder="按许可编号检索" />
      </label>
      <label class="filter-item">
        <span>许可状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="importResult" class="import-panel" :class="{ 'has-failures': importResult.failed }">
      <div class="import-summary">
        <strong>{{ importResult.failed ? '导入完成，部分行未处理' : '导入完成' }}</strong>
        <span>{{ importResult.summary }}</span>
        <button class="link" type="button" @click="importResult = null">收起</button>
      </div>
      <table v-if="importResult.failures.length" class="data-table import-failures">
        <thead>
          <tr>
            <th>表格行号</th>
            <th>许可编号</th>
            <th>申请单位</th>
            <th>占道位置</th>
            <th>未处理原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="failure in importResult.failures" :key="failure.line">
            <td>第 {{ failure.line }} 行</td>
            <td>{{ failure.data['许可编号'] || '—' }}</td>
            <td>{{ failure.data['申请单位'] || '—' }}</td>
            <td>{{ failure.data['占道位置'] || '—' }}</td>
            <td class="error-text">{{ failure.reason }}</td>
          </tr>
        </tbody>
      </table>
    </div>

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
          <td :colspan="columns.length + 1" class="empty-state">暂无占道许可数据，可先登记或整表导入</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条占道许可记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

interface ImportFailure {
  line: number
  reason: string
  data: Record<string, string>
}

interface ImportResult {
  total: number
  created: number
  updated: number
  noted: number
  unchanged: number
  failed: number
  summary: string
  failures: ImportFailure[]
}

const ENDPOINT = '/api/traffic'
const columns = ["许可编号", "申请单位", "占道位置", "占道面积", "起止日期", "审批人员", "恢复期限", "许可状态", "备注"]
const actions = ["提交审批", "确认批准", "确认恢复"]
const statuses = ["待审批", "已批准", "施工中", "已恢复"]
const stats = [{"label": "待审批许可", "value": 0}, {"label": "施工中占道", "value": 0}, {"label": "逾期未恢复", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

function buildQuery() {
  const params = new URLSearchParams()
  if (keyword.value.trim()) {
    params.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  // 导出带上和列表完全一致的过滤条件，另存下来的清单就是当前看到的范围
  window.open(`${ENDPOINT}/export${buildQuery()}`, '_blank')
}

function openCreate() {
  errorMessage.value = '占道许可登记入口尚未接入审批流'
}

function pickFile() {
  fileInput.value?.click()
}

async function onFilePicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  // 允许同一个文件再次选择；不清空的话重复选同一文件不会触发 change
  input.value = ''
  if (!file) {
    return
  }
  importing.value = true
  errorMessage.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    const response = await request(`${ENDPOINT}/import`, { method: 'POST', body: form })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(payload?.detail ? String(payload.detail) : '整表导入失败，请检查文件后重试')
    }
    importResult.value = payload as ImportResult
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '整表导入失败'
  } finally {
    importing.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('占道许可动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '占道许可操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}${buildQuery()}`)
    if (!response.ok) {
      throw new Error('占道许可列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '占道许可列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.import-panel {
  border: 1px solid var(--border, #d9d9d9);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 12px;
  background: #f6ffed;
}
.import-panel.has-failures {
  background: #fffbe6;
}
.import-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  align-items: center;
  font-size: 13px;
}
.import-failures {
  margin-top: 10px;
}
</style>
