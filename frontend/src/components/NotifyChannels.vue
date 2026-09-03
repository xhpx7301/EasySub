<template>
  <div class="card sect notify">
    <div class="nc-head">
      <div>
        <h3>🔔 {{ t('notifyCfg.title') }}</h3>
        <p class="muted" style="font-size:13px;margin:2px 0 0">Telegram / 飞书 / QQ / Bark / Email / Pushplus / Webhook</p>
      </div>
      <button class="btn" :disabled="saving" @click="save">💾 {{ t('notifyCfg.save') }}</button>
    </div>

    <div class="tabs">
      <button v-for="tb in tabs" :key="tb.key" class="tab" :class="{ on: tab === tb.key }" @click="tab = tb.key">
        {{ tb.label }}<span v-if="cfg[tb.key] && cfg[tb.key].enabled" class="on-dot"></span>
      </button>
    </div>

    <div v-if="loaded" class="panel">
      <div class="ch-head">
        <h4>{{ enableLabel }}</h4>
        <div class="ch-actions">
          <button class="btn ghost sm" :disabled="testing" @click="test(tab)">🔔 {{ t('notifyCfg.test') }}</button>
          <label class="switch"><input type="checkbox" v-model="cfg[tab].enabled" /><span class="track"></span></label>
        </div>
      </div>

      <!-- Telegram -->
      <div v-if="tab === 'telegram'" class="fields">
        <div class="f"><label>BOT TOKEN</label><input v-model="cfg.telegram.bot_token" placeholder="123456:ABC-..." /></div>
        <div class="two">
          <div class="f"><label>CHAT ID</label><input v-model="cfg.telegram.chat_id" placeholder="-100xxxx / 数字" /></div>
          <div class="f"><label>ADMIN ID</label><input v-model="cfg.telegram.admin_id" /></div>
        </div>
        <div class="f"><label>{{ t('notifyCfg.tgApiBase') }}</label><input v-model="cfg.telegram.api_base" placeholder="api.telegram.org" /></div>
        <div class="f"><label>{{ t('notifyCfg.httpProxy') }}</label><input v-model="cfg.telegram.proxy" placeholder="http://127.0.0.1:7890" /></div>
        <div class="row">
          <button class="btn ghost sm" @click="tgAction('me')">{{ t('settings.checkBot') }}</button>
          <button class="btn ghost sm" @click="tgAction('updates')">{{ t('settings.getUpdates') }}</button>
        </div>
      </div>

      <!-- 飞书 -->
      <div v-else-if="tab === 'feishu'" class="fields">
        <div class="two">
          <div class="f"><label>APP ID</label><input v-model="cfg.feishu.app_id" placeholder="cli_xxxx" /></div>
          <div class="f"><label>APP SECRET</label><input v-model="cfg.feishu.app_secret" type="password" /></div>
        </div>
        <div class="f"><label>CHAT IDS</label><input v-model="cfg.feishu.chat_ids" placeholder="oc_xxxx，多个逗号分隔" />
          <small class="muted">{{ t('notifyCfg.feishuHint') }}</small></div>
      </div>

      <!-- QQ -->
      <div v-else-if="tab === 'qq'" class="fields">
        <div class="two">
          <div class="f"><label>APP ID</label><input v-model="cfg.qq.app_id" placeholder="QQ Bot App ID" /></div>
          <div class="f"><label>APP SECRET</label><input v-model="cfg.qq.app_secret" type="password" /></div>
        </div>
        <div class="two">
          <div class="f"><label>{{ t('notifyCfg.qqGroups') }}</label><input v-model="cfg.qq.group_ids" placeholder="群聊 OpenID，多个逗号分隔" /></div>
          <div class="f"><label>{{ t('notifyCfg.qqUsers') }}</label><input v-model="cfg.qq.user_ids" placeholder="用户 OpenID，多个逗号分隔" /></div>
        </div>
        <small class="muted">{{ t('notifyCfg.qqHint') }}</small>
      </div>

      <!-- Bark -->
      <div v-else-if="tab === 'bark'" class="fields">
        <div class="f">
          <div class="f-h"><label>{{ t('notifyCfg.targetUrls') }}</label>
            <button class="btn ghost xs" @click="cfg.bark.urls.push('')">+ URL</button></div>
          <p v-if="!cfg.bark.urls.length" class="empty">{{ t('notifyCfg.noBarkUrl') }}</p>
          <div v-for="(u, i) in cfg.bark.urls" :key="i" class="list-row">
            <input v-model="cfg.bark.urls[i]" placeholder="https://api.day.app/你的Key" />
            <button class="x" @click="cfg.bark.urls.splice(i, 1)">✕</button>
          </div>
        </div>
        <div class="two">
          <div class="f"><label>{{ t('notifyCfg.barkGroup') }}</label><input v-model="cfg.bark.group" placeholder="EasySub" /></div>
          <div class="f"><label>{{ t('notifyCfg.barkLevel') }}</label>
            <select v-model="cfg.bark.level">
              <option value="active">active</option><option value="timeSensitive">timeSensitive</option>
              <option value="passive">passive</option><option value="critical">critical</option>
            </select></div>
        </div>
        <div class="f"><label>ICON</label><input v-model="cfg.bark.icon" placeholder="图标 URL，可选" /></div>
      </div>

      <!-- Email -->
      <div v-else-if="tab === 'email'" class="fields">
        <div class="three">
          <div class="f"><label>SMTP {{ t('notifyCfg.host') }}</label><input v-model="cfg.email.host" placeholder="smtp.example.com" /></div>
          <div class="f"><label>SMTP {{ t('notifyCfg.port') }}</label><input v-model.number="cfg.email.port" type="number" /></div>
          <div class="f sw"><label>SSL/TLS</label><label class="switch"><input type="checkbox" v-model="cfg.email.ssl" /><span class="track"></span></label></div>
        </div>
        <div class="two">
          <div class="f"><label>{{ t('notifyCfg.username') }}</label><input v-model="cfg.email.username" placeholder="邮箱账号" /></div>
          <div class="f"><label>{{ t('notifyCfg.password') }}</label><input v-model="cfg.email.password" type="password" placeholder="密码或授权码" /></div>
        </div>
        <div class="f"><label>{{ t('notifyCfg.from') }}</label><input v-model="cfg.email.from" placeholder="noreply@example.com" /></div>
        <div class="f"><label>{{ t('notifyCfg.to') }}</label><input v-model="cfg.email.to" placeholder="多个收件人用英文逗号分隔" /></div>
      </div>

      <!-- Pushplus -->
      <div v-else-if="tab === 'pushplus'" class="fields">
        <div class="f"><label>TOKEN</label><input v-model="cfg.pushplus.token" placeholder="Pushplus 用户 Token" /></div>
        <div class="two">
          <div class="f"><label>{{ t('notifyCfg.ppTopic') }}</label><input v-model="cfg.pushplus.topic" placeholder="群组编码，不填发给个人" /></div>
          <div class="f"><label>{{ t('notifyCfg.ppChannel') }}</label>
            <select v-model="cfg.pushplus.channel">
              <option value="wechat">微信 (wechat)</option><option value="mail">邮件 (mail)</option>
              <option value="webhook">Webhook</option><option value="cp">企业微信 (cp)</option>
            </select></div>
        </div>
      </div>

      <!-- Server酱 -->
      <div v-else-if="tab === 'serverchan'" class="fields">
        <div class="f"><label>SENDKEY</label><input v-model="cfg.serverchan.sendkey" placeholder="SCT... / SendKey" />
          <small class="muted">{{ t('notifyCfg.serverchanHint') }}</small></div>
      </div>

      <!-- 企业微信：群机器人 / 自建应用（对齐 CMSHelp「企业微信配置」） -->
      <div v-else-if="tab === 'wecom'" class="fields">
        <div class="f">
          <label>{{ t('notifyCfg.wecomMode') }}</label>
          <div class="seg">
            <button class="seg-b" :class="{ on: wecomMode === 'webhook' }" @click="cfg.wecom.mode = 'webhook'">
              🤖 {{ t('notifyCfg.wecomModeRobot') }}
            </button>
            <button class="seg-b" :class="{ on: wecomMode === 'app' }" @click="cfg.wecom.mode = 'app'">
              🏢 {{ t('notifyCfg.wecomModeApp') }}
            </button>
          </div>
          <small class="muted">{{ wecomMode === 'app' ? t('notifyCfg.wecomModeAppTip') : t('notifyCfg.wecomModeRobotTip') }}</small>
        </div>

        <!-- 群机器人 -->
        <template v-if="wecomMode === 'webhook'">
          <div class="f"><label>{{ t('notifyCfg.robotUrl') }}</label>
            <input v-model="cfg.wecom.url" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." />
            <small class="muted">{{ t('notifyCfg.wecomHint') }}</small></div>
        </template>

        <!-- 自建应用 -->
        <template v-else>
          <div class="f"><label>{{ t('notifyCfg.wecomCorpId') }}</label>
            <input v-model="cfg.wecom.corp_id" placeholder="ww1234567890abcdef" />
            <small class="muted">{{ t('notifyCfg.wecomCorpIdHint') }}</small></div>
          <div class="two">
            <div class="f"><label>{{ t('notifyCfg.wecomAgentId') }}</label>
              <input v-model="cfg.wecom.agent_id" placeholder="1000002" /></div>
            <div class="f"><label>{{ t('notifyCfg.wecomSecret') }}</label>
              <input v-model="cfg.wecom.secret" type="password" placeholder="应用 Secret" /></div>
          </div>
          <small class="muted" style="margin-top:-6px">{{ t('notifyCfg.wecomAgentHint') }}</small>
          <div class="f"><label>{{ t('notifyCfg.wecomProxy') }}</label>
            <input v-model="cfg.wecom.proxy_base" placeholder="https://qyapi.weixin.qq.com（留空用官方域名）" />
            <small class="muted">{{ t('notifyCfg.wecomProxyHint') }}</small></div>
          <div class="three-e">
            <div class="f"><label>{{ t('notifyCfg.wecomToUser') }}</label>
              <input v-model="cfg.wecom.to_user" placeholder="@all 或 UserID，多个用 | 分隔" /></div>
            <div class="f"><label>{{ t('notifyCfg.wecomToParty') }}</label>
              <input v-model="cfg.wecom.to_party" placeholder="部门ID，可选" /></div>
            <div class="f"><label>{{ t('notifyCfg.wecomToTag') }}</label>
              <input v-model="cfg.wecom.to_tag" placeholder="标签ID，可选" /></div>
          </div>
          <div class="two">
            <div class="f"><label>{{ t('notifyCfg.wecomMsgType') }}</label>
              <select v-model="cfg.wecom.msg_type">
                <option value="text">{{ t('notifyCfg.wecomMsgText') }}</option>
                <option value="markdown">{{ t('notifyCfg.wecomMsgMd') }}</option>
                <option value="textcard">{{ t('notifyCfg.wecomMsgCard') }}</option>
              </select></div>
            <div class="f" v-if="cfg.wecom.msg_type === 'textcard'"><label>{{ t('notifyCfg.wecomCardUrl') }}</label>
              <input v-model="cfg.wecom.card_url" placeholder="点击卡片跳转地址，如 http://你的域名/subs" /></div>
          </div>
          <div class="row">
            <button class="btn ghost sm" :disabled="checking" @click="wecomCheck">
              🔍 {{ t('notifyCfg.wecomCheck') }}
            </button>
          </div>
        </template>

        <!-- Web 端配置说明 -->
        <div class="help">
          <button class="help-h" @click="wecomHelp = !wecomHelp">
            <span>📖 {{ t('notifyCfg.wecomGuide') }}</span><span>{{ wecomHelp ? '▲' : '▼' }}</span>
          </button>
          <div v-show="wecomHelp" class="help-b">
            <ol>
              <li v-for="(s, i) in (wecomMode === 'app' ? wecomSteps : wecomRobotSteps)" :key="i" v-html="s"></li>
            </ol>
            <template v-if="wecomMode === 'app'">
              <p class="warn">⚠️ {{ t('notifyCfg.wecomIpWarn') }}</p>
              <details>
                <summary>{{ t('notifyCfg.wecomProxyExample') }}</summary>
                <pre>{{ nginxSnippet }}</pre>
                <p class="muted">{{ t('notifyCfg.wecomSocatTip') }}</p>
                <pre>{{ socatSnippet }}</pre>
              </details>
              <p class="muted">{{ t('notifyCfg.wecomAesTip') }}</p>
            </template>
            <p class="muted">{{ t('notifyCfg.wecomRef') }}
              <a href="https://github.com/guyue2005/CMSHelp/wiki/8.%E6%B6%88%E6%81%AF%E9%85%8D%E7%BD%AE" target="_blank" rel="noreferrer">CMSHelp Wiki · 消息配置</a>
            </p>
          </div>
        </div>
      </div>

      <!-- 钉钉 -->
      <div v-else-if="tab === 'dingtalk'" class="fields">
        <div class="f"><label>{{ t('notifyCfg.robotUrl') }}</label><input v-model="cfg.dingtalk.url" placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." /></div>
        <div class="f"><label>{{ t('notifyCfg.signSecret') }}</label><input v-model="cfg.dingtalk.secret" placeholder="SEC... 加签密钥，选填" />
          <small class="muted">{{ t('notifyCfg.dingtalkHint') }}</small></div>
      </div>

      <!-- Discord -->
      <div v-else-if="tab === 'discord'" class="fields">
        <div class="f"><label>Webhook URL</label><input v-model="cfg.discord.url" placeholder="https://discord.com/api/webhooks/..." />
          <small class="muted">{{ t('notifyCfg.discordHint') }}</small></div>
      </div>

      <!-- Slack -->
      <div v-else-if="tab === 'slack'" class="fields">
        <div class="f"><label>Webhook URL</label><input v-model="cfg.slack.url" placeholder="https://hooks.slack.com/services/..." />
          <small class="muted">{{ t('notifyCfg.slackHint') }}</small></div>
      </div>

      <!-- ntfy -->
      <div v-else-if="tab === 'ntfy'" class="fields">
        <div class="two">
          <div class="f"><label>{{ t('notifyCfg.server') }}</label><input v-model="cfg.ntfy.server" placeholder="https://ntfy.sh" /></div>
          <div class="f"><label>Topic</label><input v-model="cfg.ntfy.topic" placeholder="your-topic" /></div>
        </div>
        <div class="f"><label>{{ t('notifyCfg.tokenOptional') }}</label><input v-model="cfg.ntfy.token" placeholder="tk_... 访问令牌，选填" />
          <small class="muted">{{ t('notifyCfg.ntfyHint') }}</small></div>
      </div>

      <!-- Gotify -->
      <div v-else-if="tab === 'gotify'" class="fields">
        <div class="two">
          <div class="f"><label>{{ t('notifyCfg.server') }}</label><input v-model="cfg.gotify.server" placeholder="https://gotify.example.com" /></div>
          <div class="f"><label>App Token</label><input v-model="cfg.gotify.token" placeholder="应用 Token" /></div>
        </div>
        <div class="f" style="max-width:160px"><label>{{ t('notifyCfg.priority') }}</label><input v-model.number="cfg.gotify.priority" type="number" /></div>
      </div>

      <!-- Webhook -->
      <div v-else-if="tab === 'webhook'" class="fields">
        <div class="f">
          <div class="f-h"><label>{{ t('notifyCfg.targetUrls') }}</label>
            <button class="btn ghost xs" @click="cfg.webhook.urls.push('')">+ URL</button></div>
          <p v-if="!cfg.webhook.urls.length" class="empty">{{ t('notifyCfg.noWebhookUrl') }}</p>
          <div v-for="(u, i) in cfg.webhook.urls" :key="i" class="list-row">
            <input v-model="cfg.webhook.urls[i]" placeholder="https://example.com/hook" />
            <button class="x" @click="cfg.webhook.urls.splice(i, 1)">✕</button>
          </div>
        </div>
        <div class="f"><label>{{ t('notifyCfg.whSecret') }}</label><input v-model="cfg.webhook.secret" placeholder="HMAC-SHA256 签名密钥，选填" />
          <small class="muted">{{ t('notifyCfg.whSecretHint') }}</small></div>
        <div class="f">
          <div class="f-h"><label>{{ t('notifyCfg.whHeaders') }}</label>
            <button class="btn ghost xs" @click="cfg.webhook.headers.push({ key: '', value: '' })">+ Header</button></div>
          <div v-for="(h, i) in cfg.webhook.headers" :key="i" class="list-row">
            <input v-model="h.key" placeholder="Authorization" style="flex:1" />
            <input v-model="h.value" placeholder="值" style="flex:1.4" />
            <button class="x" @click="cfg.webhook.headers.splice(i, 1)">✕</button>
          </div>
        </div>
        <div class="f"><label>{{ t('notifyCfg.whTemplate') }}</label>
          <textarea v-model="cfg.webhook.template" rows="2" :placeholder="tplPlaceholder"></textarea>
          <small class="muted">{{ t('notifyCfg.whTemplateHint') }}</small></div>
        <div class="two">
          <div class="f"><label>{{ t('notifyCfg.whTimeout') }}</label><input v-model.number="cfg.webhook.timeout_ms" type="number" /></div>
          <div class="f"><label>{{ t('notifyCfg.whRetries') }}</label><input v-model.number="cfg.webhook.max_retries" type="number" /></div>
        </div>
      </div>

      <p v-if="msg" :class="ok ? 'ok' : 'err'">{{ msg }}</p>
    </div>
    <p v-else class="muted">{{ t('common.loading') }}</p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../api'

