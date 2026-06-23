<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { medsafeApi } from '@/api/medsafe'
import type {
  AtcTreeNode,
  DrugCatalogStats,
  DrugInfoResponse,
  DrugSearchModelStatus,
  DrugSpecialFilter,
  HospitalDrug,
} from '@/types'

const route = useRoute()
const router = useRouter()

const stats = ref<DrugCatalogStats | null>(null)
const classification = ref<AtcTreeNode[]>([])
const specialFilters = ref<DrugSpecialFilter[]>([])
const searchModel = ref<DrugSearchModelStatus | null>(null)

const drugs = ref<HospitalDrug[]>([])
const total = ref(0)
const offset = ref(0)
const limit = 40

const selectedDrug = ref<HospitalDrug | null>(null)
const drugInfo = ref<DrugInfoResponse | null>(null)
const alternatives = ref<HospitalDrug[]>([])

const searchQuery = ref('')
const searchMode = ref<'keyword' | 'semantic'>('semantic')
const isSearchMode = ref(false)
const activeAtc = ref('')
const activeFilter = ref('')

const expandedNodes = ref<Set<string>>(new Set())
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const rebuildingIndex = ref(false)

const modelReady = computed(
  () => Boolean(searchModel.value?.model_present && searchModel.value?.index_built),
)

const semanticBlocked = computed(
  () => searchMode.value === 'semantic' && !modelReady.value,
)

const breadcrumb = computed(() => {
  if (isSearchMode.value && searchQuery.value) {
    return [{ label: `搜索「${searchQuery.value}」`, code: '' }]
  }
  if (activeFilter.value) {
    const f = specialFilters.value.find(x => x.id === activeFilter.value)
    return [{ label: f?.name_cn ?? activeFilter.value, code: '' }]
  }
  if (!activeAtc.value) return [{ label: '全部分类', code: '' }]
  const crumbs: { label: string; code: string }[] = []
  const code = activeAtc.value
  for (let len = 1; len <= code.length; len++) {
    if (len === 1 || len === 3 || len === 4 || len === 5) {
      crumbs.push({ label: findNodeLabel(code.slice(0, len), len), code: code.slice(0, len) })
    }
  }
  return crumbs.length ? crumbs : [{ label: activeAtc.value, code: activeAtc.value }]
})

function findNodeLabel(code: string, level: number): string {
  function walk(nodes: AtcTreeNode[]): string | null {
    for (const n of nodes) {
      if (n.code === code && n.level === level) return n.name_cn
      const child = walk(n.children)
      if (child) return child
    }
    return null
  }
  return walk(classification.value) ?? code
}

function toggleExpand(code: string) {
  const next = new Set(expandedNodes.value)
  if (next.has(code)) next.delete(code)
  else next.add(code)
  expandedNodes.value = next
}

async function loadMeta() {
  const [sRes, clsRes, modelRes] = await Promise.allSettled([
    medsafeApi.getDrugCatalogStats(),
    medsafeApi.getDrugClassification(4),
    medsafeApi.getDrugSearchModelStatus(),
  ])
  if (sRes.status === 'fulfilled') stats.value = sRes.value
  if (clsRes.status === 'fulfilled') {
    classification.value = clsRes.value.tree
    specialFilters.value = clsRes.value.special_filters
    for (const root of clsRes.value.tree) expandedNodes.value.add(root.code)
  }
  if (modelRes.status === 'fulfilled') {
    searchModel.value = modelRes.value
    if (!modelReady.value) searchMode.value = 'keyword'
  }
}

