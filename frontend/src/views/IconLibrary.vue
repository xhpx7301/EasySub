<template>
  <div>
    <div class="head">
      <h1>{{ t('icons.title') }}</h1>
      <button class="btn" @click="openNew">+ {{ t('icons.add') }}</button>
    </div>

    <div class="bar">
      <input v-model="search" class="search-box" :placeholder="t('icons.searchPh')" />
      <div class="scope-tabs" role="group" :aria-label="t('icons.title')">
        <button class="scope-tab" :class="{ on: scope === 'all' }" :aria-pressed="scope === 'all'" @click="scope = 'all'">{{ t('icons.all') }}</button>
        <button class="scope-tab" :class="{ on: scope === 'global' }" :aria-pressed="scope === 'global'" @click="scope = 'global'">{{ t('icons.global') }}</button>
        <button class="scope-tab" :class="{ on: scope === 'personal' }" :aria-pressed="scope === 'personal'" @click="scope = 'personal'">{{ t('icons.personal') }}</button>
      </div>
    </div>

    <div v-if="loading" class="card muted">{{ t('common.loading') }}</div>
    <div v-else-if="!filteredItems.length" class="card muted">{{ t('icons.empty') }}</div>
    <div v-else class="icon-management-grid">
      <div v-for="item in filteredItems" :key="item.id" class="card icon-item" :class="{ disabled: !item.is_enabled }">
        <img :src="item.icon" :alt="item.name" class="icon-preview" @error="onImageError" />
        <div class="icon-item-main">
          <div class="icon-item-title">
            <b>{{ item.name }}</b>
            <span class="tag" :class="item.is_global ? 'global' : 'personal'">{{ item.is_global ? t('icons.global') : t('icons.personal') }}</span>
          </div>
          <div v-if="item.domain" class="muted icon-domain">{{ item.domain }}</div>
          <div class="muted icon-category">{{ item.category_label }}</div>
          <div v-if="!item.is_enabled" class="muted">{{ t('icons.disabled') }}</div>
        </div>
        <div v-if="item.can_edit" class="icon-item-actions">
          <button class="btn ghost sm" @click="openEdit(item)">{{ t('icons.edit') }}</button>
          <button class="btn danger sm" @click="removeItem(item)">{{ t('icons.delete') }}</button>
        </div>
      </div>
    </div>

    <div v-if="showForm" class="modal-mask" @click.self="showForm = false">
      <div class="modal icon-form">
        <h3>{{ editing ? t('icons.editTitle') : t('icons.addTitle') }}</h3>
        <label>{{ t('icons.name') }}</label>
        <input v-model="form.name" maxlength="128" />
        <label>{{ t('icons.domain') }}</label>
        <input v-model="form.domain" placeholder="example.com" maxlength="255" />
        <label>{{ t('icons.category') }}</label>
        <select v-model="form.category">
          <option v-for="c in categories" :key="c.key" :value="c.key">{{ c.label }}</option>
        </select>
        <label>{{ t('icons.iconUrl') }}</label>
        <input v-model="form.icon_url" placeholder="/static/icons/... or https://..." />
        <div class="row icon-upload-row">
          <label class="btn ghost sm">{{ t('icons.upload') }}
            <input type="file" accept="image/*" hidden @change="upload" />
          </label>
          <img v-if="form.icon_url" :src="form.icon_url" class="icon-form-preview" @error="onImageError" />
        </div>
        <label class="switch"><input v-model="form.is_enabled" type="checkbox" /> <span>{{ t('icons.enabled') }}</span></label>
        <label v-if="auth.user?.is_admin && !editing" class="switch"><input v-model="form.global_item" type="checkbox" /> <span>{{ t('icons.globalNew') }}</span></label>
        <p v-if="error" class="err">{{ error }}</p>
        <div class="row form-actions">
          <button class="btn ghost" @click="showForm = false">{{ t('common.cancel') }}</button>
          <button class="btn" :disabled="saving" @click="save">{{ t('common.save') }}</button>
        </div>
      </div>
    </div>

    <p v-if="message" class="ok">{{ message }}</p>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../api'
import { useAuth } from '../stores/auth'

const { t } = useI18n()
const auth = useAuth()
const items = ref([])
const categories = ref([])
const search = ref('')
const scope = ref('all')
const loading = ref(true)
const saving = ref(false)
const showForm = ref(false)
const editing = ref(null)
const error = ref('')
const message = ref('')
const form = reactive({ name: '', domain: '', category: 'other', icon_url: '', is_enabled: true, global_item: false })

