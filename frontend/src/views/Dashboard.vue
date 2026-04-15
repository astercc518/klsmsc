<template>

  <div class="dashboard-wrapper">
    <div v-if="loading" class="empty-state">{{ $t('common.loading') }}</div>
    <template v-else>
      <AdminDashboard v-if="isStaff" />
      <CustomerDashboard v-else />
    </template>
  </div>

</template>

<script setup lang='ts'>

import { ref, onMounted } from 'vue'
import AdminDashboard from './dashboard/AdminDashboard.vue'
import CustomerDashboard from './dashboard/CustomerDashboard.vue'

const loading = ref(true)
const isStaff = ref(false)

onMounted(() => {
    const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1'
    const adminToken = localStorage.getItem('admin_token')
    if (!isImpersonateMode && adminToken) {
        isStaff.value = true
    } else {
        isStaff.value = false
    }
    loading.value = false
})

</script>

<style scoped>
.dashboard-wrapper { min-height: 100%; }
.empty-state { padding: 40px; text-align: center; }
</style>