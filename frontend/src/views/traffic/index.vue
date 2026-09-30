<template>
  <section class="page" data-module="traffic">
    <header class="page-head">
      <div>
        <h2>占道许可管理</h2>
        <p class="page-desc">维护占道许可，围绕许可编号、申请单位、占道位置、占道面积做登记、筛选与状态流转；支持整份表格导入。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记占道许可</button>
        <button class="btn" type="button" :disabled="importing" @click="triggerImport">
          {{ importing ? '正在导入…' : '导入占道许可表格' }}
        </button>
        <button class="btn" type="button" @click="downloadTemplate">下载导入模板</button>
        <button class="btn" type="button" @click="exportRows">导出占道许可清单</button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,text/csv"
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

    <div v-if="importResult" class="import-panel">
      <div class="import-summary">
        <strong>上次导入结果：</strong>
        本次新添 {{ importResult.created }} 条，更新恢复期限 {{ importResult.updated }} 条，
        补说明 {{ importResult.noted }} 条，共解析 {{ importResult.total }} 行，
        <span :class="importResult.failed ? 'error-text' : 'ok-text'">
          {{ importResult.failed }} 行未处理
        </span>
        <button class="link" type="button" @click="importResult = null">收起</button>
      </div>
      <table v-if="importResult.failures.length" class="data-table fail-table">
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
          <tr v-for="item in importResult.failures" :key="`${item.行号}-${item.许可编号}`">
            <td>{{ item.行号 }}</td>
            <td>{{ item.许可编号 || '—' }}</td>
            <td>{{ item.申请单位 || '—' }}</td>
            <td>{{ item.占道位置 || '—' }}</td>
            <td class="error-text">{{ item.原因 }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field.param" class="filter-item">
        <span>{{ field.label }}</span>
        <input v-model="filters[field.param]" :placeholder="`按${field.label}检索`" />
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
          <td v-for="column in columns" :key="column">{{ row[column] || '—' }}</td>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无占道许可数据，可先登记或导入占道许可</td>
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

type Row = Record<string, string | number | null>

interface FailureRow {
  行号: number
  许可编号: string
  申请单位: string
  占道位置: string
  原因: string
}

interface ImportResult {
  created: number
  updated: number
  noted: number
  failed: number
  total: number
  failures: FailureRow[]
}

const ENDPOINT = '/api/traffic'
const columns = ["许可编号", "申请单位", "占道位置", "占道面积", "起止日期", "审批人员", "恢复期限", "备注说明", "许可状态"]
const actions = ["提交审批", "确认批准", "确认恢复"]
const statuses = ["待审批", "已批准", "施工中", "已恢复"]
const stats = [{"label": "待审批许可", "value": 0}, {"label": "施工中占道", "value": 0}, {"label": "逾期未恢复", "value": 0}]
const TEMPLATE_HEADER = '许可编号,申请单位,占道位置,占道面积,起止日期,审批人员,恢复期限'

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({ keyword: '', unit: '', location: '' })
const filterFields = [
  { label: '许可编号', param: 'keyword' },
  { label: '申请单位', param: 'unit' },
  { label: '占道位置', param: 'location' },
]
const fileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)

function currentQuery() {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value.trim()) {
      params.set(key, value.trim())
    }
  }
  return params.toString()
}

function resetFilters() {
  filters.value = { keyword: '', unit: '', location: '' }
  void reload()
}

function exportRows() {
  // 导出范围与列表当前筛选保持一致，格式取 CSV，Excel 可直接打开
  const query = currentQuery()
  window.open(`${ENDPOINT}/export?${query ? `${query}&` : ''}format=csv`, '_blank')
}

function downloadTemplate() {
  const blob = new Blob(['﻿' + TEMPLATE_HEADER + '\r\n'], { type: 'text/csv;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = '占道许可导入模板.csv'
  link.click()
  URL.revokeObjectURL(link.href)
}

function triggerImport() {
  errorMessage.value = ''
  fileInput.value?.click()
}

async function onFilePicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  importing.value = true
  errorMessage.value = ''
  try {
    const content = await file.text()
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content }),
    })
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null
      throw new Error(payload?.detail || '表格导入失败，请检查文件格式')
    }
    importResult.value = (await response.json()) as ImportResult
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '表格导入失败'
  } finally {
    importing.value = false
  }
}

function openCreate() {
  errorMessage.value = '占道许可登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
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
  const query = currentQuery()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
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
.page-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.import-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-left: 3px solid var(--brand);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.import-summary {
  font-size: 13px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  align-items: center;
}
.fail-table {
  margin-top: 10px;
}
.ok-text {
  color: #067647;
}
</style>
