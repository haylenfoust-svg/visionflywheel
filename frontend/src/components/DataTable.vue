<script setup lang="ts" generic="T extends Record<string, any>">
import { computed, ref } from 'vue'

/**
 * DataTable — generic table with sorting, filtering, pagination, density,
 * column visibility and consistent empty/loading states.
 *
 * Column spec:
 *   { key, label, sortable?, width?, align?, slot?, format?(row): string }
 */
export interface Column<T = Record<string, any>> {
  key: string
  label: string
  sortable?: boolean
  width?: number | string
  align?: 'left' | 'center' | 'right'
  slot?: string
  format?: (row: T) => string
}

const props = withDefaults(
  defineProps<{
    rows: T[]
    columns: Column<T>[]
    rowKey?: (row: T, index?: number) => string | number
    loading?: boolean
    emptyTitle?: string
    emptyDescription?: string
    emptyIcon?: string
    pageSizeOptions?: number[]
    initialPageSize?: number
    initialSortKey?: string
    initialSortOrder?: 'asc' | 'desc'
    showToolbar?: boolean
    showPagination?: boolean
  }>(),
  {
    rowKey: (row: any, i?: number) => (row?.id ?? i ?? 0),
    loading: false,
    emptyTitle: '暂无数据',
    emptyDescription: '',
    emptyIcon: '✨',
    pageSizeOptions: () => [10, 20, 50, 100],
    initialPageSize: 10,
    initialSortKey: '',
    initialSortOrder: 'asc',
    showToolbar: true,
    showPagination: true,
  },
)

const emit = defineEmits<{
  (e: 'row-click', row: T): void
  (e: 'update:page', page: number): void
  (e: 'update:pageSize', size: number): void
}>()

const search = ref('')
const sortKey = ref<string>(props.initialSortKey)
const sortOrder = ref<'asc' | 'desc'>(props.initialSortOrder)
const currentPage = ref(1)
const pageSize = ref(props.initialPageSize)
const density = ref<'compact' | 'default' | 'comfortable'>('default')
const hiddenCols = ref<Set<string>>(new Set())

const filteredRows = computed(() => {
  if (!search.value.trim()) return props.rows
  const q = search.value.toLowerCase()
  return props.rows.filter((row) =>
    props.columns.some((c) => {
      const val = c.format ? c.format(row) : row[c.key]
      return String(val ?? '').toLowerCase().includes(q)
    }),
  )
})

const sortedRows = computed(() => {
  if (!sortKey.value) return filteredRows.value
  const key = sortKey.value
  const dir = sortOrder.value === 'asc' ? 1 : -1
  return [...filteredRows.value].sort((a, b) => {
    const va = a[key]
    const vb = b[key]
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
    return String(va).localeCompare(String(vb), 'zh') * dir
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(sortedRows.value.length / pageSize.value)))

const pageRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return sortedRows.value.slice(start, start + pageSize.value)
})

const visibleColumns = computed(() =>
  props.columns.filter((c) => !hiddenCols.value.has(c.key)),
)

function toggleSort(key: string) {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = 'asc'
  }
  currentPage.value = 1
}

function toggleCol(key: string) {
  if (hiddenCols.value.has(key)) {
    hiddenCols.value.delete(key)
  } else {
    hiddenCols.value.add(key)
  }
  // force reactivity
  hiddenCols.value = new Set(hiddenCols.value)
}

function changePage(page: number) {
  currentPage.value = Math.min(Math.max(1, page), totalPages.value)
  emit('update:page', currentPage.value)
}

function changeSize(size: number) {
  pageSize.value = size
  currentPage.value = 1
  emit('update:pageSize', size)
}

function cellText(row: T, col: Column<T>): string {
  if (col.format) return col.format(row)
  return String(row[col.key] ?? '')
}
</script>

