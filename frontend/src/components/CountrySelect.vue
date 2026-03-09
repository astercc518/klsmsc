<template>
  <el-select
    v-model="selected"
    :placeholder="placeholder"
    :disabled="disabled"
    filterable
    :filter-method="handleFilter"
    clearable
    style="width: 100%"
    @clear="handleClear"
  >
    <el-option
      v-if="showAllOption"
      value="*"
      label="全部国家 (*)"
    >
      <span>全部国家 (*)</span>
    </el-option>
    <el-option
      v-for="c in filtered"
      :key="c.iso"
      :value="c.iso"
      :label="`${c.name} (+${c.dial})`"
    >
      <span style="float: left">{{ c.name }}</span>
      <span style="float: right; color: var(--el-text-color-secondary); font-size: 12px; margin-left: 12px">
        +{{ c.dial }} ({{ c.iso }})
      </span>
    </el-option>
  </el-select>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { COUNTRY_LIST, searchCountries, type CountryItem } from '@/constants/countries'

const props = withDefaults(defineProps<{
  modelValue?: string
  placeholder?: string
  showAllOption?: boolean
  disabled?: boolean
}>(), {
  modelValue: '',
  placeholder: '搜索国家 (名称/国码)',
  showAllOption: false,
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const query = ref('')
const filtered = ref<CountryItem[]>(COUNTRY_LIST)

const selected = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val || ''),
})

function handleFilter(q: string) {
  query.value = q
  filtered.value = q ? searchCountries(q) : COUNTRY_LIST
}

function handleClear() {
  query.value = ''
  filtered.value = COUNTRY_LIST
}

watch(() => props.modelValue, () => {
  if (!props.modelValue) {
    filtered.value = COUNTRY_LIST
  }
})
</script>