const { t } = useI18n()
const tab = ref('telegram')
const loaded = ref(false)
const saving = ref(false)
const testing = ref(false)
const msg = ref('')
const ok = ref(false)
const cfg = ref(defaults())
const tplPlaceholder = '{{subject}} {{text}}'
const checking = ref(false)
const wecomHelp = ref(false)
const wecomMode = computed(() => cfg.value.wecom?.mode || 'webhook')
// 说明文案含 <b> 标记，来自 i18n 静态词条（非用户输入），故用 v-html 渲染
const wecomSteps = computed(() => [1, 2, 3, 4, 5, 6].map((i) => t(`notifyCfg.wecomStep${i}`)))
const wecomRobotSteps = computed(() => [1, 2, 3].map((i) => t(`notifyCfg.wecomRStep${i}`)))
const nginxSnippet = `location ^~ /cgi-bin/gettoken       { proxy_pass https://qyapi.weixin.qq.com; }
location ^~ /cgi-bin/message/send   { proxy_pass https://qyapi.weixin.qq.com; }
location ^~ /cgi-bin/agent/get      { proxy_pass https://qyapi.weixin.qq.com; }`
const socatSnippet = `services:
  wxproxy:
    image: alpine/socat
    command: TCP-LISTEN:9090,fork,reuseaddr TCP:qyapi.weixin.qq.com:443
    ports: ["8543:9090"]
    restart: always`