async function loadBrowse() {
  loading.value = true
  error.value = ''
  try {
    const res = await medsafeApi.browseDrugCatalog({
      atc_prefix: activeAtc.value,
      filter_id: activeFilter.value,
      limit,
      offset: offset.value,
    })
    drugs.value = res.results
    total.value = res.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function runSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    isSearchMode.value = false
    await loadBrowse()
    return
  }
  if (semanticBlocked.value) {
    searchMode.value = 'keyword'
  }
  loading.value = true
  error.value = ''
  isSearchMode.value = true
  activeAtc.value = ''
  activeFilter.value = ''
  offset.value = 0
  try {
    const res = await medsafeApi.searchDrugCatalog(q, 50, searchMode.value)
    drugs.value = res.results
    total.value = res.count
    router.replace({ query: { ...route.query, q, mode: res.mode } })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function selectCategory(code: string) {
  isSearchMode.value = false
  searchQuery.value = ''
  activeFilter.value = ''
  activeAtc.value = code
  offset.value = 0
  selectedDrug.value = null
  drugInfo.value = null
  router.replace({ query: { atc: code || undefined } })
  await loadBrowse()
}

async function selectFilter(id: string) {
  isSearchMode.value = false
  searchQuery.value = ''
  activeAtc.value = ''
  activeFilter.value = id
  offset.value = 0
  selectedDrug.value = null
  drugInfo.value = null
  router.replace({ query: { filter: id || undefined } })
  await loadBrowse()
}

async function selectDrug(drug: HospitalDrug) {
  selectedDrug.value = drug
  detailLoading.value = true
  drugInfo.value = null
  alternatives.value = []
  router.replace({ query: { ...route.query, id: drug.hospital_drug_id } })
  try {
    const [info, alts] = await Promise.all([
      medsafeApi.getDrugInfo(drug.generic_name_cn || drug.generic_name_en),
      medsafeApi.getDrugAlternatives(drug.hospital_drug_id),
    ])
    drugInfo.value = info
    alternatives.value = alts.alternatives
  } catch {
    drugInfo.value = null
  } finally {
    detailLoading.value = false
  }
}

async function rebuildIndex() {
  rebuildingIndex.value = true
  try {
    searchModel.value = await medsafeApi.rebuildDrugSearchIndex()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    rebuildingIndex.value = false
  }
}

function prevPage() {
  offset.value = Math.max(0, offset.value - limit)
  loadBrowse()
}

function nextPage() {
  if (offset.value + limit < total.value) {
    offset.value += limit
    loadBrowse()
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (!searchQuery.value.trim()) {
      if (isSearchMode.value) {
        isSearchMode.value = false
        loadBrowse()
      }
      return
    }
    if (semanticBlocked.value) return
    runSearch()
  }, 350)
})

