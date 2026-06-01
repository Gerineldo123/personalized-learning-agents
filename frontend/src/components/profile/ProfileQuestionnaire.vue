<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import api from '../../api'
import { useUserStore } from '../../stores/user'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()

const emit = defineEmits<{
  done: [profile: any]
  cancel: []
}>()

const step = ref(0)
const loading = ref(false)
const config = ref<any>({})
const seedCourses = ref<string[]>([])

const educationLevel = ref('')
const educationYear = ref('')
const discipline = ref('')
const major = ref('')
const isCustomMajor = ref(false)
const customMajorInput = ref('')
const majorSearch = ref('')
const majorTree = ref<any[]>([])
const searchResults = ref<string[]>([])
const crossDisciplines = ref<string[]>([])

interface CourseEntry {
  name: string
  knowledge_points: string
  difficulty_types: string[]
  impacts: string[]
  goal: string
}
const courses = ref<CourseEntry[]>([])
const currentCourse = ref<CourseEntry>({
  name: '',
  knowledge_points: '',
  difficulty_types: [],
  impacts: [],
  goal: '',
})
const showCourseEdit = ref(false)
const courseSearch = ref('')

const years = computed(() => config.value.years_by_level?.[educationLevel.value] || [])
const disciplines = computed(() => config.value.disciplines || [])
const otherDisciplines = computed(() => disciplines.value.filter((d: string) => d !== discipline.value))
const courseGoals = computed(() => config.value.course_goals || [])
const difficultyTypes = computed(() => config.value.difficulty_types || [])
const impacts = computed(() => config.value.impacts || [])

const allMajorsInTree = computed(() => {
  const result: string[] = []
  for (const cat of majorTree.value) {
    result.push(...(cat.majors || []))
  }
  return result
})

onMounted(async () => {
  try {
    const r = await api.get('/profile/config')
    config.value = r.data
  } catch {}
})

watch(discipline, async (newDisc) => {
  if (newDisc) {
    await fetchMajorTree()
  } else {
    majorTree.value = []
  }
  major.value = ''
  isCustomMajor.value = false
  customMajorInput.value = ''
  majorSearch.value = ''
  searchResults.value = []
})

async function fetchMajorTree() {
  try {
    const r = await api.get('/profile/majors', { params: { discipline: discipline.value } })
    const tree = r.data.tree?.[discipline.value] || []
    majorTree.value = tree
  } catch { majorTree.value = [] }
}

async function doMajorSearch() {
  const kw = majorSearch.value.trim()
  if (!kw) { searchResults.value = []; return }
  try {
    const r = await api.get('/profile/majors', {
      params: { discipline: discipline.value, keyword: kw }
    })
    searchResults.value = r.data.majors || []
  } catch { searchResults.value = [] }
}

function selectMajor(name: string) {
  major.value = name
  isCustomMajor.value = false
  customMajorInput.value = ''
  majorSearch.value = ''
  searchResults.value = []
}

function confirmCustomMajor() {
  const val = customMajorInput.value.trim()
  if (!val) { ElMessage.warning('请输入专业名称'); return }
  major.value = val
  isCustomMajor.value = true
  majorSearch.value = ''
  searchResults.value = []
}

function clearMajor() {
  major.value = ''
  isCustomMajor.value = false
  customMajorInput.value = ''
}

async function loadSeedCourses() {
  if (!discipline.value) return
  try {
    const r = await api.get('/profile/seed_courses', {
      params: { discipline: discipline.value, level: educationYear.value, major: major.value }
    })
    seedCourses.value = r.data.courses || []
  } catch { seedCourses.value = [] }
}

function nextStep() {
  if (step.value === 0 && (!educationLevel.value || !educationYear.value)) {
    ElMessage.warning('请完成学历背景选择')
    return
  }
  if (step.value === 1 && !discipline.value) {
    ElMessage.warning('请选择学科门类')
    return
  }
  if (step.value === 2 && !major.value) {
    ElMessage.warning('请选择或输入你的专业')
    return
  }
  step.value++
  if (step.value === 3) loadSeedCourses()
  if (step.value === 4 && courses.value.length === 0) {
    ElMessage.warning('请至少添加一个薄弱课程')
    step.value = 3
  }
}

function prevStep() {
  step.value = Math.max(0, step.value - 1)
}