const tabs = [
  { key: 'telegram', label: 'Telegram Bot' }, { key: 'feishu', label: '飞书 Bot' },
  { key: 'qq', label: 'QQ Bot' }, { key: 'bark', label: 'Bark' }, { key: 'email', label: 'Email' },
  { key: 'pushplus', label: 'Pushplus' }, { key: 'serverchan', label: 'Server酱' },
  { key: 'wecom', label: '企业微信' }, { key: 'dingtalk', label: '钉钉' },
  { key: 'discord', label: 'Discord' }, { key: 'slack', label: 'Slack' },
  { key: 'ntfy', label: 'ntfy' }, { key: 'gotify', label: 'Gotify' },
  { key: 'webhook', label: 'Webhook' }
]
const enableLabels = {
  telegram: '启用 Telegram 机器人', feishu: '启用飞书机器人', qq: '启用 QQ 机器人',
  bark: '启用 Bark 推送', email: '启用 Email 推送', pushplus: '启用 Pushplus 推送',
  serverchan: '启用 Server酱', wecom: '启用企业微信通知', dingtalk: '启用钉钉机器人',
  discord: '启用 Discord', slack: '启用 Slack', ntfy: '启用 ntfy', gotify: '启用 Gotify',
  webhook: '启用 Webhook 推送'
}
const enableLabel = computed(() => enableLabels[tab.value])