<template>
  <div class="data-table">
    <!-- toolbar -->
    <div v-if="showToolbar" class="dt-toolbar">
      <div class="dt-toolbar__left">
        <div class="dt-search">
          <span class="dt-search__icon">🔍</span>
          <input
            v-model="search"
            type="search"
            class="dt-search__input"
            placeholder="搜索…"
            @input="currentPage = 1"
          />
        </div>
      </div>
      <div class="dt-toolbar__right">
        <div class="dt-density">
          <button
            v-for="d in ['compact', 'default', 'comfortable'] as const"
            :key="d"
            class="dt-density__btn"
            :class="{ 'is-active': density === d }"
            :title="d === 'compact' ? '紧凑' : d === 'default' ? '默认' : '宽松'"
            @click="density = d"
          >
            {{ d === 'compact' ? '▯' : d === 'default' ? '▮' : '▮▮' }}
          </button>
        </div>
        <el-dropdown trigger="click">
          <button class="dt-cols">列 ⚙</button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="c in columns"
                :key="c.key"
                @click="toggleCol(c.key)"
              >
                <span :class="{ 'col-off': hiddenCols.has(c.key) }">
                  {{ hiddenCols.has(c.key) ? '○' : '●' }} {{ c.label }}
                </span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- table -->
    <div class="dt-scroll">
      <table class="dt" :class="`density-${density}`">
        <thead>
          <tr>
            <th
              v-for="col in visibleColumns"
              :key="col.key"
              :style="{ width: col.width, textAlign: col.align ?? 'left' }"
              class="dt-th"
              :class="{ 'is-sortable': col.sortable, 'is-sorted': sortKey === col.key }"
              @click="col.sortable && toggleSort(col.key)"
            >
              <span class="dt-th__inner">
                {{ col.label }}
                <span v-if="col.sortable" class="dt-th__arrow">
                  {{ sortKey === col.key ? (sortOrder === 'asc' ? '↑' : '↓') : '↕' }}
                </span>
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-if="loading">
            <tr v-for="i in 5" :key="i">
              <td v-for="col in visibleColumns" :key="col.key" class="dt-td">
                <div class="dt-skeleton" />
              </td>
            </tr>
          </template>
          <template v-else-if="pageRows.length">
            <tr
              v-for="(row, i) in pageRows"
              :key="rowKey(row, i)"
              class="dt-row"
              @click="emit('row-click', row)"
            >
              <td
                v-for="col in visibleColumns"
                :key="col.key"
                :style="{ textAlign: col.align ?? 'left' }"
                class="dt-td"
              >
                <slot :name="col.slot" :row="row" :value="row[col.key]">
                  {{ cellText(row, col) }}
                </slot>
              </td>
            </tr>
          </template>
          <template v-else>
            <tr>
              <td :colspan="visibleColumns.length" class="dt-empty">
                <div class="dt-empty__inner">
                  <div class="dt-empty__icon">{{ emptyIcon }}</div>
                  <div class="dt-empty__title">{{ emptyTitle }}</div>
                  <div v-if="emptyDescription" class="dt-empty__desc">{{ emptyDescription }}</div>
                  <slot name="empty-action" />
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- pagination -->
    <div v-if="showPagination && !loading" class="dt-pagination">
      <div class="dt-pagination__info">
        共 <span class="num">{{ sortedRows.length }}</span> 条
        <template v-if="sortedRows.length">，第 {{ currentPage }} / {{ totalPages }} 页</template>
      </div>
      <div class="dt-pagination__controls">
        <el-select
          :model-value="pageSize"
          size="small"
          class="dt-page-size"
          @update:model-value="changeSize"
        >
          <el-option v-for="s in pageSizeOptions" :key="s" :value="s" :label="`${s} 条/页`" />
        </el-select>
        <div class="dt-pages">
          <button class="dt-page-btn" :disabled="currentPage <= 1" @click="changePage(currentPage - 1)">
            ‹
          </button>
          <button
            v-for="p in Math.min(5, totalPages)"
            :key="p"
            class="dt-page-btn"
            :class="{ 'is-active': p === currentPage }"
            @click="changePage(p)"
          >
            {{ p }}
          </button>
          <button class="dt-page-btn" :disabled="currentPage >= totalPages" @click="changePage(currentPage + 1)">
            ›
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.data-table {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

/* toolbar */
.dt-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}
.dt-search {
  position: relative;
  display: flex;
  align-items: center;
}
.dt-search__icon {
  position: absolute;
  left: var(--sp-2);
  font-size: 12px;
  color: var(--text-tertiary);
  pointer-events: none;
}
.dt-search__input {
  padding: 6px var(--sp-3) 6px 28px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
  font: inherit;
  font-size: var(--fs-sm);
  color: var(--text-primary);
  width: 220px;
  transition: all var(--t-fast) var(--ease-standard);
}
.dt-search__input:focus {
  outline: none;
  border-color: var(--border-focus);
  box-shadow: var(--shadow-focus);
}
.dt-toolbar__right {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.dt-density {
  display: flex;
  border: 1px solid var(--border-default);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.dt-density__btn {
  padding: 4px 8px;
  background: var(--bg-surface);
  border: none;
  cursor: pointer;
  font-size: 10px;
  color: var(--text-tertiary);
  transition: all var(--t-fast) var(--ease-standard);
}
.dt-density__btn + .dt-density__btn {
  border-left: 1px solid var(--border-default);
}
.dt-density__btn.is-active {
  background: var(--c-primary-50);
  color: var(--c-primary-700);
}
.dt-cols {
  padding: 4px 10px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-sm);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--t-fast) var(--ease-standard);
}
.dt-cols:hover {
  border-color: var(--border-accent);
}
.col-off {
  opacity: 0.5;
}

