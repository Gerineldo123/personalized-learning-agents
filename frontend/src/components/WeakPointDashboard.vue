<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { weakPointApi } from '../api/weakPoint'
import { ElMessage } from 'element-plus'

const props = defineProps<{ userId: string; visible: boolean }>()
const emit = defineEmits(['update:visible'])

const activeTab = ref('active')
const allItems = ref<any[]>([])

const statusMap: Record<string, string> = {
  active: '待攻克',
  reviewing: '复习中',
  mastered: '已掌握',
  archived: '已归档',
}

const filteredList = computed(() =>
  allItems.value.filter((w) => w.status === activeTab.value)
)

function progressColor(row: any) {
  if (row.mastery_score >= 0.75) return '#67c23a'
  if (row.mastery_score >= 0.5) return '#e6a23c'
  return '#f56c6c'
}

async function load() {
  if (!props.userId) return
  const r = await weakPointApi.listAll(props.userId)
  allItems.value = r.data
}

async function setStatus(row: any, status: string) {
  await weakPointApi.updateStatus(row.id, status, props.userId)
  await load()
  ElMessage.success('已更新')
}

watch(() => props.visible, (v) => { if (v) load() })
</script>

<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="emit('update:visible', $event)"
    title="薄弱知识点管理"
    width="760px"
  >
    <el-tabs v-model="activeTab">
      <el-tab-pane v-for="(label, key) in statusMap" :key="key" :label="label" :name="key" />
    </el-tabs>

    <el-table :data="filteredList" stripe style="margin-top: 8px">
      <el-table-column prop="name" label="知识点" min-width="120" />
      <el-table-column label="掌握度" width="160">
        <template #default="{ row }">
          <el-progress
            :percentage="Math.round(row.mastery_score * 100)"
            :color="progressColor(row)"
            :stroke-width="8"
          />
        </template>
      </el-table-column>
      <el-table-column prop="quiz_count" label="做题次数" width="90" align="center" />
      <el-table-column label="下次复习" width="110">
        <template #default="{ row }">
          {{ row.next_review_at ? row.next_review_at.slice(0, 10) : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <template v-if="row.status !== 'mastered' && row.status !== 'archived'">
            <el-button link size="small" @click="setStatus(row, 'mastered')">标为已掌握</el-button>
          </template>
          <template v-if="row.status !== 'archived'">
            <el-button link size="small" type="danger" @click="setStatus(row, 'archived')">归档</el-button>
          </template>
          <template v-if="row.status === 'archived' || row.status === 'mastered'">
            <el-button link size="small" @click="setStatus(row, 'active')">重新激活</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="filteredList.length === 0" description="暂无数据" style="padding: 20px 0" />
  </el-dialog>
</template>
