<template>
  <div class="shell">
    <!-- 桌面端左侧导航 -->
    <aside class="sidebar">
      <div class="brand">🔔 {{ t('app.title') }}</div>
      <nav>
        <router-link v-for="it in navItems" :key="it.to" :to="it.to" class="nav-card">
          <span class="nav-ico" v-html="icon(it.key)"></span>
          <span class="nav-label">{{ t(it.label) }}</span>
          <span class="nav-arrow">›</span>
        </router-link>
      </nav>
      <div class="spacer"></div>
      <div class="user" v-if="auth.user">
        <div class="uname">{{ auth.user.username }}</div>
        <a href="#" @click.prevent="logout">🚪 {{ t('nav.logout') }}</a>
      </div>
      <div class="credit">
        <a href="https://t.me/Aiden_SU" target="_blank" rel="noopener">✈️ TG @Aiden_SU</a>
        <a href="mailto:aidensu8182@gmail.com">✉️ aidensu8182@gmail.com</a>
      </div>
    </aside>

    <main class="content">
      <router-link v-if="updateInfo && updateInfo.update_available && !bannerDismissed" to="/settings" class="upd-banner" @click="dismissBanner">
        <span>🎉 {{ t('upd.banner', { v: updateInfo.latest }) }}</span>
        <a href="#" class="x" @click.prevent.stop="dismissBanner">✕</a>
      </router-link>
      <router-view />
    </main>

    <!-- 手机端底部标签栏 -->
    <nav class="tabbar" aria-label="tabs">
      <router-link v-for="it in tabItems" :key="it.to" :to="it.to" class="tab">
        <span class="tab-ico" v-html="icon(it.key)"></span>
        <span class="tab-label">{{ t(it.label) }}</span>
      </router-link>
      <button type="button" class="tab" :class="{ active: moreActive || sheet }" @click="sheet = true">
        <span class="tab-ico" v-html="icon('more')"></span>
        <span class="tab-label">{{ t('nav.more') }}</span>
      </button>
    </nav>

    <!-- 手机端「更多」底部抽屉面板 -->
    <div v-if="sheet" class="modal-mask" @click.self="sheet = false">
      <div class="modal more-sheet" role="dialog" :aria-label="t('nav.more')">
        <div class="ms-user" v-if="auth.user">
          <span class="ms-avatar" aria-hidden="true">{{ initial }}</span>
          <div class="ms-uname">{{ auth.user.username }}</div>
        </div>
        <router-link v-for="it in moreItems" :key="it.to" :to="it.to" class="ms-item" @click="sheet = false">
          <span class="ms-ico" v-html="icon(it.key)"></span>
          <span class="nav-label">{{ t(it.label) }}</span>
          <span class="ms-chev" v-html="icon('chevron')"></span>
        </router-link>
        <button type="button" class="ms-item danger" @click="logout">
          <span class="ms-ico" v-html="icon('logout')"></span>
          <span class="nav-label">{{ t('nav.logout') }}</span>
        </button>
        <div class="credit ms-credit">
          <a href="https://t.me/Aiden_SU" target="_blank" rel="noopener">✈️ TG @Aiden_SU</a>
          <a href="mailto:aidensu8182@gmail.com">✉️ aidensu8182@gmail.com</a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { useAuth } from '../stores/auth'
import { icon } from '../icons'

const { t } = useI18n()
const auth = useAuth()
const router = useRouter()
const route = useRoute()
const sheet = ref(false)

const updateInfo = ref(null)
const bannerDismissed = ref(false)
function dismissBanner() {
  bannerDismissed.value = true
  try { sessionStorage.setItem('upd_dismissed', updateInfo.value?.latest || '1') } catch { /* ignore */ }
}
onMounted(async () => {
  try {
    const { data } = await api.get('/api/system/version-check')
    updateInfo.value = data
    if (sessionStorage.getItem('upd_dismissed') === (data.latest || '')) bannerDismissed.value = true
  } catch { /* ignore */ }
})

const initial = computed(() => (auth.user?.username || '?').charAt(0).toUpperCase())

const navItems = computed(() => {
  const base = [
    { to: '/dashboard', key: 'dashboard', label: 'nav.dashboard', tab: true },
    { to: '/subscriptions', key: 'subscriptions', label: 'nav.subscriptions', tab: true },
    { to: '/calendar', key: 'calendar', label: 'nav.calendar', tab: true },
    { to: '/reports', key: 'reports', label: 'nav.reports', tab: true },
    { to: '/icons', key: 'icons', label: 'nav.icons' },
    { to: '/notifications', key: 'notifications', label: 'nav.notifications' },
    { to: '/logs', key: 'logs', label: 'nav.logs' },
    { to: '/settings', key: 'settings', label: 'nav.settings' }
  ]
  if (auth.user?.is_admin) base.push({ to: '/users', key: 'users', label: 'nav.users' })
  return base
})
const tabItems = computed(() => navItems.value.filter((x) => x.tab))
const moreItems = computed(() => navItems.value.filter((x) => !x.tab))
const moreActive = computed(() => moreItems.value.some((x) => route.path.startsWith(x.to)))

