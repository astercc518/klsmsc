<template>
  <div class="tg-bot-panel">
    <el-tabs v-model="activeSub" class="tg-sub-tabs">
      <el-tab-pane :label="$t('menu.botConfig')" name="config" lazy>
        <BotConfig />
      </el-tab-pane>
      <el-tab-pane :label="$t('menu.botMessages')" name="messages" lazy>
        <BotMessages />
      </el-tab-pane>
      <el-tab-pane :label="$t('menu.invitations')" name="invites" lazy>
        <BotInvites />
      </el-tab-pane>
      <el-tab-pane :label="$t('menu.templateWhitelist')" name="templates" lazy>
        <BotTemplates />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import BotConfig from '@/views/bot/Config.vue'
import BotMessages from '@/views/bot/Messages.vue'
import BotInvites from '@/views/bot/Invites.vue'
import BotTemplates from '@/views/bot/Templates.vue'

const route = useRoute()
const validSubs = ['config', 'messages', 'invites', 'templates']
const initialSub = String(route.query.sub || '')
const activeSub = ref(validSubs.includes(initialSub) ? initialSub : 'config')
</script>

<style scoped>
.tg-bot-panel {
  width: 100%;
}
.tg-sub-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}
.tg-sub-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}
</style>