function toggleCourse(name: string) {
  const exists = courses.value.find(c => c.name === name)
  if (exists) {
    courses.value = courses.value.filter(c => c.name !== name)
  } else {
    currentCourse.value = { name, knowledge_points: '', difficulty_types: [], impacts: [], goal: '' }
    showCourseEdit.value = true
  }
}

function searchCourse() {
  const name = courseSearch.value.trim()
  if (!name) return
  toggleCourse(name)
  courseSearch.value = ''
}

function saveCourse() {
  const c = currentCourse.value
  if (!c.name.trim()) { ElMessage.warning('请输入课程名称'); return }
  if (!c.knowledge_points.trim()) { ElMessage.warning('请描述薄弱知识点'); return }
  if (c.difficulty_types.length === 0) { ElMessage.warning('请选择困难类型'); return }
  if (!c.goal) { ElMessage.warning('请选择学习目标'); return }

  const idx = courses.value.findIndex((x: CourseEntry) => x.name === c.name)
  if (idx >= 0) courses.value[idx] = { ...c }
  else courses.value.push({ ...c })

  showCourseEdit.value = false
}

function removeCourse(name: string) {
  courses.value = courses.value.filter(c => c.name !== name)
}

function isCourseAdded(name: string) {
  return courses.value.some(c => c.name === name)
}

async function submitQuestionnaire() {
  loading.value = true
  try {
    const r = await api.post('/profile/generate', {
      education_level: educationLevel.value,
      education_year: educationYear.value,
      discipline: discipline.value,
      major: major.value,
      cross_disciplines: crossDisciplines.value,
      courses: courses.value,
    }, { params: { user_id: userStore.userId }, timeout: 120000 })
    emit('done', r.data.profile)
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err?.message || '请求失败'
    ElMessage.error(`画像生成失败：${msg}`)
  } finally {
    loading.value = false
  }
}

defineExpose({ educationLevel, educationYear, discipline, major, crossDisciplines, courses })
</script>

