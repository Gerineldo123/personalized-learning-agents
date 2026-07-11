<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import api from '../../api'

const props = defineProps<{
  resourceId: number
  userId: string
}>()

const emit = defineEmits<{
  (e: 'open', id: number): void
  (e: 'filter-group', groupId: string): void
}>()

const loading = ref(false)
const data = ref<any>(null)

function typeLabel(type: string) {
  const map: Record<string, string> = {
    article: '文章',
    quiz: '题库',
    code: '代码',
    anime: '动画',
    mindmap: '思维导图',
    ppt: 'PPT',
    video: '视频',
    evaluation: '评估',
    unknown: '资源',
  }
  return map[type] || type || '资源'
}

function relationLabel(type: string) {
  const map: Record<string, string> = {
    generated_from_article: '由文章生成',
    generated_from_quiz: '由题库生成',
    same_package: '资源包成员',
    path_step: '路径步骤资源',
    path_check: '路径检查题',
    remediation: '补弱资源',
    ppt_session: 'AiPPT 分步生成',
    manual: '手动/助手保存',
    unknown: '独立资源',
  }
  return map[type] || '独立资源'
}

const lineage = computed(() => data.value?.lineage || {})
const hasGroup = computed(() => Boolean(lineage.value?.group_id))

async function loadLineage() {
  if (!props.resourceId || !props.userId) return
  loading.value = true
  try {
    const resp = await api.get(`/resources/${props.resourceId}/lineage`, {
      params: { user_id: props.userId },
    })
    data.value = resp.data
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

function openNode(node: any) {
  if (!node?.id || node.missing) return
  emit('open', Number(node.id))
}

watch(
  () => [props.resourceId, props.userId],
  () => loadLineage(),
  { immediate: true }
)
</script>

<template>
  <section class="lineage-panel">
    <div class="lineage-head">
      <div>
        <strong>资源族谱</strong>
        <p>查看当前资源的来源、派生资源和同组资源。</p>
      </div>
      <el-tag size="small" effect="plain">{{ relationLabel(lineage.relation_type) }}</el-tag>
    </div>

    <el-skeleton v-if="loading" :rows="3" animated />

    <div v-else-if="!data" class="lineage-empty">族谱信息加载失败。</div>

    <div v-else class="lineage-content">
      <div class="lineage-tree">
        <div class="lineage-column">
          <span class="column-title">上游来源</span>
          <button
            v-for="node in data.parent_resources"
            :key="`parent-${node.id}`"
            class="lineage-node"
            :class="{ missing: node.missing }"
            :disabled="node.missing"
            @click="openNode(node)"
          >
            <el-tag size="small">{{ typeLabel(node.resource_type) }}</el-tag>
            <span>{{ node.title }}</span>
          </button>
          <div v-if="!data.parent_resources?.length" class="lineage-placeholder">无上游来源</div>
        </div>

        <div class="lineage-column current">
          <span class="column-title">当前资源</span>
          <button class="lineage-node active" @click="openNode(data.current)">
            <el-tag size="small" type="success">{{ typeLabel(data.current?.resource_type) }}</el-tag>
            <span>{{ data.current?.title }}</span>
          </button>
        </div>

        <div class="lineage-column">
          <span class="column-title">下游派生</span>
          <button
            v-for="node in data.child_resources"
            :key="`child-${node.id}`"
            class="lineage-node"
            @click="openNode(node)"
          >
            <el-tag size="small" type="warning">{{ typeLabel(node.resource_type) }}</el-tag>
            <span>{{ node.title }}</span>
          </button>
          <div v-if="!data.child_resources?.length" class="lineage-placeholder">暂无派生资源</div>
        </div>
      </div>

      <div v-if="data.group_resources?.length" class="lineage-group">
        <div class="group-head">
          <strong>同组资源</strong>
          <el-button v-if="hasGroup" size="small" text @click="emit('filter-group', lineage.group_id)">
            只看这个资源族
          </el-button>
        </div>
        <div class="group-list">
          <button
            v-for="node in data.group_resources"
            :key="`group-${node.id}`"
            class="group-node"
            @click="openNode(node)"
          >
            <el-tag size="small" effect="plain">{{ typeLabel(node.resource_type) }}</el-tag>
            <span>{{ node.title }}</span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.lineage-panel {
  margin: 14px 0;
  padding: 16px;
  background: #fffaf4;
  border: 1px solid #f0ddc5;
  border-radius: 14px;
}

.lineage-head,
.group-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.lineage-head p {
  margin: 4px 0 0;
  color: #948a80;
  font-size: 13px;
}

.lineage-content {
  display: grid;
  gap: 14px;
  margin-top: 14px;
}

.lineage-tree {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.lineage-column {
  display: grid;
  gap: 8px;
  align-content: start;
}

.column-title {
  color: #a36b35;
  font-size: 13px;
  font-weight: 700;
}

.lineage-node,
.group-node {
  display: flex;
  width: 100%;
  gap: 8px;
  align-items: center;
  padding: 10px;
  color: #3a332e;
  text-align: left;
  background: #fff;
  border: 1px solid #ead8c4;
  border-radius: 10px;
  cursor: pointer;
}

.lineage-node:hover,
.group-node:hover {
  border-color: #e8c29c;
  box-shadow: 0 4px 12px rgba(58, 51, 46, 0.08);
}

.lineage-node.active {
  border-color: #67c23a;
  background: #f6fff4;
}

.lineage-node.missing {
  color: #999;
  cursor: not-allowed;
  background: #f7f7f7;
}

.lineage-placeholder,
.lineage-empty {
  padding: 10px;
  color: #948a80;
  background: #fff;
  border: 1px dashed #ead8c4;
  border-radius: 10px;
}

.lineage-group {
  padding-top: 12px;
  border-top: 1px solid #f0ddc5;
}

.group-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.lineage-node span:last-child,
.group-node span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .lineage-tree,
  .group-list {
    grid-template-columns: 1fr;
  }
}
</style>