// 客户端默认结构：与后端保持一致，防止某渠道/字段缺失导致模板访问 undefined（webhook 空白根因防御）
function defaults() {
  return {
    telegram: { enabled: false, bot_token: '', chat_id: '', admin_id: '', api_base: '', proxy: '' },
    feishu: { enabled: false, app_id: '', app_secret: '', chat_ids: '' },
    qq: { enabled: false, app_id: '', app_secret: '', group_ids: '', user_ids: '' },
    bark: { enabled: false, urls: [], group: '', level: 'active', icon: '' },
    email: { enabled: false, host: '', port: 465, ssl: true, username: '', password: '', from: '', to: '' },
    pushplus: { enabled: false, token: '', topic: '', channel: 'wechat' },
    serverchan: { enabled: false, sendkey: '' },
    wecom: {
      enabled: false, mode: 'webhook', url: '',
      corp_id: '', agent_id: '', secret: '', proxy_base: '',
      to_user: '@all', to_party: '', to_tag: '', msg_type: 'text', card_url: ''
    },
    dingtalk: { enabled: false, url: '', secret: '' },
    discord: { enabled: false, url: '' },
    slack: { enabled: false, url: '' },
    ntfy: { enabled: false, server: 'https://ntfy.sh', topic: '', token: '' },
    gotify: { enabled: false, server: '', token: '', priority: 5 },
    webhook: { enabled: false, urls: [], secret: '', headers: [], template: '', timeout_ms: 5000, max_retries: 3 }
  }
}