/* table */
.dt-scroll {
  overflow-x: auto;
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
  background: var(--bg-surface);
}
.dt {
  width: 100%;
  border-collapse: collapse;
}
.dt-th {
  padding: var(--sp-3);
  background: var(--bg-subtle);
  border-bottom: 1px solid var(--border-default);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--text-secondary);
  white-space: nowrap;
  user-select: none;
}
.dt-th.is-sortable {
  cursor: pointer;
}
.dt-th.is-sortable:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.dt-th.is-sorted {
  color: var(--text-accent);
}
.dt-th__inner {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.dt-th__arrow {
  font-size: 10px;
  opacity: 0.7;
}

.dt-td {
  padding: var(--sp-3);
  border-bottom: 1px solid var(--border-default);
  font-size: var(--fs-md);
  color: var(--text-primary);
  vertical-align: middle;
}
.density-compact .dt-th,
.density-compact .dt-td {
  padding: 6px var(--sp-2);
  font-size: var(--fs-sm);
}
.density-comfortable .dt-th,
.density-comfortable .dt-td {
  padding: var(--sp-4);
}

.dt-row {
  cursor: pointer;
  transition: background var(--t-fast) var(--ease-standard);
}
.dt-row:hover {
  background: var(--bg-hover);
}
.dt-row:active {
  background: var(--bg-active);
}

/* skeleton */
.dt-skeleton {
  height: 16px;
  background: linear-gradient(90deg, var(--c-neutral-200) 25%, var(--c-neutral-100) 50%, var(--c-neutral-200) 75%);
  background-size: 200% 100%;
  border-radius: var(--r-xs);
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer {
  from { background-position: -200% 0; }
  to { background-position: 200% 0; }
}

/* empty */
.dt-empty {
  padding: 0;
}
.dt-empty__inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--sp-10) var(--sp-4);
  animation: fade-in var(--t-base) var(--ease-decelerate);
}
.dt-empty__icon {
  font-size: 32px;
  padding: var(--sp-3);
  background: var(--bg-subtle);
  border-radius: var(--r-full);
  margin-bottom: var(--sp-3);
}
.dt-empty__title {
  font-size: var(--fs-md);
  font-weight: var(--fw-semibold);
}
.dt-empty__desc {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-top: 4px;
  text-align: center;
}

/* pagination */
.dt-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  flex-wrap: wrap;
}
.dt-pagination__info {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.dt-pagination__controls {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.dt-page-size {
  width: 110px;
}
.dt-pages {
  display: flex;
  gap: 2px;
}
.dt-page-btn {
  min-width: 28px;
  height: 28px;
  padding: 0 6px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-sm);
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--t-fast) var(--ease-standard);
}
.dt-page-btn:hover:not(:disabled) {
  border-color: var(--border-accent);
  color: var(--text-accent);
}
.dt-page-btn.is-active {
  background: var(--c-primary-600);
  color: white;
  border-color: var(--c-primary-600);
}
.dt-page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