const filteredItems = computed(() => {
  const q = search.value.trim().toLowerCase()
  return items.value.filter((item) => {
    if (scope.value === 'global' && !item.is_global) return false
    if (scope.value === 'personal' && item.is_global) return false
    if (!q) return true
    return [item.name, item.domain, item.category_label].some((v) => String(v || '').toLowerCase().includes(q))
  })
})

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/api/icons/manage')
    items.value = data.items || []
    categories.value = data.categories || []
  } catch (e) {
    error.value = e.response?.data?.detail || 'Error'
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, { name: '', domain: '', category: 'other', icon_url: '', is_enabled: true, global_item: false })
  error.value = ''
}
function openNew() { editing.value = null; resetForm(); showForm.value = true }
function openEdit(item) {
  editing.value = item
  Object.assign(form, { name: item.name, domain: item.domain, category: item.category, icon_url: item.icon_url, is_enabled: item.is_enabled, global_item: item.is_global })
  error.value = ''; showForm.value = true
}
async function upload(event) {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    const data = new FormData()
    data.append('file', file)
    const response = await api.post('/api/icons/upload', data)
    form.icon_url = response.data.url
  } catch (e) { error.value = e.response?.data?.detail || 'Error' }
  event.target.value = ''
}
async function save() {
  error.value = ''; saving.value = true
  try {
    const payload = { ...form }
    const response = editing.value
      ? await api.put(`/api/icons/manage/${editing.value.id}`, payload)
      : await api.post('/api/icons/manage', payload)
    if (editing.value) {
      const index = items.value.findIndex((item) => item.id === editing.value.id)
      if (index >= 0) items.value[index] = response.data
    } else items.value.push(response.data)
    showForm.value = false
    message.value = t('icons.saved')
    setTimeout(() => { message.value = '' }, 2500)
  } catch (e) { error.value = e.response?.data?.detail || 'Error' }
  finally { saving.value = false }
}
async function removeItem(item) {
  if (!window.confirm(t('icons.deleteConfirm', { name: item.name }))) return
  try {
    await api.delete(`/api/icons/manage/${item.id}`)
    items.value = items.value.filter((x) => x.id !== item.id)
  } catch (e) { error.value = e.response?.data?.detail || 'Error' }
}
function onImageError(event) { event.target.style.visibility = 'hidden' }

onMounted(load)
</script>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.head h1 { margin: 0; }
.bar { display: grid; grid-template-columns: minmax(220px, 1fr) auto; align-items: center; gap: 12px; margin-bottom: 16px; }
.search-box { width: 100%; min-width: 0; }
.scope-tabs { display: inline-flex; align-items: center; gap: 4px; padding: 4px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.scope-tab { min-width: 58px; border: 0; border-radius: 7px; padding: 7px 11px; background: transparent; color: var(--text-soft); font: inherit; font-size: 13px; font-weight: 600; line-height: 1.2; cursor: pointer; transition: background .15s ease, color .15s ease, box-shadow .15s ease; }
.scope-tab:hover { color: var(--primary); background: var(--primary-soft); }
.scope-tab.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; box-shadow: 0 2px 7px color-mix(in srgb, var(--primary) 32%, transparent); }
.icon-management-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.icon-item { display: flex; align-items: center; gap: 12px; min-width: 0; }
.icon-item.disabled { opacity: .58; }
.icon-preview { width: 48px; height: 48px; flex: 0 0 48px; object-fit: contain; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.icon-item-main { min-width: 0; flex: 1; }
.icon-item-title { display: flex; align-items: center; gap: 6px; min-width: 0; }
.icon-item-title b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.icon-domain, .icon-category { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.icon-item-actions { display: flex; gap: 5px; flex-shrink: 0; }
.tag.global { background: var(--primary-soft); color: var(--primary); }
.tag.personal { background: var(--surface-2); color: var(--text-soft); }
.icon-form { max-width: 520px; }
.icon-upload-row { align-items: center; gap: 10px; margin: 8px 0 12px; }
.icon-form-preview { width: 40px; height: 40px; object-fit: contain; border: 1px solid var(--border); border-radius: 8px; }
.form-actions { justify-content: flex-end; margin-top: 18px; }
.switch { display: flex; align-items: center; gap: 6px; width: auto; margin: 8px 0 0; }
.switch input { width: auto; }
.err { color: var(--danger); font-size: 13px; margin: 8px 0 0; }
.ok { color: var(--success); font-size: 13px; }
@media (max-width: 600px) {
  .head { align-items: flex-start; flex-direction: column; }
  .bar { grid-template-columns: 1fr; }
  .scope-tabs { width: 100%; }
  .scope-tab { flex: 1; }
  .icon-management-grid { grid-template-columns: 1fr; }
  .icon-item-actions { flex-direction: column; }
}
</style>