function logout() {
  sheet.value = false
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.shell { display: flex; min-height: 100vh; }
.sidebar { width: 230px; background: var(--surface); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; padding: 18px 14px; position: sticky; top: 0; height: 100vh; z-index: 50; }
.brand { font-weight: 700; font-size: 16px; margin-bottom: 22px;
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
nav { display: flex; flex-direction: column; gap: 7px; }
.nav-card { display: flex; align-items: center; gap: 10px; padding: 9px 11px; border-radius: 12px;
  color: var(--text); font-size: 14px; border: 1px solid transparent; background: var(--surface-2);
  transition: transform .15s ease, background .15s ease, box-shadow .2s ease, border-color .15s ease; }
.nav-ico { width: 30px; height: 30px; border-radius: 9px; display: flex; align-items: center;
  justify-content: center; background: var(--surface); border: 1px solid var(--border);
  flex-shrink: 0; transition: transform .2s ease; color: var(--text-soft); }
.upd-banner { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-bottom: 16px; padding: 10px 14px; border-radius: 12px; font-size: 14px; text-decoration: none;
  background: linear-gradient(120deg, var(--primary-soft), var(--surface)); color: var(--text);
  border: 1px solid var(--primary); }
.upd-banner .x { color: var(--text-soft); text-decoration: none; font-size: 13px; }
.nav-ico :deep(svg) { width: 17px; height: 17px; }
.nav-card:hover .nav-ico { color: var(--primary); }
.nav-card.router-link-active .nav-ico { color: #fff; }
.nav-label { flex: 1; font-weight: 500; }
.nav-arrow { color: var(--text-soft); opacity: 0; transform: translateX(-4px); transition: all .2s ease; }
.nav-card:hover { transform: translateX(3px); background: var(--primary-soft); border-color: color-mix(in srgb, var(--primary) 30%, var(--border)); }
.nav-card:hover .nav-ico { transform: scale(1.1) rotate(-4deg); }
.nav-card:hover .nav-arrow { opacity: 1; transform: translateX(0); }
.nav-card.router-link-active { background: linear-gradient(135deg, var(--primary), var(--primary-2));
  color: #fff; box-shadow: 0 6px 16px rgba(91,91,214,.32); border-color: transparent; }
.nav-card.router-link-active .nav-ico { background: rgba(255,255,255,.22); border-color: transparent; }
.nav-card.router-link-active .nav-arrow { opacity: 1; transform: translateX(0); color: #fff; }
.spacer { flex: 1; }
.user { font-size: 13px; color: var(--text-soft); border-top: 1px solid var(--border); padding-top: 12px; }
.user .uname { font-weight: 600; color: var(--text); }
.user a { display: block; margin-top: 6px; }
.credit { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 5px; }
.credit a { font-size: 12px; color: var(--text-soft); display: flex; align-items: center; gap: 5px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: color .15s ease; }
.credit a:hover { color: var(--primary); }
.content { flex: 1; min-width: 0; padding: 26px 32px; max-width: 1200px; width: 100%; }

/* 手机底部标签栏仅移动端显示 */
.tabbar { display: none; }
.more-sheet { padding-top: 18px; }
.ms-user { display: flex; align-items: center; gap: 10px; padding: 4px 4px 14px;
  border-bottom: 1px solid var(--border); margin-bottom: 4px; }
.ms-avatar { width: 34px; height: 34px; border-radius: 50%; display: inline-flex; align-items: center;
  justify-content: center; background: linear-gradient(135deg, var(--primary), var(--primary-2));
  color: #fff; font-weight: 700; font-size: 14px; flex-shrink: 0; }
.ms-uname { font-weight: 600; font-size: 15px; color: var(--text); }
.ms-item { width: 100%; display: flex; align-items: center; gap: 12px; min-height: 48px; padding: 0 6px;
  border: 0; border-bottom: 1px solid var(--border); background: none; font: inherit; font-size: 15px;
  color: var(--text); text-decoration: none; cursor: pointer; text-align: left; }
.ms-ico { width: 20px; height: 20px; display: inline-flex; color: var(--text-soft); flex-shrink: 0; }
.ms-ico :deep(svg) { width: 20px; height: 20px; }
.ms-chev { width: 16px; height: 16px; display: inline-flex; color: var(--text-soft); }
.ms-chev :deep(svg) { width: 16px; height: 16px; }
.ms-item.router-link-active { color: var(--primary); font-weight: 600; }
.ms-item.router-link-active .ms-ico { color: var(--primary); }
.ms-item.danger { color: var(--danger); border-bottom: 0; }
.ms-item.danger .ms-ico { color: var(--danger); }
.ms-credit { border-top: 1px solid var(--border); margin-top: 8px; padding-top: 12px; }

@media (max-width: 860px) {
  .shell { display: block; }
  .sidebar { display: none; }
  .content { padding: calc(16px + env(safe-area-inset-top)) 14px calc(88px + env(safe-area-inset-bottom)); }
  .tabbar { display: grid; grid-template-columns: repeat(5, 1fr); position: fixed; left: 0; right: 0; bottom: 0;
    z-index: 60; padding: 6px 6px calc(6px + env(safe-area-inset-bottom)); gap: 2px;
    background: color-mix(in srgb, var(--surface) 88%, transparent); border-top: 1px solid var(--border);
    backdrop-filter: blur(16px) saturate(160%); -webkit-backdrop-filter: blur(16px) saturate(160%); }
  .tab { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
    min-height: 50px; border: 0; background: none; font: inherit; color: var(--text-soft);
    text-decoration: none; border-radius: 10px; cursor: pointer; padding: 4px 2px;
    -webkit-tap-highlight-color: transparent; }
  .tab-ico { width: 22px; height: 22px; display: inline-flex; }
  .tab-ico :deep(svg) { width: 22px; height: 22px; }
  .tab-label { font-size: 11px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
  .tab.router-link-active, .tab.active { color: var(--primary); font-weight: 600; }
  .tab.router-link-active .tab-ico, .tab.active .tab-ico { color: var(--primary); }
  .tab:active { background: var(--surface-2); }
}
</style>