<template>
  <el-dialog
    :model-value="true"
    width="680px"
    :close-on-click-modal="false"
    :show-close="false"
  >
    <template #header>
      <div class="q-header">
        <span>构建学习画像</span>
        <el-steps :active="step" finish-status="success" align-center style="flex:1;margin:0 40px">
          <el-step title="学历背景" />
          <el-step title="学科归属" />
          <el-step title="专业选择" />
          <el-step title="薄弱课程" />
          <el-step title="确认提交" />
        </el-steps>
      </div>
    </template>

    <!-- Step 0: 学历背景 -->
    <div v-if="step === 0" class="q-step">
      <h4>你目前的学历层次与年级是？</h4>
      <div class="level-grid">
        <div
          v-for="lev in config.education_levels || []" :key="lev"
          :class="['level-card', { active: educationLevel === lev }]"
          @click="educationLevel = lev; educationYear = ''"
        >
          {{ lev }}
        </div>
      </div>
      <div v-if="educationLevel" class="year-grid">
        <el-radio-group v-model="educationYear">
          <el-radio-button v-for="y in years" :key="y" :value="y">{{ y }}</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- Step 1: 学科归属 -->
    <div v-else-if="step === 1" class="q-step">
      <h4>你的主修学科门类是？</h4>
      <div class="discipline-grid">
        <div
          v-for="d in disciplines" :key="d"
          :class="['disc-card', { active: discipline === d }]"
          @click="discipline = d"
        >
          {{ d }}
        </div>
      </div>
      <div v-if="discipline" style="margin-top:20px">
        <h5>你的课程还涉及其他领域吗？（最多2项）</h5>
        <el-checkbox-group v-model="crossDisciplines" :max="2">
          <el-checkbox
            v-for="d in otherDisciplines"
            :key="d" :value="d" :label="d"
          />
        </el-checkbox-group>
      </div>
    </div>

    <!-- Step 2: 专业选择 -->
    <div v-else-if="step === 2" class="q-step">
      <h4>请选择你的专业</h4>
      <p class="q-desc">
        当前学科门类：<el-tag size="small" type="primary">{{ discipline }}</el-tag>
      </p>

      <!-- 已选专业 -->
      <div v-if="major" class="selected-major">
        <el-tag type="success" size="large" closable @close="clearMajor">
          {{ major }}
          <template v-if="isCustomMajor"><span style="color:#909399;font-size:11px">（自行输入）</span></template>
        </el-tag>
      </div>

      <!-- 搜索栏 -->
      <div class="major-search-row">
        <el-input
          v-model="majorSearch"
          placeholder="搜索专业名称..."
          clearable
          style="width:320px"
          @input="doMajorSearch"
          @keyup.enter="doMajorSearch"
        >
          <template #prefix>
            <el-icon><component :is="'Search'" /></el-icon>
          </template>
        </el-input>
      </div>

      <!-- 搜索结果 -->
      <div v-if="searchResults.length > 0" class="search-results">
        <div
          v-for="name in searchResults" :key="name"
          :class="['search-item', { active: major === name }]"
          @click="selectMajor(name)"
        >
          {{ name }}
        </div>
      </div>

      <!-- 专业树（未搜索时显示） -->
      <div v-if="!majorSearch.trim() && !searchResults.length" class="major-tree">
        <el-collapse v-if="majorTree.length > 0">
          <el-collapse-item
            v-for="cat in majorTree" :key="cat.category"
          >
            <template #title>
              <span class="cat-title">{{ cat.category }}</span>
              <el-tag size="small" type="info" style="margin-left:8px">{{ cat.majors.length }}个</el-tag>
            </template>
            <div class="major-list">
              <div
                v-for="name in cat.majors" :key="name"
                :class="['major-item', { active: major === name }]"
                @click="selectMajor(name)"
              >
                {{ name }}
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
        <div v-else style="color:#909399;padding:20px 0;text-align:center">
          加载专业列表中...
        </div>
      </div>

      <!-- 自定义输入 -->
      <el-divider />
      <div class="custom-major">
        <span style="color:#909399;font-size:13px;margin-right:8px">没有我的专业：</span>
        <el-input
          v-model="customMajorInput"
          placeholder="输入你的专业名称"
          style="width:200px"
          @keyup.enter="confirmCustomMajor"
        />
        <el-button type="primary" size="small" style="margin-left:8px" @click="confirmCustomMajor">
          自行输入
        </el-button>
      </div>
    </div>

    <!-- Step 3: 薄弱课程 -->
    <div v-else-if="step === 3" class="q-step">
      <h4>选择你的薄弱课程</h4>
      <p class="q-desc">系统根据你的学科和年级推荐了以下种子课程，点击添加或搜索其他课程：</p>

      <div class="seed-tags">
        <el-tag
          v-for="c in seedCourses" :key="c"
          :type="isCourseAdded(c) ? 'success' : 'info'"
          size="large"
          class="seed-tag"
          @click="toggleCourse(c)"
        >
          {{ c }} {{ isCourseAdded(c) ? '✓' : '+' }}
        </el-tag>
      </div>

      <div class="search-row">
        <el-input v-model="courseSearch" placeholder="搜索其他课程..." style="width:240px" @keyup.enter="searchCourse" />
        <el-button @click="searchCourse">添加</el-button>
      </div>

      <div v-if="courses.length > 0" class="added-courses">
        <el-divider />
        <h5>已添加课程（{{ courses.length }}门）：</h5>
        <div v-for="c in courses" :key="c.name" class="added-item">
          <span class="course-name">{{ c.name }}</span>
          <span class="course-detail" v-if="c.knowledge_points">- {{ c.knowledge_points.slice(0, 40) }}...</span>
          <el-button size="small" text @click="currentCourse = { ...c }; showCourseEdit = true">编辑</el-button>
          <el-button size="small" text type="danger" @click="removeCourse(c.name)">删除</el-button>
        </div>
      </div>

      <el-dialog
        v-model="showCourseEdit"
        width="520px"
        title="编辑薄弱课程"
        append-to-body
      >
        <el-form label-width="90px">
          <el-form-item label="课程名称">
            <el-input v-model="currentCourse.name" />
          </el-form-item>
          <el-form-item label="薄弱知识点">
            <el-input
              v-model="currentCourse.knowledge_points"
              type="textarea"
              :rows="2"
              placeholder="哪一章、哪个概念最让你头疼？"
            />
          </el-form-item>
          <el-form-item label="困难类型">
            <el-checkbox-group v-model="currentCourse.difficulty_types">
              <el-checkbox v-for="t in difficultyTypes" :key="t" :value="t" :label="t" />
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="影响范围">
            <el-checkbox-group v-model="currentCourse.impacts">
              <el-checkbox v-for="i in impacts" :key="i" :value="i" :label="i" />
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="学习目标">
            <el-radio-group v-model="currentCourse.goal">
              <el-radio v-for="g in courseGoals" :key="g" :value="g">{{ g }}</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showCourseEdit = false">取消</el-button>
          <el-button type="primary" @click="saveCourse">保存</el-button>
        </template>
      </el-dialog>
    </div>

    <!-- Step 4: 确认提交 -->
    <div v-else-if="step === 4" class="q-step">
      <h4>确认提交</h4>
      <div class="summary-card">
        <div class="summary-row">
          <span class="s-label">学历背景</span>
          <span class="s-value">{{ educationLevel }} {{ educationYear }}</span>
        </div>
        <div class="summary-row">
          <span class="s-label">学科·专业</span>
          <span class="s-value">{{ discipline }} · {{ major }}<template v-if="isCustomMajor">（自行输入）</template></span>
        </div>
        <div class="summary-row">
          <span class="s-label">交叉学科</span>
          <span class="s-value"><template v-if="crossDisciplines.length">{{ crossDisciplines.join('、') }}</template><template v-else>无</template></span>
        </div>
        <div class="summary-row">
          <span class="s-label">薄弱课程</span>
          <span class="s-value">{{ courses.length }}门</span>
        </div>
        <div v-for="c in courses" :key="c.name" class="course-summary">
          <el-tag type="danger" size="small">{{ c.name }}</el-tag>
          <span>{{ c.knowledge_points }}</span>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="q-footer">
        <el-button v-if="step > 0" @click="prevStep">上一步</el-button>
        <el-button @click="emit('cancel')">取消</el-button>
        <el-button v-if="step < 4" type="primary" @click="nextStep">下一步</el-button>
        <el-button v-else type="primary" :loading="loading" @click="submitQuestionnaire">
          生成画像
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.q-header { display: flex; align-items: center; }
.q-step { min-height: 300px; max-height: 520px; overflow-y: auto; }
.q-step h4 { color: #303133; margin-bottom: 16px; }
.q-desc { color: #909399; font-size: 13px; margin-bottom: 12px; }

.level-grid, .discipline-grid { display: flex; gap: 10px; flex-wrap: wrap; }
.level-card, .disc-card {
  padding: 12px 20px;
  border-radius: 8px;
  border: 1px solid #dcdfe6;
  cursor: pointer;
  transition: 0.2s;
  font-size: 14px;
}
.level-card:hover, .disc-card:hover { border-color: #409eff; color: #409eff; }
.level-card.active, .disc-card.active {
  border-color: #409eff;
  background: #ecf5ff;
  color: #409eff;
  font-weight: 600;
}

.year-grid { margin-top: 16px; }

/* 专业选择 */
.selected-major { margin-bottom: 16px; }
.major-search-row { margin-bottom: 12px; }

.search-results {
  display: flex; gap: 8px; flex-wrap: wrap;
  margin-bottom: 12px;
}
.search-item {
  padding: 8px 16px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  cursor: pointer;
  font-size: 14px;
  transition: 0.15s;
}
.search-item:hover { border-color: #409eff; color: #409eff; }
.search-item.active { border-color: #409eff; background: #ecf5ff; color: #409eff; font-weight: 600; }

.major-tree { margin-bottom: 8px; }
.cat-title { font-weight: 600; font-size: 14px; color: #303133; }

.major-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
  padding: 8px 0 12px;
}
.major-item {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  cursor: pointer;
  font-size: 13px;
  transition: 0.15s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.major-item:hover { border-color: #409eff; color: #409eff; }
.major-item.active { border-color: #409eff; background: #ecf5ff; color: #409eff; font-weight: 600; }

.custom-major { display: flex; align-items: center; }

/* 薄弱课程 */
.seed-tags { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.seed-tag { cursor: pointer; font-size: 14px; }

.search-row { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }

.added-courses { margin-top: 8px; }
.added-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
.course-name { font-weight: 600; color: #303133; }
.course-detail { color: #909399; font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 确认 */
.summary-card { background: #f5f7fa; border-radius: 8px; padding: 20px; }
.summary-row { display: flex; justify-content: space-between; margin-bottom: 12px; }
.s-label { color: #909399; font-size: 13px; }
.s-value { color: #303133; font-weight: 500; }
.course-summary { display: flex; align-items: center; gap: 8px; padding: 8px; background: #fff; border-radius: 4px; margin-bottom: 6px; }
.course-summary span { color: #606266; font-size: 13px; }

.q-footer { display: flex; justify-content: flex-end; gap: 8px; }
</style>
