<!--
  渲染错误兜底：Vue 里子组件渲染抛异常会导致整棵子树被卸载，页面上表现为「某一栏整块消失」，
  用户完全看不出发生了什么（debug13 的 Webhook、debug16 的企业微信自建应用都是这个现象）。
  包一层边界后，出错的只是这一个面板，且会把错误信息显示出来便于反馈，页面其余部分照常可用。
-->
<template>
  <div v-if="err" class="card sect eb">
    <h3>⚠️ {{ t('eb.title') }}</h3>
    <p class="eb-tip">{{ t('eb.tip') }}</p>
    <pre>{{ err }}</pre>
    <p class="muted eb-contact">TG:@Aiden_SU · E-mail:aidensu8182@gmail.com</p>
  </div>
  <slot v-else />
</template>

<script setup>
import { onErrorCaptured, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const err = ref('')

onErrorCaptured((e) => {
  err.value = String(e?.message || e)
  console.error('[EasySub] 面板渲染失败：', e)
  return false // 不再向上冒泡，保住页面其余部分
})
</script>

<style scoped>
.eb { border-left: 3px solid var(--danger); }
.eb h3 { margin: 0 0 8px; font-size: 16px; }
.eb-tip { margin: 0 0 10px; font-size: 13px; color: var(--text-soft); line-height: 1.7; }
.eb pre { margin: 0; padding: 10px 12px; border-radius: 9px; background: var(--surface-2);
  border: 1px solid var(--border); overflow-x: auto; font-size: 12px; white-space: pre-wrap;
  word-break: break-word; color: var(--danger); }
.eb-contact { margin: 10px 0 0; font-size: 12px; }
</style>