function flash(good, text) { ok.value = good; msg.value = text; setTimeout(() => (msg.value = ''), 4000) }

async function load() {
  const base = defaults()
  try {
    const { data } = await api.get('/api/notifications/config')
    const got = data.config || {}
    for (const k of Object.keys(base)) {
      if (got[k] && typeof got[k] === 'object') Object.assign(base[k], got[k])
      // 数组字段确保是数组，避免 v-for over null
      if (!Array.isArray(base[k].urls) && 'urls' in base[k]) base[k].urls = []
      if (k === 'webhook' && !Array.isArray(base[k].headers)) base[k].headers = []
    }
  } catch { /* 用默认值 */ }
  cfg.value = base
  loaded.value = true
}

async function save() {
  saving.value = true
  try {
    await api.put('/api/notifications/config', { config: cfg.value })
    flash(true, t('notifyCfg.saved'))
  } catch (e) { flash(false, e.response?.data?.detail || 'Error') } finally { saving.value = false }
}

async function test(channel) {
  testing.value = true; msg.value = ''
  try {
    await api.post('/api/notifications/test', { channel, config: cfg.value[channel] })
    flash(true, t('notifyCfg.testOk'))
  } catch (e) { flash(false, e.response?.data?.detail || 'Error') } finally { testing.value = false }
}