onMounted(async () => {
  try {
    await loadMeta()
    const q = route.query.q as string | undefined
    const atc = route.query.atc as string | undefined
    const filter = route.query.filter as string | undefined
    const id = route.query.id as string | undefined
    if (q) {
      searchQuery.value = q
      if (route.query.mode === 'keyword') searchMode.value = 'keyword'
    if (semanticBlocked.value) searchMode.value = 'keyword'
    if (!semanticBlocked.value || searchMode.value === 'keyword') await runSearch()
    } else if (filter) {
      activeFilter.value = filter
      await loadBrowse()
    } else if (atc) {
      activeAtc.value = atc
      await loadBrowse()
    } else {
      await loadBrowse()
    }
    if (id) {
      const drug = drugs.value.find(d => d.hospital_drug_id === id)
      if (drug) await selectDrug(drug)
      else {
        try {
          const d = await medsafeApi.getDrugById(id)
          await selectDrug(d)
        } catch { /* ignore */ }
      }
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})
</script>

<template>
  <div class="drug-db">
    <header class="page-head">
      <div>
        <h1>药品库</h1>
        <p class="sub">ATC 分级浏览 · 语义检索 · 知识图谱安全信息</p>
      </div>
      <div v-if="stats" class="stats-row">
        <div class="stat-pill"><span>品种</span><strong>{{ stats.total_drugs }}</strong></div>
        <div class="stat-pill"><span>在册</span><strong>{{ stats.in_formulary }}</strong></div>
        <div class="stat-pill"><span>有库存</span><strong>{{ stats.in_stock }}</strong></div>
      </div>
    </header>

    <div v-if="searchModel && !modelReady" class="card model-banner warn">
      <div>
        <strong>语义检索未就绪</strong>
        <p>默认使用语义搜索；模型或索引缺失时将返回 503，请下载模型并重建索引，或切换为「关键词」模式。</p>
        <code>{{ searchModel.download_command }}</code>
        <p class="hint">下载后点击「重建索引」，或切换搜索模式为「关键词」。</p>
      </div>
      <button
        class="btn-secondary"
        type="button"
        :disabled="!searchModel.model_present || rebuildingIndex"
        @click="rebuildIndex"
      >
        {{ rebuildingIndex ? '重建中…' : '重建索引' }}
      </button>
    </div>
    <div v-else-if="searchModel" class="card model-banner ok">
      <div>
        <strong>语义检索已就绪</strong>
        <span class="muted">
          {{ searchModel.model ?? '—' }} · 索引 {{ searchModel.indexed_drugs }} 条
        </span>
      </div>
      <button
        class="btn-secondary"
        type="button"
        :disabled="rebuildingIndex"
        @click="rebuildIndex"
      >
        {{ rebuildingIndex ? '重建中…' : '重建索引' }}
      </button>
    </div>

    <div class="search-bar card">
      <input
        v-model="searchQuery"
        class="input search-input"
        type="search"
        placeholder="搜索通用名、商品名、英文 INN、院内码…"
        autocomplete="off"
      />
      <select v-model="searchMode" class="select mode-select">
        <option value="semantic">语义</option>
        <option value="keyword">关键词</option>
      </select>
      <button class="btn-primary" type="button" @click="runSearch">
        搜索
      </button>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="workspace">
      <aside class="tree-panel card">
        <h3>分类浏览</h3>
        <ul class="facet-list">
          <li
            v-for="f in specialFilters"
            :key="f.id"
            class="facet-item"
            :class="{ active: activeFilter === f.id && !isSearchMode }"
            @click="selectFilter(f.id)"
          >
            {{ f.name_cn }}
          </li>
        </ul>
        <hr class="divider" />
        <ul class="tree">
          <li>
            <button
              type="button"
              class="tree-node root"
              :class="{ active: !activeAtc && !activeFilter && !isSearchMode }"
              @click="selectCategory('')"
            >
              全部分类
            </button>
          </li>
          <template v-for="node in classification" :key="node.code">
            <li>
              <div class="tree-row">
                <button
                  v-if="node.children.length"
                  type="button"
                  class="expand-btn"
                  @click.stop="toggleExpand(node.code)"
                >
                  {{ expandedNodes.has(node.code) ? '▼' : '▶' }}
                </button>
                <span v-else class="expand-spacer" />
                <button
                  type="button"
                  class="tree-node"
                  :class="{ active: activeAtc === node.code && !isSearchMode }"
                  @click="selectCategory(node.code)"
                >
                  <span class="code">{{ node.code }}</span>
                  {{ node.name_cn }}
                  <span class="count">{{ node.drug_count }}</span>
                </button>
              </div>
              <ul v-if="expandedNodes.has(node.code)" class="tree nested">
                <template v-for="child in node.children" :key="child.code">
                  <li>
                    <div class="tree-row">
                      <button
                        v-if="child.children.length"
                        type="button"
                        class="expand-btn"
                        @click.stop="toggleExpand(child.code)"
                      >
                        {{ expandedNodes.has(child.code) ? '▼' : '▶' }}
                      </button>
                      <span v-else class="expand-spacer" />
                      <button
                        type="button"
                        class="tree-node"
                        :class="{ active: activeAtc === child.code && !isSearchMode }"
                        @click="selectCategory(child.code)"
                      >
                        <span class="code">{{ child.code }}</span>
                        {{ child.name_cn }}
                        <span class="count">{{ child.drug_count }}</span>
                      </button>
                    </div>
                    <ul v-if="expandedNodes.has(child.code)" class="tree nested">
                      <li v-for="gc in child.children" :key="gc.code">
                        <button
                          type="button"
                          class="tree-node leaf"
                          :class="{ active: activeAtc === gc.code && !isSearchMode }"
                          @click="selectCategory(gc.code)"
                        >
                          <span class="code">{{ gc.code }}</span>
                          {{ gc.name_cn }}
                          <span class="count">{{ gc.drug_count }}</span>
                        </button>
                      </li>
                    </ul>
                  </li>
                </template>
              </ul>
            </li>
          </template>
        </ul>
      </aside>

      <section class="list-panel card">
        <nav class="breadcrumb">
          <template v-for="(cr, i) in breadcrumb" :key="i">
            <button
              v-if="cr.code"
              type="button"
              class="crumb"
              @click="selectCategory(cr.code)"
            >
              {{ cr.label }}
            </button>
            <span v-else>{{ cr.label }}</span>
            <span v-if="i < breadcrumb.length - 1" class="sep">›</span>
          </template>
          <span class="total-hint">共 {{ total }} 条</span>
        </nav>

        <div v-if="loading" class="loading-row"><span class="spinner" /> 加载中…</div>

        <table v-else-if="drugs.length" class="drug-table">
          <thead>
            <tr>
              <th>药品</th>
              <th>规格</th>
              <th>ATC</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="d in drugs"
              :key="d.hospital_drug_id"
              :class="{ selected: selectedDrug?.hospital_drug_id === d.hospital_drug_id }"
              @click="selectDrug(d)"
            >
              <td>
                <strong>{{ d.trade_name_cn || d.generic_name_cn }}</strong>
                <small>{{ d.generic_name_cn }} / {{ d.generic_name_en }}</small>
              </td>
              <td>{{ d.strength }} {{ d.dosage_form }}</td>
              <td><code>{{ d.atc_code }}</code></td>
              <td class="badges">
                <span v-if="d.high_alert" class="badge badge-high">高警示</span>
                <span v-if="!d.in_stock" class="badge badge-medium">缺货</span>
                <span v-if="d.in_formulary" class="badge badge-none">在册</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty">暂无匹配药品</p>

        <div v-if="!isSearchMode && total > limit" class="pager">
          <button class="btn-secondary" type="button" :disabled="offset === 0" @click="prevPage">上一页</button>
          <span>{{ offset + 1 }}–{{ Math.min(offset + limit, total) }} / {{ total }}</span>
          <button class="btn-secondary" type="button" :disabled="offset + limit >= total" @click="nextPage">下一页</button>
        </div>
      </section>

      <aside class="detail-panel card">
        <template v-if="selectedDrug">
          <h3>{{ selectedDrug.display_name || selectedDrug.trade_name_cn }}</h3>
          <dl class="detail-dl">
            <dt>院内码</dt><dd><code>{{ selectedDrug.hospital_drug_id }}</code></dd>
            <dt>通用名</dt><dd>{{ selectedDrug.generic_name_cn }} ({{ selectedDrug.generic_name_en }})</dd>
            <dt>商品名</dt><dd>{{ selectedDrug.trade_name_cn || '—' }}</dd>
            <dt>规格 / 剂型</dt><dd>{{ selectedDrug.strength }} · {{ selectedDrug.dosage_form }}</dd>
            <dt>给药途径</dt><dd>{{ selectedDrug.route || '—' }}</dd>
            <dt>ATC</dt><dd><code>{{ selectedDrug.atc_code }}</code></dd>
            <dt>RxNorm</dt><dd>{{ selectedDrug.rxnorm_rxcui || '—' }}</dd>
            <dt>生产企业</dt><dd>{{ selectedDrug.manufacturer || '—' }}</dd>
            <dt v-if="selectedDrug.restricted_dept">科室限制</dt>
            <dd v-if="selectedDrug.restricted_dept">{{ selectedDrug.restricted_dept }}</dd>
            <dt v-if="selectedDrug.antibiotic_level && selectedDrug.antibiotic_level !== '0'">抗菌级别</dt>
            <dd v-if="selectedDrug.antibiotic_level && selectedDrug.antibiotic_level !== '0'">{{ selectedDrug.antibiotic_level }}</dd>
          </dl>

          <div v-if="detailLoading" class="loading-row"><span class="spinner" /> 加载知识图谱…</div>

          <template v-else-if="drugInfo">
            <div v-if="drugInfo.category" class="kg-section">
              <h4>药理分类</h4>
              <p>{{ drugInfo.category }}</p>
              <p v-if="drugInfo.description" class="desc">{{ drugInfo.description }}</p>
            </div>
            <div v-if="drugInfo.interactions?.length" class="kg-section">
              <h4>已知相互作用</h4>
              <ul>
                <li v-for="(inter, i) in drugInfo.interactions" :key="i">
                  <strong>{{ inter.drug }}</strong>
                  <span class="badge badge-medium">{{ inter.severity }}</span>
                  <p v-if="inter.effect">{{ inter.effect }}</p>
                </li>
              </ul>
            </div>
          </template>

          <div v-if="alternatives.length" class="kg-section">
            <h4>可替代品种</h4>
            <ul class="alt-list">
              <li v-for="a in alternatives" :key="a.hospital_drug_id">
                <button type="button" class="link-btn" @click="selectDrug(a)">
                  {{ a.display_name || a.trade_name_cn }}
                </button>
              </li>
            </ul>
          </div>
        </template>
        <p v-else class="empty detail-empty">选择左侧列表中的药品查看详情与安全信息</p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}
h1 { margin-bottom: 0.25rem; }
.sub { color: var(--text-muted); font-size: 0.92rem; }
.stats-row { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.stat-pill {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.4rem 0.75rem;
  text-align: center;
  min-width: 72px;
}
.stat-pill span { display: block; font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; }
.stat-pill strong { font-size: 1.15rem; color: var(--primary); }

.model-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
  padding: 0.85rem 1rem;
}
.model-banner.warn { background: #fff8e1; border-color: #ffe082; }
.model-banner.ok { background: #e8f5e9; border-color: #a5d6a7; }
.model-banner code { display: block; font-size: 0.82rem; margin-top: 0.35rem; color: var(--text-muted); }
.model-banner .hint { font-size: 0.85rem; color: var(--text-muted); margin-top: 0.35rem; }
.muted { font-size: 0.85rem; color: var(--text-muted); margin-left: 0.5rem; }

.search-bar {
  display: flex;
  gap: 0.65rem;
  margin-bottom: 1rem;
  align-items: center;
}
.search-input { flex: 1; }
.mode-select { width: 110px; flex-shrink: 0; }

.workspace {
  display: grid;
  grid-template-columns: 240px 1fr 300px;
  gap: 1rem;
  align-items: start;
}
@media (max-width: 1100px) {
  .workspace { grid-template-columns: 1fr; }
  .detail-panel { order: 3; }
}

.tree-panel h3 { font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.65rem; }
.facet-list { list-style: none; margin-bottom: 0.5rem; }
.facet-item {
  padding: 0.4rem 0.5rem;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 0.88rem;
}
.facet-item:hover { background: var(--surface-2); }
.facet-item.active { background: var(--primary-light); color: var(--primary-dark); font-weight: 600; }
.divider { border: none; border-top: 1px solid var(--border); margin: 0.65rem 0; }

.tree { list-style: none; }
.tree.nested { margin-left: 0.75rem; }
.tree-row { display: flex; align-items: center; gap: 0.15rem; }
.expand-btn, .expand-spacer {
  width: 1.25rem;
  flex-shrink: 0;
  background: none;
  border: none;
  padding: 0;
  font-size: 0.65rem;
  color: var(--text-muted);
  cursor: pointer;
}
.tree-node {
  flex: 1;
  text-align: left;
  background: none;
  border: none;
  padding: 0.35rem 0.4rem;
  border-radius: var(--radius);
  font-size: 0.82rem;
  color: var(--text);
  cursor: pointer;
  font-weight: 400;
}
.tree-node:hover { background: var(--surface-2); }
.tree-node.active { background: var(--primary-light); font-weight: 600; }
.tree-node .code { font-family: var(--mono); font-size: 0.75rem; color: var(--text-muted); margin-right: 0.25rem; }
.tree-node .count { float: right; font-size: 0.72rem; color: var(--text-muted); }

.breadcrumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  margin-bottom: 0.85rem;
  font-size: 0.88rem;
}
.crumb { background: none; border: none; color: var(--primary); padding: 0; cursor: pointer; font-size: inherit; }
.sep { color: var(--text-muted); }
.total-hint { margin-left: auto; color: var(--text-muted); font-size: 0.82rem; }

.drug-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
.drug-table th {
  text-align: left;
  padding: 0.5rem 0.4rem;
  border-bottom: 2px solid var(--border);
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
}
.drug-table td { padding: 0.55rem 0.4rem; border-bottom: 1px solid var(--surface-2); vertical-align: top; }
.drug-table tr { cursor: pointer; }
.drug-table tr:hover td { background: var(--surface-2); }
.drug-table tr.selected td { background: var(--primary-light); }
.drug-table small { display: block; color: var(--text-muted); font-size: 0.78rem; }
.badges { white-space: nowrap; }
.badges .badge { margin-right: 0.25rem; }

.detail-panel h3 { margin-bottom: 0.85rem; font-size: 1.05rem; }
.detail-dl { display: grid; grid-template-columns: 88px 1fr; gap: 0.35rem 0.5rem; font-size: 0.88rem; margin-bottom: 1rem; }
.detail-dl dt { color: var(--text-muted); font-weight: 600; }
.kg-section { margin-top: 1rem; padding-top: 0.85rem; border-top: 1px solid var(--border); }
.kg-section h4 { font-size: 0.82rem; color: var(--primary); margin-bottom: 0.5rem; text-transform: uppercase; }
.kg-section ul { list-style: none; font-size: 0.85rem; }
.kg-section li { margin-bottom: 0.5rem; }
.desc { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.35rem; }
.alt-list .link-btn { background: none; border: none; color: var(--primary); padding: 0; cursor: pointer; font-size: 0.88rem; }
.empty { color: var(--text-muted); padding: 2rem 0; text-align: center; }
.detail-empty { padding: 3rem 1rem; }
.loading-row { display: flex; align-items: center; gap: 0.5rem; color: var(--text-muted); padding: 1rem 0; }
.pager { display: flex; align-items: center; justify-content: center; gap: 1rem; margin-top: 1rem; font-size: 0.88rem; }
.err { color: var(--danger); margin-bottom: 0.75rem; }
</style>