async function wecomCheck() {
  checking.value = true; msg.value = ''
  try {
    const { data } = await api.post('/api/notifications/wecom/check', { config: cfg.value.wecom })
    const a = data.agent || {}
    flash(true, `${t('notifyCfg.wecomCheckOk')}「${a.name}」· AgentId ${a.agentid} · ${t('notifyCfg.wecomScope')}: ${a.users} / ${a.parties} / ${a.tags}`)
  } catch (e) { flash(false, e.response?.data?.detail || 'Error') } finally { checking.value = false }
}

async function tgAction(kind) {
  msg.value = ''
  try {
    await api.put('/api/notifications/config', { config: cfg.value })
    if (kind === 'me') {
      const { data } = await api.get('/api/notifications/telegram/me')
      flash(true, `${t('settings.botOk')}: @${data.result?.username}`)
    } else {
      const { data } = await api.get('/api/notifications/telegram/updates')
      const ids = (data.result || []).map((u) => u.message?.chat?.id).filter(Boolean)
      if (ids.length) { cfg.value.telegram.chat_id = String(ids[ids.length - 1]); flash(true, 'Chat IDs: ' + [...new Set(ids)].join(', ')) }
      else flash(false, 'No messages yet')
    }
  } catch (e) { flash(false, e.response?.data?.detail || 'Error') }
}

onMounted(load)
</script>

<style scoped>
.notify h3 { margin: 0; }
.nc-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.nc-head .btn { width: auto; }
.tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; padding: 6px; background: var(--surface-2); border-radius: 12px; }
.tab { border: none; background: transparent; padding: 7px 13px; border-radius: 9px; cursor: pointer; font-size: 13px;
  color: var(--text-soft); display: inline-flex; align-items: center; gap: 6px; }
.tab.on { background: var(--surface); color: var(--primary); font-weight: 600; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.on-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--success); }
.ch-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.ch-head h4 { margin: 0; font-size: 16px; }
.ch-actions { display: flex; align-items: center; gap: 12px; }
.fields { display: flex; flex-direction: column; gap: 13px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 13px; }
.three { display: grid; grid-template-columns: 1fr 1fr auto; gap: 13px; align-items: end; }
.f { display: flex; flex-direction: column; gap: 5px; }
.f.sw { align-items: flex-start; }
.f label { font-size: 12px; font-weight: 600; color: var(--text-soft); letter-spacing: .03em; }
.f-h { display: flex; justify-content: space-between; align-items: center; }
.f small { font-size: 12px; }
.empty { border: 1px dashed var(--border); border-radius: 10px; padding: 12px; text-align: center; color: var(--text-soft); font-size: 13px; margin: 0; }
.list-row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
.list-row input { flex: 1; }
.x { background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; width: 34px; height: 34px; cursor: pointer; color: var(--danger); flex-shrink: 0; }
.btn.sm { width: auto; padding: 7px 12px; font-size: 13px; }
.btn.xs { width: auto; padding: 4px 10px; font-size: 12px; }
.row { display: flex; flex-wrap: wrap; gap: 8px; }
.switch { display: inline-flex; align-items: center; cursor: pointer; }
.switch input { display: none; }
.switch .track { width: 42px; height: 24px; border-radius: 12px; background: var(--border); position: relative; transition: background .2s; }
.switch .track::after { content: ''; position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%; background: #fff; transition: transform .2s; }
.switch input:checked + .track { background: var(--primary); }
.switch input:checked + .track::after { transform: translateX(18px); }
.ok { color: var(--success); font-size: 13px; }
.err { color: var(--danger); font-size: 13px; word-break: break-all; }
/* 企业微信：模式切换 + 配置说明 */
.three-e { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 13px; }
.seg { display: flex; gap: 6px; padding: 5px; background: var(--surface-2); border-radius: 11px; }
.seg-b { flex: 1; border: none; background: transparent; padding: 9px 12px; border-radius: 8px;
  cursor: pointer; font-size: 13px; color: var(--text-soft); transition: all .18s; }
.seg-b:hover { color: var(--primary); }
.seg-b.on { background: var(--surface); color: var(--primary); font-weight: 600; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.help { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--surface-2); }
.help-h { width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 8px;
  border: none; background: transparent; padding: 11px 14px; cursor: pointer; font-size: 13px;
  font-weight: 600; color: var(--text-soft); }
.help-b { padding: 0 14px 14px; font-size: 12.5px; line-height: 1.75; color: var(--text-soft); }
.help-b ol { margin: 0 0 10px; padding-left: 20px; }
.help-b li { margin-bottom: 5px; }
.help-b :deep(b) { color: var(--text); }
.help-b .warn { margin: 0 0 10px; padding: 9px 11px; border-radius: 9px;
  background: color-mix(in srgb, var(--warning, #f59e0b) 12%, transparent);
  border-left: 3px solid var(--warning, #f59e0b); color: var(--text); }
.help-b details { margin-bottom: 8px; }
.help-b summary { cursor: pointer; color: var(--primary); user-select: none; }
.help-b pre { margin: 8px 0; padding: 10px 12px; border-radius: 9px; background: var(--surface);
  border: 1px solid var(--border); overflow-x: auto; font-size: 11.5px; line-height: 1.6;
  white-space: pre; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.help-b p { margin: 6px 0 0; }
@media (max-width: 720px) {
  .two, .three, .three-e { grid-template-columns: 1fr; }
  .seg { flex-direction: column; }
}
</style>
