<template>
  <div class="send-page">
    <!-- 发送统计 -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-icon today">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M18 2L9 11M18 2L12 18L9 11L2 8L18 2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.today_sent }}</span>
          <span class="stat-label">{{ $t('smsSend.todaySent') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon success">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M16 6L8 14L4 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.today_success }}</span>
          <span class="stat-label">{{ $t('smsSend.successDelivered') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon rate">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M2 16H18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M4 16V10M8 16V6M12 16V8M16 16V4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.success_rate }}%</span>
          <el-tooltip :content="$t('smsSend.successRateTooltip')" placement="top" :show-after="400">
            <span class="stat-label stat-label-hint">{{ $t('smsSend.successRate') }}</span>
          </el-tooltip>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon cost">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5"/>
            <path d="M10 5V15M7 8H13M7 12H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.today_cost }}</span>
          <span class="stat-label">{{ $t('smsSend.todayCost') }}</span>
        </div>
      </div>
    </div>

    <div class="page-grid">
      <!-- 左侧：发送表单 -->
      <div class="form-panel">
        <div class="panel-header">
          <h1 class="panel-title">{{ $t('smsSend.title') }}</h1>
          <p class="panel-desc">{{ $t('smsSend.pageDesc') }}</p>
        </div>
        
        <div class="form-body">
          <el-form ref="formRef" :model="form" label-position="top">
            
            <!-- 1. 短信内容 -->
            <div class="field-group">
              <label class="field-label required">{{ $t('smsSend.message') }}：</label>

              <!-- 变量插入工具栏 -->
              <div class="var-toolbar">
                <div class="var-toolbar-left">
                  <span class="toolbar-tip">变量:</span>
                  <el-tooltip v-for="v in MAIN_VARS" :key="v.tag" :content="v.tip" placement="top" :show-after="400">
                    <el-button size="small" @click="insertVariable(v.tag)">{{ v.label }}</el-button>
                  </el-tooltip>
                  <el-dropdown trigger="click" @command="insertVariable">
                    <el-button size="small">更多 ▾</el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item v-for="v in MORE_VARS" :key="v.tag" :command="v.tag">
                          {{ v.label }} <span style="color:var(--el-text-color-placeholder);font-size:11px;margin-left:6px">{{ v.tip }}</span>
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                  <el-divider v-if="customVars.length" direction="vertical" />
                  <el-button v-for="cv in customVars" :key="cv.name" size="small" type="warning" @click="insertVariable(`{${cv.name}}`)">{{ cv.name }}</el-button>
                  <el-button size="small" type="info" plain @click="openCustomVarDialog">+ 自定义</el-button>
                </div>
                <div class="var-toolbar-right">
                  <el-button size="small" type="warning" plain @click="showShortLinkDialog = true">
                    <el-icon><Link /></el-icon> 短链转换
                  </el-button>
                  <el-button v-if="aiEnabled" size="small" type="primary" @click="showAiDialog = true">
                    <el-icon><MagicStick /></el-icon> AI 生成
                  </el-button>
                </div>
              </div>

              <el-input
                ref="msgInputRef"
                v-model="form.message"
                type="textarea"
                :rows="5"
                :placeholder="$t('smsSend.enterContent')"
                maxlength="1000"
                class="custom-textarea"
                @focus="saveCursorPos"
                @click="saveCursorPos"
                @keyup="saveCursorPos"
              />

              <!-- 字符计数 & 敏感词提示 -->
              <div class="msg-meta-bar">
                <span
                  class="char-counter"
                  :class="{ 'over-limit': messageSegmentUnits > singleSegmentCharLimit }"
                >
                  {{ messageSmsLen }} 字符
                  <template v-if="messageSegmentUnits > singleSegmentCharLimit">
                    （超过 {{ singleSegmentCharLimit }} 字符可能被拆分为多条）
                  </template>
                </span>
                <div v-if="hasSensitiveWord" class="banned-word-warn">
                  <span class="bw-icon">⚠</span>
                  <span>检测到违禁词：</span>
                  <span v-for="(w, i) in matchedBannedWords" :key="w">
                    <span class="bw-highlight">{{ w }}</span><span v-if="i < matchedBannedWords.length - 1">、</span>
                  </span>
                  <span class="bw-hint">（建议修改后再发送，含违禁词可能被运营商拦截）</span>
                </div>
              </div>

              <!-- 变量预览 -->
              <div v-if="hasVariables" class="var-preview">
                <span class="preview-tag">预览效果{{ hasMultiValueVars ? '（第1条）' : '' }}:</span>
                <div class="preview-msg">{{ previewSms }}</div>
                <div v-if="hasMultiValueVars" class="preview-multi-hint">多值变量：每个号码将收到不同的值</div>
              </div>

              <!-- 多文案提示 -->
              <div v-if="multiMessages.length > 1" class="multi-msg-banner">
                <div class="mmb-header">
                  <span>已加载 <strong>{{ multiMessages.length }}</strong> 条文案，发送时均匀分配号码</span>
                  <div class="mmb-actions">
                    <el-button link type="primary" size="small" :icon="CopyDocument" @click="copyAll(multiMessages)">复制全部</el-button>
                    <el-button link type="primary" size="small" :loading="multiZhLoading" @click="translateMulti">翻译中文</el-button>
                    <el-button link type="danger" size="small" @click="multiMessages = []">清除多文案</el-button>
                  </div>
                </div>
                <div class="mmb-list">
                  <div v-for="(msg, idx) in multiMessages" :key="idx" class="mmb-item" :class="{ current: idx === 0 }">
                    <span class="mmb-idx">{{ idx + 1 }}</span>
                    <div class="mmb-body">
                      <span class="mmb-text">{{ msg }}</span>
                      <span v-if="multiMessagesZh[idx]" class="mmb-zh">中文：{{ multiMessagesZh[idx] }}</span>
                    </div>
                    <span class="mmb-char-count">{{ msg.length }}字符</span>
                    <el-button class="mmb-copy-btn" link size="small" :icon="CopyDocument" title="复制此条" @click.stop="copyText(msg)" />
                  </div>
                </div>
              </div>

              <div class="field-toolbar">
                <div class="stats-info">
                  {{ $t('smsSend.totalChars') }} <span class="highlight">{{ messageSmsLen }}</span> {{ $t('smsSend.chars') }}，
                  {{ $t('smsSend.encoding') }}：<span class="highlight">{{ messageEncoding }}</span>，
                  {{ $t('smsSend.billingUnits') }}：<span class="highlight">{{ messageSegmentUnits }}</span> {{ messageUnitLabel }}，
                  {{ $t('smsSend.standardEstimatedParts') }}：<span class="highlight">{{ estimatedParts }}</span> {{ $t('smsSend.parts') }}
                </div>
                <div class="toolbar-actions">
                  <el-button link type="primary" size="small" @click="handleSelectDraft">{{ $t('smsSend.loadDraft') }}</el-button>
                  <el-button link type="primary" size="small" @click="handleSaveDraft">{{ $t('smsSend.saveDraft') }}</el-button>
                  <el-button link type="primary" size="small" @click="handlePreview">{{ $t('smsSend.preview') }}</el-button>
                </div>
              </div>
            </div>

            <!-- 2. 号码来源切换 -->
            <div class="field-group">
              <label class="field-label required">{{ $t('smsSend.recipients') }}:</label>
              <div class="source-tabs">
                <div class="source-tab" :class="{ active: numberSource === 'manual' }" @click="numberSource = 'manual'">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M2 3H14V13H2V3Z" stroke="currentColor" stroke-width="1.2"/>
                    <path d="M5 6H11M5 8H9" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
                  </svg>
                  手动输入号码
                </div>
                <div v-if="hasDataService" class="source-tab" :class="{ active: numberSource === 'store' }" @click="numberSource = 'store'">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M2 5L4 2H12L14 5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                    <rect x="2" y="5" width="12" height="9" rx="1" stroke="currentColor" stroke-width="1.2"/>
                    <path d="M6 8H10" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
                  </svg>
                  从数据商店购买发送
                </div>
                <div class="source-tab" :class="{ active: numberSource === 'private' }" @click="numberSource = 'private'">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M4 2V14M12 2V14M2 14H14" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
                    <rect x="4" y="4" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/>
                  </svg>
                  从私有库载入
                </div>
              </div>

              <!-- 私有库模式 -->
              <template v-if="numberSource === 'private'">
                <el-alert
                  type="info"
                  :closable="false"
                  show-icon
                  style="margin-bottom: 12px"
                >
                  {{ $t('smsSend.privateLibraryHint') }}
                </el-alert>
                <div class="store-section">
                  <div class="carrier-filter" style="margin-bottom: 16px;">
                    <label class="carrier-label">运营商 / 数据状态筛选:</label>
                    <div class="carrier-tags" style="display: flex; flex-direction: column; gap: 10px;">
                      <div class="tag-row" style="display: flex; flex-wrap: wrap; gap: 6px;">
                        <span
                          class="carrier-tag"
                          :class="{ active: !carrierFilterPrivate }"
                          @click="carrierFilterPrivate = ''"
                        >全部运营商</span>
                        <span
                          v-for="c in availableCarriersPrivate"
                          :key="c.name"
                          class="carrier-tag"
                          :class="{ active: carrierFilterPrivate === c.name }"
                          @click="carrierFilterPrivate = c.name"
                        >
                          {{ c.name }}
                          <span class="carrier-count">{{ formatCount(c.count) }}</span>
                        </span>
                      </div>
                      <div class="status-row">
                        <el-checkbox v-model="unusedOnlyPrivate" size="large">
                          <span style="color: var(--el-color-primary); font-weight: bold; font-size: 14px;">仅限未使用号码 (Fresh Data Only)</span>
                        </el-checkbox>
                      </div>
                    </div>
                  </div>
                  <div class="store-products" v-loading="loadingPrivate" style="max-height: 200px; overflow-y: auto;">
                    <div
                      v-for="(group, idx) in filteredPrivateGroups"
                      :key="idx"
                      class="store-product-item"
                      :class="{ selected: selectedPrivateGroup === group }"
                      @click="selectedPrivateGroup = group"
                    >
                      <div class="sp-info">
                        <div class="sp-name" :title="getGroupName(group)">
                          {{ getGroupName(group) }}
                        </div>
                        <div class="sp-meta">
                          库存: {{ privateEffectiveStock(group).toLocaleString() }}
                          · $0.00/条
                          <span v-if="carrierFilterPrivate" class="sp-carrier-badge">{{ carrierFilterPrivate }}</span>
                          <el-tag v-if="group.library_origin" size="small" type="info" effect="plain" style="margin-left: 6px">{{ privateLibraryOriginLabel(group.library_origin) }}</el-tag>
                          <el-tag v-if="unusedOnlyPrivate" size="small" type="success" effect="dark" style="margin-left: 8px">仅未使用</el-tag>
                        </div>
                      </div>
                      <div class="sp-check" v-if="selectedPrivateGroup === group">✓</div>
                    </div>
                    <el-empty v-if="filteredPrivateGroups.length === 0 && !loadingPrivate" description="该筛选条件下暂无数据" :image-size="40" />
                  </div>

                  <div v-if="selectedPrivateGroup" class="store-quantity">
                    <label>发送数量:</label>
                    <el-input-number
                      v-model="privateQuantity"
                      :min="privateStockMax > 0 ? 1 : 0"
                      :max="Math.max(0, privateStockMax)"
                      :step="100"
                      style="width: 200px"
                    />
                    <span class="store-cost">
                      费用: 数据 ${{ formatUsdEstimate(privateDataCost) }} + 短信 ${{ formatUsdEstimate(privateSmsCost) }}
                      = 合计 <strong>${{ privateCostStr }}</strong>
                      <span style="margin-left: 12px; font-size: 13px; color: var(--text-tertiary); font-weight: normal;">
                        (可用库存: {{ privateEffectiveStock(selectedPrivateGroup).toLocaleString() }})
                      </span>
                    </span>
                  </div>

                  <div class="store-footer" v-if="selectedPrivateGroup">
                    <div class="store-summary">
                      费用: 数据 ${{ formatUsdEstimate(privateDataCost) }} + 短信 ${{ formatUsdEstimate(privateSmsCost) }}
                      = 合计 <span class="total-price">${{ privateCostStr }}</span>
                    </div>
                  </div>
                </div>
              </template>

              <!-- 手动输入模式 -->
              <template v-if="numberSource === 'manual'">
                <el-input
                  v-model="form.phone_numbers_text"
                  type="textarea"
                  :rows="6"
                  :placeholder="$t('smsSend.numbersPlaceholder')"
                  class="custom-textarea"
                />
                <div class="field-toolbar">
                  <div class="stats-info">
                    {{ $t('smsSend.totalNumbers') }}: <span class="highlight">{{ numberCount }}</span>,
                    {{ $t('smsSend.estimatedCost') }}: <span class="highlight">{{ totalEstimatedSegments }}</span>
                  </div>
                </div>
                <div class="number-actions">
                  <div class="action-group">
                    <el-button link size="small" @click="filterNumbers('duplicate')">{{ $t('smsSend.filterDuplicate') }}</el-button>
                    <el-button link size="small" @click="filterNumbers('invalid')">{{ $t('smsSend.filterInvalid') }}</el-button>
                    <el-button link size="small" @click="filterNumbers('empty')">{{ $t('smsSend.filterEmpty') }}</el-button>
                  </div>
                  <div class="action-group">
                    <el-button link type="primary" size="small" @click="importFile('txt')">{{ $t('smsSend.importTxt') }}</el-button>
                    <el-button link type="primary" size="small" @click="importFile('excel')">{{ $t('smsSend.importExcel') }}</el-button>
                    <el-button link type="warning" size="small" @click="checkEmpty">{{ $t('smsSend.checkEmpty') }}</el-button>
                  </div>
                </div>
              </template>

              <!-- 数据商店模式 -->
              <template v-if="numberSource === 'store'">
                <div class="store-section">
                  <!-- 运营商筛选 -->
                  <div class="carrier-filter">
                    <label class="carrier-label">运营商筛选:</label>
                    <div class="carrier-tags">
                      <span
                        class="carrier-tag"
                        :class="{ active: !selectedCarrier }"
                        @click="selectCarrier('')"
                      >全部</span>
                      <span
                        v-for="c in carrierList"
                        :key="c.name"
                        class="carrier-tag"
                        :class="{ active: selectedCarrier === c.name }"
                        @click="selectCarrier(c.name)"
                      >
                        {{ c.name }}
                        <span class="carrier-count">{{ formatCount(c.count) }}</span>
                      </span>
                    </div>
                  </div>

                  <div class="store-products" v-loading="loadingProducts">
                    <div
                      v-for="product in storeProducts"
                      :key="product.id"
                      class="store-product-item"
                      :class="{ selected: selectedProduct?.id === product.id }"
                      @click="selectProduct(product)"
                    >
                      <div class="sp-info">
                        <div class="sp-name">{{ product.product_name }}</div>
                        <div class="sp-meta">
                          库存: {{ product.stock_count?.toLocaleString() }} · ${{ product.price_per_number }}/条
                          <span v-if="selectedCarrier" class="sp-carrier-badge">{{ selectedCarrier }}</span>
                          <span v-if="product.rating?.avg > 0" class="sp-rating-badge">
                            ★{{ product.rating.avg }}
                            <span v-if="product.rating.recent_avg > 0" class="sp-rating-recent">近期{{ product.rating.recent_avg }}</span>
                          </span>
                        </div>
                      </div>
                      <div class="sp-check" v-if="selectedProduct?.id === product.id">✓</div>
                    </div>
                    <el-empty v-if="storeProducts.length === 0 && !loadingProducts" description="暂无可用数据包" :image-size="60" />
                  </div>

                  <div v-if="selectedProduct" class="store-quantity">
                    <label>购买数量:</label>
                    <el-input-number
                      v-model="storeQuantity"
                      :min="selectedProduct.min_purchase || 100"
                      :max="Math.min(selectedProduct.max_purchase || 100000, selectedProduct.stock_count || 100000)"
                      :step="100"
                      style="width: 200px"
                    />
                    <span class="store-cost">
                      费用: 数据 ${{ formatUsdEstimate(storeDataCost) }}
                      <template v-if="storeSmsCost > 0"> + 短信 ${{ formatUsdEstimate(storeSmsCost) }}</template>
                      = 合计 <strong>${{ storeCost }}</strong>
                    </span>
                  </div>
                </div>
              </template>
            </div>
            
            <!-- 3. 发送选项 -->
            <div class="options-row">
              <div class="field-group">
                <label class="field-label">
                  {{ $t('smsSend.senderId') }}
                  <span class="optional">{{ $t('common.optional') }}</span>
                </label>
                <!-- 该通道+目的国家已配置可选 SID 时显示下拉；否则回退自由输入 -->
                <el-select
                  v-if="availableSids.length > 0"
                  v-model="form.sender_id"
                  :placeholder="$t('smsSend.senderIdPlaceholder')"
                  size="default"
                  class="custom-select"
                  clearable
                >
                  <el-option
                    v-for="s in availableSids"
                    :key="s.sender_id"
                    :value="s.sender_id"
                    :label="s.is_default ? (s.sender_id + ' (默认)') : s.sender_id"
                  />
                </el-select>
                <el-input
                  v-else
                  v-model="form.sender_id"
                  :placeholder="$t('smsSend.senderIdPlaceholder')"
                  size="default"
                  class="custom-input"
                />
              </div>
              <!-- 通道选择：仅账户绑定 2+ 条通道时展示 -->
              <div v-if="channelBound && channels.length > 1" class="field-group">
                <label class="field-label">
                  {{ $t('smsSend.channel') }}
                </label>
                <el-select
                  v-model="form.channel_id"
                  :placeholder="$t('smsSend.channelPlaceholder')"
                  size="default"
                  class="custom-select"
                  popper-class="channel-popper"
                  clearable
                >
                  <el-option
                    v-for="ch in channels"
                    :key="ch.id"
                    :value="ch.id"
                    :label="ch.code"
                  />
                </el-select>
              </div>
            </div>

            <!-- 4. 其他选项 -->
            <div class="checkbox-options">
              <el-checkbox v-if="numberSource === 'manual'" v-model="form.resetOnlyNumbers">
                {{ $t('smsSend.resetNumbersOnly') }}
              </el-checkbox>
              
              <el-checkbox v-model="form.isScheduled">
                {{ $t('smsSend.scheduleSend') }}
              </el-checkbox>

              <div v-if="form.isScheduled" class="schedule-picker">
                <el-date-picker
                  v-model="form.scheduledTime"
                  type="datetime"
                  :placeholder="$t('smsSend.selectTime')"
                  size="small"
                  format="YYYY-MM-DD HH:mm"
                  value-format="YYYY-MM-DD HH:mm:ss"
                />
              </div>
            </div>

            <!-- 5. 操作按钮 -->
            <div class="form-footer">
              <button type="button" class="btn-reset" @click="handleReset">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M2 8C2 4.68629 4.68629 2 8 2C10.5 2 12.5 3.5 13.5 5.5M14 8C14 11.3137 11.3137 14 8 14C5.5 14 3.5 12.5 2.5 10.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                {{ $t('common.reset') }}
              </button>

              <!-- 手动模式发送按钮 -->
              <button v-if="numberSource === 'manual'" type="button" class="btn-send" :disabled="loading || !form.phone_numbers_text || !form.message" @click="handleSend">
                <template v-if="!loading">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M14 2L7 9M14 2L9.5 14L7 9L2 6.5L14 2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                  </svg>
                  {{ numberCount > 1 ? $t('smsSend.batchSend') + ` (${numberCount})` : $t('smsSend.sendNow') }}
                </template>
                <template v-else>
                  <svg class="spinner" width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5" stroke-dasharray="30" stroke-dashoffset="8" stroke-linecap="round"/>
                  </svg>
                  {{ $t('smsSend.sending') }}... ({{ sendProgress }}/{{ numberCount }})
                </template>
              </button>
              <!-- 仅需文案即可提交审核（填一个号码时会一并带给后端） -->
              <button
                v-if="numberSource === 'manual'"
                type="button"
                class="btn-audit"
                :disabled="loading || !form.message || approvalSubmitting"
                @click="handleSubmitApproval"
              >
                <template v-if="!approvalSubmitting">📋 {{ $t('smsApprovalsPage.submitAudit') }}</template>
                <template v-else>{{ $t('smsApprovalsPage.submitting') }}</template>
              </button>

              <!-- 私有库发送按钮 -->
              <button 
                v-if="numberSource === 'private'" 
                type="button" 
                class="btn-send" 
                :disabled="privateSending || !selectedPrivateGroup || !form.message || privateStockMax < 1 || privateQuantity < 1"
                @click="handlePrivateSend"
              >
                <template v-if="!privateSending">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M14 2L7 9M14 2L9.5 14L7 9L2 6.5L14 2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                  </svg>
                  发送 {{ privateQuantity }} 条（私有库）
                </template>
                <template v-else>
                  <svg class="spinner" width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5" stroke-dasharray="30" stroke-dashoffset="8" stroke-linecap="round"/>
                  </svg>
                  正在创建任务...
                </template>
              </button>

              <!-- 商店模式发送按钮 -->
              <button v-if="numberSource === 'store'" type="button" class="btn-send" :disabled="storeSending || !selectedProduct || !form.message" @click="handleStoreSend">
                <template v-if="!storeSending">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M14 2L7 9M14 2L9.5 14L7 9L2 6.5L14 2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                  </svg>
                  购买 {{ storeQuantity }} 条并发送
                </template>
                <template v-else>
                  <svg class="spinner" width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5" stroke-dasharray="30" stroke-dashoffset="8" stroke-linecap="round"/>
                  </svg>
                  发送中...
                </template>
              </button>
            </div>

            <!-- 大批量异步进度 -->
            <div v-if="asyncBatchPolling" class="async-batch-progress">
              <div class="async-batch-header">
                <span>批次 #{{ asyncBatchPolling.batchId }} 后台处理中</span>
                <span class="async-batch-pct">{{ asyncBatchProgress }}%</span>
              </div>
              <el-progress :percentage="asyncBatchProgress" :stroke-width="8" :show-text="false"
                :status="asyncBatchStatus === 'completed' ? 'success' : asyncBatchStatus === 'failed' ? 'exception' : ''" />
              <div class="async-batch-tip">共 {{ asyncBatchPolling.total.toLocaleString() }} 条，可关闭页面，在「发送任务」页查看进度</div>
            </div>

            <!-- 发送结果 -->
            <transition name="slide">
              <div class="result-banner" v-if="result" :class="result.success ? 'success' : 'error'">
                <div class="result-icon">
                  <svg v-if="result.success" width="18" height="18" viewBox="0 0 18 18" fill="none">
                    <path d="M5 9L8 12L13 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                  <svg v-else width="18" height="18" viewBox="0 0 18 18" fill="none">
                    <path d="M12 6L6 12M6 6L12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>
                </div>
                <div class="result-text">
                  <strong class="result-title">{{ result.success ? $t('smsSend.sendComplete') : $t('smsSend.sendFailed') }}</strong>
                  <div class="result-meta">
                    <template v-if="result.success && result.successCount != null">
                      <span>{{ $t('common.success') }}: {{ result.successCount }}, {{ $t('common.failed') }}: {{ result.failCount }}</span>
                      <span v-if="result.batchId != null" class="result-task-wrap">
                        · <router-link class="result-task-link" to="/sms/tasks">{{ $t('smsSend.viewSendTask') }} #{{ result.batchId }}</router-link>
                      </span>
                    </template>
                    <template v-else-if="result.total != null && (result.succeeded != null || result.failed != null)">
                      <span>共 {{ result.total }} 条 · 成功 {{ result.succeeded ?? 0 }} · 失败 {{ result.failed ?? 0 }}</span>
                      <span v-if="result.batch_id != null" class="result-task-wrap">
                        · <router-link class="result-task-link" to="/sms/tasks">{{ $t('smsSend.viewSendTask') }} #{{ result.batch_id }}</router-link>
                      </span>
                    </template>
                    <span v-else-if="result.success && result.message">{{ result.message }}</span>
                    <span v-else-if="!result.success">{{ result.error?.message || result.message }}</span>
                  </div>

                  <!-- 失败原因汇总：当存在 messages 明细且有失败项时按原因分组展示 -->
                  <div v-if="failureSummary.length > 0" class="failure-summary">
                    <div class="failure-summary-title">失败原因汇总</div>
                    <div v-for="grp in failureSummary" :key="grp.code" class="failure-group">
                      <div class="failure-group-head">
                        <span class="failure-count">{{ grp.count }} 条</span>
                        <span class="failure-reason">{{ grp.message }}</span>
                        <el-button link type="primary" size="small" @click="grp.expanded = !grp.expanded">
                          {{ grp.expanded ? '收起' : '查看号码' }}
                        </el-button>
                      </div>
                      <div v-if="grp.expanded" class="failure-phones">
                        <span v-for="(p, i) in grp.phones.slice(0, 100)" :key="i" class="failure-phone-chip">{{ p }}</span>
                        <span v-if="grp.phones.length > 100" class="failure-phones-more">… 共 {{ grp.phones.length }} 个号码（仅显示前 100 个）</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </transition>
          </el-form>
        </div>
      </div>
      
      <!-- 右侧：手机预览 -->
      <div class="preview-panel">
        <div class="preview-header">
          <span class="preview-title">{{ $t('smsSend.livePreview') }}</span>
          <div class="preview-actions">
            <div class="preview-theme-toggle">
              <button type="button" :class="{ active: previewTheme === 'android' }" @click="previewTheme = 'android'">Android</button>
              <button type="button" :class="{ active: previewTheme === 'ios' }" @click="previewTheme = 'ios'">iOS</button>
            </div>
            <button type="button" class="preview-shot-btn" :disabled="capturing || !form.message" @click="capturePreview">
              <svg v-if="!capturing" width="15" height="15" viewBox="0 0 24 24" fill="none">
                <rect x="8" y="8" width="12" height="12" rx="2.4" stroke="currentColor" stroke-width="1.8"/>
                <path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4H5.5A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <svg v-else class="spinner" width="15" height="15" viewBox="0 0 24 24" fill="none">
                <path d="M12 3a9 9 0 1 0 9 9" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
              <span>{{ $t('smsSend.previewCopyImage') }}</span>
            </button>
          </div>
        </div>

        <!-- 自定义发送人(默认取 SID) -->
        <div class="preview-sender-field">
          <span class="psf-label">{{ $t('smsSend.previewSenderLabel') }}</span>
          <input v-model="previewSenderInput" class="psf-input" :placeholder="senderAutoName" maxlength="24" />
        </div>
        <div class="preview-tz-hint" v-if="previewCountryName">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8"/><path d="M12 7v5l3 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          {{ $t('smsSend.previewLocalTime', { country: previewCountryName }) }}
        </div>

        <div class="phone-container">
          <!-- ============ Android · Google 信息 ============ -->
          <div class="android-phone" v-if="previewTheme === 'android'">
            <div class="android-screen" ref="phoneCaptureRef">
              <div class="punch-hole"></div>

              <!-- 状态栏(浅色) -->
              <div class="gm-status-bar">
                <span class="gm-sb-time">{{ statusBarTime }}</span>
                <div class="gm-sb-right">
                  <span class="gm-sb-net">4G</span>
                  <svg width="17" height="11" viewBox="0 0 17 11" fill="#202124">
                    <rect x="0" y="7" width="3" height="4" rx="0.8"/>
                    <rect x="4.6" y="4.8" width="3" height="6.2" rx="0.8"/>
                    <rect x="9.2" y="2.4" width="3" height="8.6" rx="0.8"/>
                    <rect x="13.8" y="0" width="3" height="11" rx="0.8"/>
                  </svg>
                  <svg width="15" height="11" viewBox="0 0 16 12" fill="none">
                    <path d="M8 11 5.6 8.6a3.4 3.4 0 0 1 4.8 0L8 11Z" fill="#202124"/>
                    <path d="M3.7 6.7a6 6 0 0 1 8.6 0" stroke="#202124" stroke-width="1.4" stroke-linecap="round"/>
                    <path d="M1.4 4.35a9.3 9.3 0 0 1 13.2 0" stroke="#202124" stroke-width="1.4" stroke-linecap="round"/>
                  </svg>
                  <div class="gm-battery">
                    <span class="gm-battery-pct">79</span>
                    <div class="gm-battery-body"><div class="gm-battery-fill" style="width:79%"></div></div>
                    <div class="gm-battery-cap"></div>
                  </div>
                </div>
              </div>

              <!-- Google 信息 顶栏 -->
              <div class="gm-appbar">
                <svg class="gm-back" width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M20 12H4M4 12l7-7M4 12l7 7" stroke="#444746" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <div class="gm-avatar" :style="{ background: senderLooksNumeric ? '#E8664E' : senderAvatarColor }">
                  <svg width="18" height="18" viewBox="0 0 24 24">
                    <path fill="#fff" d="M12 12.2a4.3 4.3 0 1 0 0-8.6 4.3 4.3 0 0 0 0 8.6Zm0 2c-4.1 0-7.4 2.5-7.4 5.5 0 .9.6 1.6 1.5 1.6h11.8c.9 0 1.5-.7 1.5-1.6 0-3-3.3-5.5-7.4-5.5Z"/>
                  </svg>
                </div>
                <span class="gm-sender">{{ senderDisplay }}</span>
                <svg v-if="senderLooksNumeric" class="gm-call" width="18" height="18" viewBox="0 0 24 24" fill="#444746">
                  <path d="M6.6 10.8a15 15 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.24 11 11 0 0 0 3.5.56 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1 11 11 0 0 0 .56 3.5 1 1 0 0 1-.24 1l-2.2 2.3Z"/>
                </svg>
                <svg class="gm-more" width="18" height="18" viewBox="0 0 24 24" fill="#444746">
                  <circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/>
                </svg>
              </div>

              <!-- 会话区 -->
              <div class="gm-conversation">
                <!-- 保存联系人建议卡(仅号码发送人) -->
                <div class="gm-save-card" v-if="form.message && senderLooksNumeric">
                  <div class="gm-save-top">
                    <div class="gm-save-icon">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="#fff">
                        <path d="M10 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0 1.6c-3.3 0-6 1.7-6 3.9v1.3h8.3a5.4 5.4 0 0 1-.3-3.6c-.6-.1-1.3-.2-2-.2Zm8 .4v2h2v1.6h-2v2h-1.6v-2h-2V16h2v-2H18Z"/>
                      </svg>
                    </div>
                    <div class="gm-save-text">
                      <div class="gm-save-title">{{ saveTitleText }}</div>
                      <div class="gm-save-sub">{{ chrome.saveSub }}</div>
                    </div>
                    <svg class="gm-save-x" width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M6 6l12 12M18 6L6 18" stroke="#5f6368" stroke-width="2" stroke-linecap="round"/></svg>
                  </div>
                  <div class="gm-save-actions">
                    <span>{{ chrome.reportSpam }}</span>
                    <span>{{ chrome.addContact }}</span>
                  </div>
                </div>

                <div class="gm-spacer"></div>

                <div class="gm-empty" v-if="!form.message">
                  <div class="empty-icon">
                    <svg width="46" height="46" viewBox="0 0 48 48" fill="none">
                      <path d="M42 6H6C4.34 6 3 7.34 3 9V33C3 34.66 4.34 36 6 36H12V45L24 36H42C43.66 36 45 34.66 45 33V9C45 7.34 43.66 6 42 6Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
                    </svg>
                  </div>
                  <span>{{ $t('smsSend.enterToPreview') }}</span>
                </div>

                <!-- 号码发送人:时间 + 会话副标题 + 未读 -->
                <template v-else-if="senderLooksNumeric">
                  <div class="gm-time-center">{{ clockLabel }}</div>
                  <div class="gm-texting-with">{{ textingWithText }}</div>
                  <div class="gm-unread"><span>{{ chrome.unread }}</span></div>
                  <div class="gm-bubble"><template v-for="(part, i) in messageParts" :key="i"><a v-if="part.isLink" class="msg-link">{{ part.text }}</a><template v-else>{{ part.text }}</template></template></div>
                  <div class="gm-replies">
                    <span class="gm-reply-chip">{{ chrome.replyOkay }}</span>
                    <span class="gm-reply-chip">{{ chrome.replyThanks }}</span>
                    <span class="gm-reply-chip gm-reply-emoji">😊</span>
                  </div>
                </template>

                <!-- 品牌发送人:未读 + 气泡 + 链接预览卡 + 时间 -->
                <template v-else>
                  <div class="gm-unread"><span>{{ chrome.unread }}</span></div>
                  <div class="gm-bubble"><template v-for="(part, i) in messageParts" :key="i"><a v-if="part.isLink" class="msg-link">{{ part.text }}</a><template v-else>{{ part.text }}</template></template></div>
                  <div class="gm-link-card" v-if="messageHasUrl">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                      <path d="M4 12a8 8 0 1 1 2.3 5.6" stroke="#5f6368" stroke-width="2" stroke-linecap="round"/>
                      <path d="M4 20v-4h4" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <span>{{ chrome.tapToLoad }}</span>
                  </div>
                  <div class="gm-time-left">{{ clockLabel }}</div>
                </template>
              </div>

              <!-- 底部:品牌发送人=不可回复提示;号码发送人=输入栏 -->
              <div class="gm-footer" v-if="form.message && !senderLooksNumeric">
                {{ chrome.noReply }}<a>{{ chrome.learnMore }}</a>
              </div>
              <div class="gm-inputbar" v-else>
                <div class="gm-input-plus">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="#444746" stroke-width="2.2" stroke-linecap="round"/></svg>
                </div>
                <div class="gm-input-field">
                  <span>{{ chrome.simText }}</span>
                  <div class="gm-input-icons">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="#5f6368" stroke-width="1.7"/><circle cx="9" cy="10" r="1" fill="#5f6368"/><circle cx="15" cy="10" r="1" fill="#5f6368"/><path d="M8.5 14.5a4.5 4.5 0 0 0 7 0" stroke="#5f6368" stroke-width="1.7" stroke-linecap="round"/></svg>
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none"><rect x="3.5" y="5" width="17" height="14" rx="2.4" stroke="#5f6368" stroke-width="1.7"/><circle cx="8.5" cy="10" r="1.6" stroke="#5f6368" stroke-width="1.5"/><path d="M4 17l5-4 4 3 3-2.5 4 3.5" stroke="#5f6368" stroke-width="1.7" stroke-linejoin="round"/></svg>
                  </div>
                </div>
                <div class="gm-input-mic">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none"><path d="M6 10v2M10 7v8M14 5v12M18 9v4" stroke="#7c4dff" stroke-width="2.2" stroke-linecap="round"/></svg>
                </div>
              </div>

              <!-- Android 三键导航 -->
              <div class="gm-navbar">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M4 7h16M4 12h16M4 17h16" stroke="#4d4d4d" stroke-width="2" stroke-linecap="round"/></svg>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><rect x="4" y="4" width="16" height="16" rx="2.5" stroke="#4d4d4d" stroke-width="2.4"/></svg>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M15 5l-7 7 7 7" stroke="#4d4d4d" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </div>
            </div>
          </div>

          <!-- ============ iOS · 信息(浅色,真实短信截图,无边框) ============ -->
          <div class="iphone-l" v-else>
            <div class="iphone-l-screen" ref="phoneCaptureRef">
              <!-- 状态栏(黑字,含勿扰月亮) -->
              <div class="il-status-bar">
                <span class="il-time">{{ statusBarTime }}
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="#000"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>
                </span>
                <div class="il-icons">
                  <svg width="17" height="11" viewBox="0 0 17 11" fill="#000">
                    <rect x="0" y="7" width="3" height="4" rx="0.9"/>
                    <rect x="4.6" y="4.8" width="3" height="6.2" rx="0.9"/>
                    <rect x="9.2" y="2.4" width="3" height="8.6" rx="0.9"/>
                    <rect x="13.8" y="0" width="3" height="11" rx="0.9"/>
                  </svg>
                  <svg width="16" height="12" viewBox="0 0 16 12" fill="none">
                    <path d="M8 11.2 5.55 8.75a3.46 3.46 0 0 1 4.9 0L8 11.2Z" fill="#000"/>
                    <path d="M3.6 6.8a6.2 6.2 0 0 1 8.8 0" stroke="#000" stroke-width="1.5" stroke-linecap="round"/>
                    <path d="M1.2 4.35a9.6 9.6 0 0 1 13.6 0" stroke="#000" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                  <div class="il-battery">
                    <div class="il-battery-body"><div class="il-battery-fill"></div></div>
                    <div class="il-battery-cap"></div>
                  </div>
                </div>
              </div>

              <!-- 会话顶栏 -->
              <div class="il-nav">
                <div class="il-back">
                  <svg width="12" height="21" viewBox="0 0 12 21" fill="none">
                    <path d="M10.5 1.5 2 10.5l8.5 9" stroke="#007AFF" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                  <span class="il-unread">1</span>
                </div>
                <div class="il-contact">
                  <div class="il-avatar" style="background:#C7C7CC">
                    <svg width="26" height="26" viewBox="0 0 24 24">
                      <path fill="#fff" d="M12 12.2a4.3 4.3 0 1 0 0-8.6 4.3 4.3 0 0 0 0 8.6Zm0 2c-4.1 0-7.4 2.5-7.4 5.5 0 .9.6 1.6 1.5 1.6h11.8c.9 0 1.5-.7 1.5-1.6 0-3-3.3-5.5-7.4-5.5Z"/>
                    </svg>
                  </div>
                  <div class="il-name-row">
                    <span class="il-name">{{ senderDisplay }}</span>
                    <svg width="7" height="12" viewBox="0 0 7 12" fill="none">
                      <path d="M1 1l4.5 5L1 11" stroke="#B0B0B5" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </div>
                </div>
                <div class="il-nav-right"></div>
              </div>

              <!-- 会话区 -->
              <div class="il-chat">
                <template v-if="form.message">
                  <div class="il-date">
                    <span>{{ chrome.iosSmsLabel }}</span>
                    <span>{{ chrome.today }} {{ clockLabel }}</span>
                  </div>
                  <div class="il-bubble"><template v-for="(part, i) in messageParts" :key="i"><a v-if="part.isLink" class="msg-link ios">{{ part.text }}</a><template v-else>{{ part.text }}</template></template></div>
                </template>

                <div class="il-empty" v-else>
                  <div class="empty-icon">
                    <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                      <path d="M42 6H6C4.34 6 3 7.34 3 9V33C3 34.66 4.34 36 6 36H12V45L24 36H42C43.66 36 45 34.66 45 33V9C45 7.34 43.66 6 42 6Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
                    </svg>
                  </div>
                  <span>{{ $t('smsSend.enterToPreview') }}</span>
                </div>
              </div>

              <!-- 输入栏 -->
              <div class="il-input-bar">
                <div class="il-plus">
                  <svg width="14" height="14" viewBox="0 0 13 13" fill="none">
                    <path d="M6.5 1v11M1 6.5h11" stroke="#8A8A8E" stroke-width="1.7" stroke-linecap="round"/>
                  </svg>
                </div>
                <div class="il-field">
                  <span>{{ chrome.iosInput }}</span>
                  <svg width="11" height="16" viewBox="0 0 12 18" fill="none">
                    <rect x="3.5" y="0.5" width="5" height="10" rx="2.5" fill="#8A8A8E"/>
                    <path d="M1 8a5 5 0 0 0 10 0" stroke="#8A8A8E" stroke-width="1.4" fill="none" stroke-linecap="round"/>
                    <path d="M6 13v3.5M3.8 16.5h4.4" stroke="#8A8A8E" stroke-width="1.4" stroke-linecap="round"/>
                  </svg>
                </div>
              </div>

              <div class="il-home"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 草稿选择对话框 -->
    <el-dialog v-model="draftDialogVisible" :title="$t('smsSend.loadDraft')" width="500px">
      <div v-if="drafts.length === 0" class="empty-drafts">
        {{ $t('smsSend.noDrafts') }}
      </div>
      <div v-else class="draft-list">
        <div 
          v-for="(draft, index) in drafts" 
          :key="index" 
          class="draft-item"
          @click="selectDraft(draft)"
        >
          <div class="draft-content">{{ draft.content.substring(0, 50) }}{{ draft.content.length > 50 ? '...' : '' }}</div>
          <div class="draft-time">{{ draft.time }}</div>
          <el-button link type="danger" size="small" @click.stop="deleteDraft(index)">{{ $t('common.delete') }}</el-button>
        </div>
      </div>
    </el-dialog>

    <!-- 文件上传 -->
    <input 
      type="file" 
      ref="fileInputRef" 
      style="display: none" 
      :accept="fileAccept"
      @change="handleFileUpload"
    />

    <!-- ========== 自定义变量管理对话框 ========== -->
    <el-dialog v-model="showCustomVarDialog" title="自定义变量" width="540px" destroy-on-close>
      <!-- 快速添加标签（始终显示） -->
      <div class="cv-quick-tags">
        <span class="cv-quick-label">快速添加：</span>
        <el-tag v-for="q in quickVarOptions" :key="q" class="cv-quick-tag" :disabled="customVars.some(v => v.name === q)" @click="quickAddCustomVar(q, '')">+ {{ q }}</el-tag>
      </div>

      <!-- 已有变量列表 -->
      <div v-if="customVars.length" class="cv-list">
        <div v-for="(cv, idx) in customVars" :key="idx" class="cv-item-block">
          <div class="cv-item-header">
            <el-tag closable type="warning" @close="removeCustomVar(idx)">{{ '{' + cv.name + '}' }}</el-tag>
            <el-switch v-model="cv.multi" size="small" active-text="多值" inactive-text="单值" style="margin-left: auto;" />
          </div>
          <div v-if="!cv.multi" class="cv-item-value">
            <el-input v-model="cv.value" size="small" placeholder="替换值" clearable />
          </div>
          <div v-else class="cv-item-value">
            <el-input v-model="cv.value" type="textarea" :rows="3" placeholder="每行一个值，按号码顺序分配&#10;例如：&#10;CODE001&#10;CODE002&#10;CODE003" resize="vertical" />
            <div class="cv-multi-info">
              共 {{ cvValueLines(cv.value) }} 个值，按号码顺序依次分配（不足时循环）
            </div>
          </div>
        </div>
      </div>
      <el-empty v-else description="暂无自定义变量，点击上方标签快速添加" :image-size="48" />

      <!-- 新增变量 -->
      <div class="cv-add">
        <el-input v-model="newVarName" size="small" placeholder="变量名" style="width: 130px" @keyup.enter="addCustomVar" />
        <span class="cv-eq">=</span>
        <el-input v-model="newVarValue" size="small" placeholder="替换值" style="flex: 1" @keyup.enter="addCustomVar" />
        <el-button size="small" type="primary" @click="addCustomVar" :disabled="!newVarName.trim()">添加</el-button>
      </div>

      <template #footer>
        <div class="cv-footer">
          <el-button link type="info" size="small" @click="showVarGuide = true">变量使用教程</el-button>
          <div>
            <el-button @click="showCustomVarDialog = false">关闭</el-button>
            <el-button type="primary" @click="saveCustomVars">保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- ========== 变量使用教程（轻量） ========== -->
    <el-dialog v-model="showVarGuide" title="变量使用教程" width="500px" destroy-on-close append-to-body>
      <div class="guide-lite">
        <div class="guide-lite-section">
          <div class="guide-lite-title">系统变量</div>
          <p>工具栏中的变量按钮（序号、号码、国家等）点击即可插入到短信内容中。发送时系统自动替换为真实值，每条短信独立生成。</p>
          <div class="guide-lite-example">
            <div>模板：您的验证码 <code>{随机码}</code>，请在5分钟内使用</div>
            <div class="guide-lite-arrow">↓</div>
            <div>短信1：您的验证码 <strong>385921</strong>，请在5分钟内使用</div>
            <div>短信2：您的验证码 <strong>749063</strong>，请在5分钟内使用</div>
          </div>
        </div>
        <div class="guide-lite-section">
          <div class="guide-lite-title">自定义变量</div>
          <p>点击 <code>+ 自定义</code> 添加变量，如 <code>{公司名}</code>、<code>{链接}</code>、<code>{金额}</code>，设定值后发送时统一替换。</p>
        </div>
        <div class="guide-lite-section">
          <div class="guide-lite-title">多值模式（一号一码）</div>
          <p>开启"多值"开关后，每行输入一个值。发送时按号码顺序依次分配，不足时自动循环。适用于优惠码、邀请码等场景。</p>
          <div class="guide-lite-example">
            <div>值列表：CODE01 / CODE02 / CODE03</div>
            <div class="guide-lite-arrow">↓</div>
            <div>号码1 → CODE01，号码2 → CODE02，号码3 → CODE03</div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="showVarGuide = false">知道了</el-button>
      </template>
    </el-dialog>

    <!-- ========== 前端模板引擎对话框 ========== -->
    <el-dialog v-model="showTemplateEngine" title="智能生成短信文案" width="680px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="生成方式">
          <el-radio-group v-model="tplForm.mode">
            <el-radio value="type">按类型生成</el-radio>
            <el-radio value="rewrite" :disabled="!form.message.trim()">基于当前文案改写</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="tplForm.mode === 'type'">
          <el-form-item label="文案类型">
            <el-select v-model="tplForm.type" style="width: 100%">
              <el-option v-for="opt in TPL_TYPES" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="原始文案">
            <el-input :model-value="form.message" type="textarea" :rows="2" disabled />
          </el-form-item>
        </template>
        <el-form-item label="目标国家（可选）">
          <el-select
            v-model="tplGenCountryIso"
            filterable
            clearable
            placeholder="选择后显示该国主要语言，并同步模板语言"
            style="width: 100%"
            @change="onTplGenCountryChange"
          >
            <el-option
              v-for="c in countrySelectOptions"
              :key="c.iso"
              :label="`${c.name} (+${c.dial})`"
              :value="c.iso"
            />
          </el-select>
          <p v-if="tplCountryHint" class="lang-smart-hint">{{ tplCountryHint }}</p>
        </el-form-item>
        <div style="display: flex; gap: 12px">
          <el-form-item label="语言" style="flex: 1">
            <el-select v-model="tplForm.language" style="width: 100%">
              <el-option v-for="lang in LANG_OPTIONS" :key="lang.value" :label="lang.label" :value="lang.value" />
            </el-select>
            <div class="lang-smart-row">
              <el-checkbox v-model="tplAutoDetectOnOpen" size="small">打开时自动识别短信框内文案语言</el-checkbox>
              <div class="lang-smart-actions">
                <el-button type="primary" link size="small" @click="applyTplLangFromText">识别文案语言</el-button>
                <el-button type="primary" link size="small" @click="applyTplLangFromCountry">按首个收件号码国家</el-button>
              </div>
              <p v-if="tplLangHint" class="lang-smart-hint">{{ tplLangHint }}</p>
            </div>
          </el-form-item>
          <el-form-item label="生成条数" style="flex: 1">
            <el-input-number v-model="tplForm.count" :min="1" :max="20" style="width: 100%" />
          </el-form-item>
        </div>
        <el-form-item label="补充关键词（可选）">
          <el-input v-model="tplForm.keywords" placeholder="如：优惠、限时、注册奖励" />
        </el-form-item>
        <el-form-item label="单条最大字符数">
          <el-input-number v-model="tplForm.maxLen" :min="30" :max="tplMaxLenLimit" :step="10" style="width: 160px" />
          <span style="margin-left: 8px; font-size: 12px; color: var(--el-text-color-secondary)">英文 160 字/条，其它语言 70 字/条；随「语言」自动调整，超出将截断</span>
        </el-form-item>
        <el-button type="primary" @click="generateFromTemplateEngine" :loading="tplGenerating">
          生成文案
        </el-button>
      </el-form>

      <div v-if="tplResults.length" class="gen-results">
        <div class="gen-header">
          <el-checkbox v-model="tplSelectAll" @change="toggleTplSelectAll">全选</el-checkbox>
          <span class="gen-selected-tip">已选 {{ tplSelectedSet.size }} 条</span>
        </div>
        <div v-for="(msg, idx) in tplResults" :key="idx" class="gen-result-item" :class="{ selected: tplSelectedSet.has(idx) }" @click="toggleTplSelect(idx)">
          <el-checkbox :model-value="tplSelectedSet.has(idx)" @click.stop @change="toggleTplSelect(idx)" />
          <span class="gen-idx">{{ idx + 1 }}</span>
          <span class="gen-text">{{ msg }}</span>
          <span class="gen-char-count">{{ msg.length }}字符</span>
        </div>
      </div>

      <!-- 多选时的发送分配设置 -->
      <div v-if="tplSelectedSet.size > 1" class="multi-msg-config">
        <div class="mmc-title">多文案发送分配</div>
        <div class="mmc-desc">每条文案发送的号码数量，总量由系统自动按比例分配</div>
        <div class="mmc-row" v-for="idx in [...tplSelectedSet]" :key="idx">
          <span class="mmc-label">文案 {{ idx + 1 }}:</span>
          <span class="mmc-preview">{{ tplResults[idx] }}</span>
        </div>
        <div class="mmc-summary">
          共 {{ tplSelectedSet.size }} 条文案，发送时将均匀分配号码
        </div>
      </div>

      <template #footer>
        <el-button @click="showTemplateEngine = false">{{ t('common.cancel') }}</el-button>
        <el-button v-if="tplSelectedSet.size === 1" type="primary" @click="applySingleTpl">{{ t('smsSend.applySelectedText') }}</el-button>
        <el-button v-if="tplSelectedSet.size > 1" type="primary" @click="applyMultiTpl">{{ t('smsSend.applyNumItems', { n: tplSelectedSet.size }) }}</el-button>
      </template>
    </el-dialog>

    <!-- ========== 短链转换对话框 ========== -->
    <ShortLinkConvertDialog
      v-model="showShortLinkDialog"
      :message="form.message"
      @apply="applyShortLinkResult"
    />

    <!-- ========== AI 生成对话框 ========== -->
    <el-dialog v-model="showAiDialog" title="AI 智能优化短信文案" width="680px" destroy-on-close>
      <el-form label-position="top">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
          title="AI 会基于下方原始文案生成多条优化版本：语义不变，表达更自然吸引人，并降低运营商拦截风险（链接、数字原样保留）。"
        />
        <el-form-item label="原始文案（可直接编辑，与上方「短信内容」同步）">
          <el-input
            v-model="form.message"
            type="textarea"
            :rows="3"
            placeholder="在此输入或粘贴要优化的原始文案"
            @input="onAiOriginalInput"
          />
        </el-form-item>
        <el-form-item>
          <el-switch v-model="aiUseShortLink" active-text="启用短链转换" inline-prompt @change="onToggleShortLink" />
          <span class="ai-original-tools-hint" style="margin-left: 10px">开启后把文案里的链接转成可追踪短链，降低拦截风险</span>
        </el-form-item>
        <template v-if="aiUseShortLink">
          <el-form-item label="原链接（长链接，将转成短链）">
            <el-input
              v-model="aiShortLinkTarget"
              placeholder="https://promo.example.com/landing"
              clearable
              @blur="aiShortLinkTarget = normalizeTargetUrl(aiShortLinkTarget)"
            />
          </el-form-item>
          <el-form-item label="短链域名">
            <el-select
              v-model="aiShortLinkDomainId"
              :loading="aiShortLinkDomainLoading"
              filterable
              placeholder="请选择短链域名"
              style="width: 100%"
            >
              <el-option v-for="d in aiShortLinkDomains" :key="d.id" :label="d.base_url" :value="d.id">
                <span>{{ d.base_url }}</span>
                <span v-if="d.remark" style="color: var(--el-text-color-placeholder); margin-left: 8px; font-size: 12px">{{ d.remark }}</span>
              </el-option>
            </el-select>
            <div v-if="!aiShortLinkDomains.length && !aiShortLinkDomainLoading" class="ai-original-tools-hint">
              暂无可用域名，请联系管理员在「系统管理 → 短链域名」中配置
            </div>
          </el-form-item>
          <el-form-item label="短链模式">
            <el-radio-group v-model="aiShortLinkMode">
              <el-radio value="per_number">一号码一链</el-radio>
              <el-radio value="per_copy">一文案一链</el-radio>
            </el-radio-group>
            <div class="ai-original-tools-hint">
              一号码一链：每个号码唯一短链，可精准追踪到号码。
              一文案一链：同一条文案的所有号码共用一条短链，正文固定=报备模板，<strong>报备后不易被拦</strong>（点击按文案聚合统计）。
            </div>
          </el-form-item>
        </template>
        <div style="display: flex; gap: 12px">
          <el-form-item label="语言" style="flex: 1">
            <el-select v-model="aiForm.language" style="width: 100%">
              <el-option v-for="lang in LANG_OPTIONS" :key="lang.value" :label="lang.label" :value="lang.value" />
            </el-select>
            <div class="lang-smart-row">
              <el-checkbox v-model="aiAutoDetectOnOpen" size="small">打开时自动识别短信框内文案语言</el-checkbox>
              <div class="lang-smart-actions">
                <el-button type="primary" link size="small" @click="applyAiLangFromText">识别文案语言</el-button>
                <el-button type="primary" link size="small" @click="applyAiLangFromCountry">按首个收件号码国家</el-button>
              </div>
              <p v-if="aiLangHint" class="lang-smart-hint">{{ aiLangHint }}</p>
            </div>
          </el-form-item>
          <el-form-item label="生成条数" style="flex: 1">
            <el-input-number v-model="aiForm.count" :min="1" :max="20" style="width: 100%" />
          </el-form-item>
        </div>
        <el-form-item label="单条最大字符数">
          <el-input-number v-model="aiForm.maxLen" :min="30" :max="aiMaxLenLimit" :step="10" style="width: 160px" />
          <span style="margin-left: 8px; font-size: 12px; color: var(--el-text-color-secondary)">英文 160 字/条，其它语言 70 字/条；随「语言」自动调整，超出将截断</span>
        </el-form-item>
        <el-button type="primary" @click="generateFromAi" :loading="aiGenerating" :disabled="!form.message.trim()">
          <el-icon><MagicStick /></el-icon> AI 优化生成
        </el-button>
      </el-form>

      <div v-if="aiResults.length" class="gen-results">
        <div class="gen-header">
          <el-checkbox v-model="aiSelectAll" @change="toggleAiSelectAll">全选</el-checkbox>
          <span class="gen-selected-tip">已选 {{ aiSelectedSet.size }} 条</span>
          <div class="gen-header-actions">
            <el-button link type="primary" size="small" :loading="aiZhLoading" @click="translateAiResults">中文对照</el-button>
            <el-button link type="primary" size="small" :loading="aiGenerating" @click="generateFromAi">换一批</el-button>
          </div>
        </div>
        <div v-for="(msg, idx) in aiResults" :key="idx" class="gen-result-item" :class="{ selected: aiSelectedSet.has(idx) }" @click="toggleAiSelect(idx)">
          <el-checkbox :model-value="aiSelectedSet.has(idx)" @click.stop @change="toggleAiSelect(idx)" />
          <span class="gen-idx">{{ idx + 1 }}</span>
          <div class="gen-body">
            <span class="gen-text">{{ msg }}</span>
            <span v-if="aiResultsZh[idx]" class="gen-zh">中文：{{ aiResultsZh[idx] }}</span>
          </div>
          <span class="gen-char-count">{{ msg.length }}字符</span>
        </div>
      </div>

      <div v-if="aiSelectedSet.size > 1" class="multi-msg-config">
        <div class="mmc-title">多文案发送分配</div>
        <div class="mmc-row" v-for="idx in [...aiSelectedSet]" :key="idx">
          <span class="mmc-label">文案 {{ idx + 1 }}:</span>
          <span class="mmc-preview">{{ aiResults[idx] }}</span>
        </div>
        <div class="mmc-summary">
          共 {{ aiSelectedSet.size }} 条文案，发送时将均匀分配号码
        </div>
      </div>

      <template #footer>
        <el-button @click="showAiDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button v-if="aiSelectedSet.size === 1" type="primary" @click="applySingleAi">{{ t('smsSend.applySelectedText') }}</el-button>
        <el-button v-if="aiSelectedSet.size > 1" type="primary" @click="applyMultiAi">{{ t('smsSend.applyNumItems', { n: aiSelectedSet.size }) }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { toBlob } from 'html-to-image'
import { useRoute } from 'vue-router'
import type { FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Link, CopyDocument } from '@element-plus/icons-vue'
import ShortLinkConvertDialog from '../../components/ShortLinkConvertDialog.vue'
import { sendBatchSMS, submitSmsApproval, getChannelSenderIds } from '@/api/sms'
import { getChannels } from '@/api/channel'
import { getChannelBannedWords } from '@/api/sms'
import { getBatchDetail } from '@/api/batch'
import { getDataProducts, buyAndSend, getCarriers, getMyNumbersSummary, type DataProduct } from '@/api/data'
import { getAiConfig, generateSmsContent, paraphraseText, translateTexts } from '@/api/ai'
import { listActiveShortLinkDomains, buildTrackUrlPlaceholder, type ShortLinkDomain } from '@/api/short-link'
import request from '@/api/index'
import { COUNTRY_LIST, findCountryByIso } from '@/constants/countries'
import { COUNTRY_TIMEZONE } from '@/constants/countryTimezones'
import { PREVIEW_CHROME, COUNTRY_LANG } from '@/constants/previewChrome'
import { smsCodePointLength, isGsm7Message, countSmsParts, smsSegmentUnitLength } from '@/utils/smsParts'

const { t, locale } = useI18n()
const route = useRoute()

// ============ 常量 ============

const MAIN_VARS = [
  { tag: '{序号}', label: '序号', tip: '批次内序号，从1递增' },
  { tag: '{号码后四位}', label: '号码后四位', tip: '接收方号码后4位' },
  { tag: '{随机码4}', label: '随机码4', tip: '4位随机数字' },
  { tag: '{随机字母}', label: '随机字母', tip: '6位随机大写字母' },
  { tag: '{时间}', label: '时间', tip: '当前时间 HH:MM' },
]
const MORE_VARS = [
  { tag: '{号码}', label: '号码', tip: '接收方手机号码' },
  { tag: '{国家}', label: '国家', tip: '目标国家代码（如 BR、IN）' },
  { tag: '{日期}', label: '日期', tip: '当天日期 YYYY-MM-DD' },
  { tag: '{随机码}', label: '随机码', tip: '6位随机数字' },
  { tag: '{随机码8}', label: '随机码8', tip: '8位随机数字' },
]
const VARIABLES = [...MAIN_VARS, ...MORE_VARS]

const TPL_TYPES = [
  { value: 'marketing', label: '营销推广' },
  { value: 'notification', label: '通知提醒' },
  { value: 'verification', label: '验证码' },
  { value: 'greeting', label: '节日问候' },
  { value: 'promotion', label: '优惠活动' },
  { value: 'invitation', label: '邀请注册' },
]

const LANG_OPTIONS = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
  { value: 'ko', label: '한국어' },
  { value: 'bn', label: 'বাংলা (Bengali)' },
  { value: 'pt', label: 'Português' },
  { value: 'es', label: 'Español' },
  { value: 'vi', label: 'Tiếng Việt' },
  { value: 'th', label: 'ภาษาไทย' },
  { value: 'id', label: 'Bahasa Indonesia' },
]

/** 国际冠码前缀 → 模板语言（无专属文案库的国家回落到 en）；前缀越长越优先 */
const PHONE_PREFIX_TO_LANG: { prefix: string; lang: string }[] = [
  { prefix: '886', lang: 'zh' },
  { prefix: '852', lang: 'zh' },
  { prefix: '853', lang: 'zh' },
  { prefix: '855', lang: 'en' },
  { prefix: '856', lang: 'en' },
  { prefix: '880', lang: 'bn' },
  { prefix: '84', lang: 'vi' },
  { prefix: '66', lang: 'th' },
  { prefix: '62', lang: 'id' },
  { prefix: '60', lang: 'en' },
  { prefix: '65', lang: 'en' },
  { prefix: '63', lang: 'en' },
  { prefix: '55', lang: 'pt' },
  { prefix: '54', lang: 'es' },
  { prefix: '52', lang: 'es' },
  { prefix: '51', lang: 'es' },
  { prefix: '56', lang: 'es' },
  { prefix: '57', lang: 'es' },
  { prefix: '91', lang: 'en' },
  { prefix: '44', lang: 'en' },
  { prefix: '49', lang: 'en' },
  { prefix: '33', lang: 'en' },
  { prefix: '39', lang: 'en' },
  { prefix: '81', lang: 'ja' },
  { prefix: '82', lang: 'ko' },
  { prefix: '86', lang: 'zh' },
  { prefix: '7', lang: 'en' },
  { prefix: '1', lang: 'en' },
].sort((a, b) => b.prefix.length - a.prefix.length)

/**
 * ISO 3166-1 alpha-2 → 短信模板语言（未列出的国家默认 en，与现有模板池一致）
 */
const ISO_TO_TEMPLATE_LANG: Record<string, string> = {
  CN: 'zh',
  HK: 'zh',
  MO: 'zh',
  TW: 'zh',
  BD: 'bn',
  VN: 'vi',
  TH: 'th',
  ID: 'id',
  BR: 'pt',
  PT: 'pt',
  AR: 'es',
  MX: 'es',
  CO: 'es',
  CL: 'es',
  PE: 'es',
  VE: 'es',
  EC: 'es',
  GT: 'es',
  BO: 'es',
  PY: 'es',
  UY: 'es',
  CR: 'es',
  PA: 'es',
  CU: 'es',
  DO: 'es',
  SV: 'es',
  HN: 'es',
  NI: 'es',
  MY: 'en',
  PH: 'en',
  SG: 'en',
  IN: 'en',
  PK: 'en',
  NP: 'en',
  LK: 'en',
  MM: 'en',
  KH: 'en',
  LA: 'en',
  US: 'en',
  CA: 'en',
  GB: 'en',
  AU: 'en',
  NZ: 'en',
  IE: 'en',
  ZA: 'en',
  NG: 'en',
  KE: 'en',
  GH: 'en',
  EG: 'en',
  SA: 'en',
  AE: 'en',
  TR: 'en',
  RU: 'en',
  UA: 'en',
  PL: 'en',
  DE: 'en',
  FR: 'en',
  IT: 'en',
  ES: 'en',
  NL: 'en',
  BE: 'en',
  CH: 'en',
  AT: 'en',
  SE: 'en',
  NO: 'en',
  DK: 'en',
  FI: 'en',
  CZ: 'en',
  RO: 'en',
  HU: 'en',
  GR: 'en',
  IL: 'en',
  IR: 'en',
  IQ: 'en',
  JP: 'ja',
  KR: 'ko',
  KZ: 'en',
}

/** 模板语言对应「主要自然语言」中文说明（用于向用户展示） */
const TEMPLATE_LANG_NATURAL_ZH: Record<string, string> = {
  zh: '中文',
  bn: '孟加拉语',
  en: '英语（或当地多语环境下常用英语文案）',
  ja: '日语',
  ko: '韩语',
  pt: '葡萄牙语',
  es: '西班牙语',
  vi: '越南语',
  th: '泰语',
  id: '印尼语',
}

const countrySelectOptions = computed(() =>
  [...COUNTRY_LIST].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN')),
)

function getLangLabel(code: string): string {
  return LANG_OPTIONS.find((l) => l.value === code)?.label || code
}

/** 智能生成单条长度上限：英文按 GSM 单条 160；其余语言按 Unicode 单条 70 */
function maxSmsCharsForLang(lang: string): number {
  return lang === 'en' ? 160 : 70
}

/**
 * 去掉常见短链（无 https 的 bit.ly 等），避免仅剩拉丁字母误判为英文
 */
function stripNoiseForLangDetect(raw: string): string {
  return raw
    .replace(/\{[^}]+\}/g, ' ')
    .replace(/https?:\/\/\S+/gi, ' ')
    .replace(/\bbit\.ly\/[A-Za-z0-9]+\b/gi, ' ')
    .replace(/\b(?:t\.co|tinyurl\.com|goo\.gl)\/\S+/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * 根据正文粗略识别语言（孟加拉文优先于拉丁字母启发式）
 */
function detectLanguageFromText(text: string): string {
  const s = stripNoiseForLangDetect(text)
  if (!s) return 'zh'

  let cjk = 0
  let thai = 0
  let bengali = 0
  let arabic = 0
  for (const ch of s) {
    const c = ch.codePointAt(0)!
    if ((c >= 0x4e00 && c <= 0x9fff) || (c >= 0x3400 && c <= 0x4dbf)) cjk++
    if (c >= 0x0e00 && c <= 0x0e7f) thai++
    if (c >= 0x0980 && c <= 0x09ff) bengali++
    if (c >= 0x0600 && c <= 0x06ff) arabic++
    if ((c >= 0x3040 && c <= 0x30ff) || (c >= 0x31f0 && c <= 0x31ff)) return 'ja'
    if (c >= 0xac00 && c <= 0xd7af) return 'ko'
  }
  // 孟加拉文与阿拉伯文：至少 2 个区块内字符即判定（避免单字符误触）
  if (bengali >= 2) return 'bn'
  if (arabic >= 3) return 'en'
  if (cjk >= 2) return 'zh'
  if (thai >= 2) return 'th'
  if (/[ăâđêôơưĂÂĐÊÔƠƯ]/.test(s)) return 'vi'
  if (/\b(você|obrigado|cadastre|bônus|reais|voce)\b/i.test(s)) return 'pt'
  if (/\b(hola|gracias|registro|dinero|usted)\b/i.test(s)) return 'es'
  if (/[ñáéíóúü¿¡]/i.test(s) && !/[ãõ]/.test(s)) return 'es'
  if (/[ãõç]/.test(s.toLowerCase())) return 'pt'
  if (/[a-z]{4,}/i.test(s)) return 'en'
  return 'zh'
}

/**
 * 从单个号码（可含 +）推断模板语言
 */
function inferLanguageFromFirstPhone(raw: string): string {
  let d = raw.replace(/\D/g, '')
  if (d.startsWith('00')) d = d.slice(2)
  for (const { prefix, lang } of PHONE_PREFIX_TO_LANG) {
    if (d.startsWith(prefix)) return lang
  }
  return 'en'
}

/** 从号码解析 ISO（按最长国码优先匹配，与收件号码习惯一致） */
function inferCountryIsoFromPhone(raw: string): string {
  let d = raw.replace(/\D/g, '')
  if (d.startsWith('00')) d = d.slice(2)
  const sorted = [...COUNTRY_LIST].sort((a, b) => b.dial.length - a.dial.length)
  for (const c of sorted) {
    if (d.startsWith(c.dial)) return c.iso
  }
  return ''
}

// 全局违禁词（始终检测）
const GLOBAL_BANNED_WORDS = [
  'casino', 'gambling', 'porn', 'sex', 'drug', 'kill', 'bomb', 'terror',
  '赌博', '色情', '毒品', '暴力', '杀', '炸弹', '恐怖',
  'free money', 'dinero gratis', 'dinheiro grátis',
]

// 去除 emoji 的工具函数
function stripEmoji(str: string): string {
  // 仅删 emoji + 去首尾空白；不压缩内部连续空格——上游模板审核常做精确比对，
  // 「! 」「!  」是不同模板，不能擅自合并。
  return str.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{27BF}\u{FE00}-\u{FE0F}\u{1F900}-\u{1F9FF}\u{200D}\u{20E3}\u{2702}-\u{27B0}\u{E0020}-\u{E007F}]/gu, '').trim()
}

// 链接识别：http(s):// 或 裸域名(含路径)，如 cutt.ly/nt5UMSgf、shorturl.at/fNUmg
const URL_REGEX = /(https?:\/\/[^\s]+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:\/[^\s]*)?)/gi

function hasUrl(s: string): boolean {
  return new RegExp(URL_REGEX.source, 'i').test(s)
}

// 截断到指定字符数：优先保住末尾的「链接 + 紧邻的数字/验证码」整段，裁掉前面的正文，
// 而不是把链接整段丢掉。例如改写后正文变长超限，应裁泰文散文、保留 99-9999 与短链。
function truncateToLimit(msg: string, maxLen: number): string {
  if (msg.length <= maxLen) return msg
  const isProtected = (t: string) => hasUrl(t) || /\d/.test(t)
  // 按空白切分（保留空白片段），从末尾向前收集连续的「链接/含数字」token 作为受保护尾巴
  const parts = msg.split(/(\s+)/)
  let k = parts.length
  for (let idx = parts.length - 1; idx >= 0; idx--) {
    const tok = parts[idx]
    if (/^\s*$/.test(tok)) continue        // 跳过空白继续往前看
    if (isProtected(tok)) { k = idx; continue }
    break                                   // 遇到普通文字 token 即停
  }
  const tail = parts.slice(k).join('').trim()
  // 有可保护尾巴且尾巴本身放得下：裁前面正文给尾巴腾位置
  if (tail && tail.length + 1 < maxLen) {
    let prose = parts.slice(0, k).join('').replace(/\s+$/, '')
    const room = maxLen - tail.length - 1
    if (prose.length > room) prose = prose.substring(0, room).replace(/\s+$/, '')
    return (prose ? prose + ' ' + tail : tail).trim()
  }
  // 无尾巴或尾巴过长：退回「不在链接中间截断」的逻辑，避免出现半截坏链
  let cut = maxLen
  const re = new RegExp(URL_REGEX.source, 'gi')
  let m: RegExpExecArray | null
  while ((m = re.exec(msg)) !== null) {
    const start = m.index
    const end = m.index + m[0].length
    if (cut > start && cut < end) { cut = start; break }
  }
  return msg.substring(0, cut).replace(/\s+$/, '')
}
function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// 同义词/同义短语表（仅对有空格、可按词替换的语言；泰语等无空格语言不做替换，只重排）
// 取常见营销用词，保守替换，避免改变含义或破坏上游已报备模板。
const SYNONYMS: Record<string, Record<string, string[]>> = {
  en: {
    'now': ['today', 'right away'], 'free': ['complimentary', 'no-cost'], 'get': ['claim', 'grab'],
    'win': ['earn', 'score'], 'bonus': ['reward', 'perk'], 'join': ['sign up', 'enroll'],
    'limited': ['exclusive', 'special'], 'offer': ['deal', 'promo'], 'hurry': ['be quick', 'act fast'],
    'click': ['tap', 'open'], 'register': ['sign up', 'enroll'], 'discount': ['markdown', 'price cut'],
    'sale': ['clearance', 'flash sale'], 'new': ['latest', 'fresh'], 'best': ['top', 'finest'],
    'huge': ['massive', 'big'], 'instantly': ['right away', 'in seconds'], 'amazing': ['incredible', 'awesome'],
    'save': ['save big', 'cut costs'], 'gift': ['present', 'freebie'], 'deal': ['offer', 'bargain'],
    'exclusive': ['VIP', 'members-only'], 'extra': ['bonus', 'added'], 'today': ['now', 'right away'],
  },
  pt: {
    'agora': ['já', 'hoje'], 'grátis': ['gratuito', 'de graça'], 'ganhe': ['receba', 'conquiste'],
    'bônus': ['prêmio', 'recompensa'], 'oferta': ['promoção', 'oferta especial'],
    'cadastre-se': ['registre-se', 'inscreva-se'], 'aproveite': ['não perca', 'garanta'],
    'desconto': ['abatimento', 'redução'], 'novo': ['novíssimo', 'recém-chegado'],
    'rápido': ['depressa', 'sem demora'], 'limitado': ['restrito', 'por tempo limitado'],
    'clique': ['acesse', 'toque'], 'presente': ['brinde', 'mimo'], 'exclusivo': ['especial', 'só para você'],
    'promoção': ['oferta', 'liquidação'], 'última chance': ['não perca', 'corra'],
  },
  es: {
    'ahora': ['ya', 'hoy'], 'gratis': ['gratuito', 'sin costo'], 'gana': ['recibe', 'consigue'],
    'bono': ['premio', 'recompensa'], 'oferta': ['promoción', 'oferta especial'],
    'regístrate': ['inscríbete', 'únete'], 'aprovecha': ['no te lo pierdas', 'asegura'],
    'descuento': ['rebaja', 'precio especial'], 'nuevo': ['novedoso', 'recién llegado'],
    'rápido': ['pronto', 'sin demora'], 'limitado': ['exclusivo', 'por tiempo limitado'],
    'haz clic': ['ingresa', 'visita'], 'regalo': ['obsequio', 'detalle'], 'promoción': ['oferta', 'rebaja'],
    'última oportunidad': ['no te lo pierdas', 'date prisa'],
  },
  vi: {
    'ngay': ['hôm nay', 'liền'], 'nhận': ['lấy', 'sở hữu'], 'thưởng': ['quà', 'phần thưởng'],
    'ưu đãi': ['khuyến mãi', 'giảm giá'], 'đăng ký': ['tham gia', 'mở tài khoản'],
    'nhanh': ['gấp', 'mau lên'], 'miễn phí': ['không mất phí', 'free'],
    'cơ hội': ['dịp', 'thời cơ'], 'mới': ['mới nhất', 'vừa ra mắt'], 'tặng': ['biếu', 'trao'],
    'duy nhất': ['độc quyền', 'riêng biệt'], 'nạp': ['gửi', 'thêm tiền'], 'rút': ['rút tiền', 'lấy ra'],
  },
  id: {
    'sekarang': ['hari ini', 'segera'], 'gratis': ['cuma-cuma', 'tanpa biaya'],
    'dapatkan': ['raih', 'ambil'], 'bonus': ['hadiah', 'imbalan'],
    'penawaran': ['promo', 'diskon'], 'daftar': ['gabung', 'registrasi'],
    'buruan': ['cepat', 'jangan lewatkan'], 'baru': ['terbaru', 'baru rilis'],
    'menang': ['raih', 'menangkan'], 'klik': ['kunjungi', 'buka'],
    'terbatas': ['eksklusif', 'spesial'], 'kesempatan': ['peluang', 'kesempatan emas'],
    'hadiah': ['bonus', 'hibah'],
  },
}

// 同义词替换：保护链接，对命中词随机替换一个同义词；无词表的语言原样返回
function applySynonyms(text: string, lang: string): string {
  const map = SYNONYMS[lang]
  if (!map) return text
  const urls: string[] = []
  let out = text.replace(new RegExp(URL_REGEX.source, 'gi'), (m) => { urls.push(m); return `\u0000${urls.length - 1}\u0000` })
  // 单次扫描：所有词条合并成一个正则一次性替换，已替换的文本不会被后续词条再次命中（避免来回替换）
  const keys = Object.keys(map).sort((a, b) => b.length - a.length)
  const re = new RegExp(`(^|[^\\p{L}])(${keys.map(escapeRegExp).join('|')})(?![\\p{L}])`, 'giu')
  out = out.replace(re, (_full, pre: string, kw: string) => {
    const syns = map[kw.toLowerCase()]
    if (!syns) return _full
    const syn = syns[Math.floor(Math.random() * syns.length)]
      const cased = /^[A-ZÀ-Þ]/.test(kw) ? syn.charAt(0).toUpperCase() + syn.slice(1) : syn
    return pre + cased
  })
  return out.replace(/\u0000(\d+)\u0000/g, (_m, i) => urls[+i])
}

// 子句重排：按句末标点拆分，打乱非链接子句顺序，含链接子句保持在末尾。
// 不改动任何文字，语言无关（泰语等无空格语言同样安全）。
function reorderClauses(text: string): string {
  const parts = text.split(/([!！。?？]+)/)
  const clauses: string[] = []
  for (let i = 0; i < parts.length; i += 2) {
    const seg = (parts[i] || '').trim()
    const delim = (parts[i + 1] || '').trim()
    if (seg) clauses.push(seg + delim)
  }
  if (clauses.length < 2) return text
  const urlClauses = clauses.filter(c => hasUrl(c))
  const textClauses = clauses.filter(c => !hasUrl(c))
  for (let i = textClauses.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [textClauses[i], textClauses[j]] = [textClauses[j], textClauses[i]]
  }
  return [...textClauses, ...urlClauses].join(' ')
}

const TEMPLATE_POOL: Record<string, Record<string, string[]>> = {
  marketing: {
    zh: ['限时特惠！立即注册即可获得丰厚奖励，机会不容错过！','新用户专属福利来了！首次注册即送大礼包，快来领取！','您的专属邀请已生效！点击链接开启全新体验，好礼等你拿！','精选好物推荐！超值优惠限时开放，先到先得！','恭喜您获得VIP体验资格！立即激活享受尊贵服务！','重磅福利！邀请好友一起参与，双倍奖励等你赢！','开启财富之旅！注册即享新手礼包，机会稍纵即逝！'],
    en: ['Limited offer! Register now and claim your exclusive bonus!','Special welcome package waiting for you! Sign up today!','Your VIP invitation is ready! Click to start winning big!','Exclusive deal just for you! Don\'t miss this chance!','Congratulations! You\'ve been selected for a special reward!','Start your journey today! Register and get instant rewards!'],
    pt: ['Oferta limitada! Cadastre-se agora e ganhe bonus exclusivo!','Pacote de boas-vindas especial esperando por voce!','Seu convite VIP esta pronto! Clique para comecar a ganhar!','Promocao exclusiva so para voce! Nao perca esta chance!','Parabens! Voce foi selecionado para uma recompensa especial!'],
    es: ['Oferta limitada! Registrate ahora y reclama tu bono exclusivo!','Paquete de bienvenida especial esperandote!','Tu invitacion VIP esta lista! Haz clic para empezar a ganar!','Oferta exclusiva solo para ti! No pierdas esta oportunidad!'],
    vi: ['Uu dai co han! Dang ky ngay de nhan thuong doc quyen!','Goi chao mung dac biet dang cho ban!','Loi moi VIP cua ban da san sang! Nhap de bat dau!'],
    th: ['ข้อเสนอจำกัด! สมัครเลยรับโบนัสพิเศษ!','แพ็คเกจต้อนรับพิเศษรอคุณอยู่!'],
    id: ['Penawaran terbatas! Daftar sekarang dan dapatkan bonus eksklusif!','Paket selamat datang spesial menunggu Anda!'],
    ja: [
      '期間限定！今すぐ登録で特典をプレゼント。お見逃しなく！',
      '新規様限定のお得なキャンペーン開催中！お早めにご確認ください。',
      '会員様だけの特別オファー！本日限りのチャンスです。',
      '厳選オファー！この機会にぜひご登録ください。',
      'VIP体験のご案内！今すぐ有効化して特典をお受け取りください。',
      'お得なご紹介キャンペーン！お友達とご一緒にどうぞ。',
    ],
    ko: [
      '한정 특가! 지금 가입하시면 특별 보너스를 드립니다!',
      '신규 회원 전용 혜택이 열렸습니다. 서둘러 등록하세요!',
      '회원님만을 위한 특별 제안, 오늘만 진행됩니다.',
      '엄선된 혜택! 지금 등록하고 보상을 받아보세요.',
      'VIP 체험 초대! 바로 활성화하고 보상을 받으세요.',
      '친구 초대 이벤트! 함께하시면 추가 혜택이 있습니다.',
    ],
    bn: [
      'প্রথম জমা করলেই বিশেষ পুরস্কার! এখনই নিবন্ধন করুন, সুযোগ হাতছাড়া করবেন না।',
      'নতুন সদস্যদের জন্য উপহার! অ্যাকাউন্ট খুলুন আর বোনাস জিতুন।',
      'সীমিত সময়ের অফার! লিংকে ক্লিক করে আজই যোগ দিন।',
      'বন্ধুদের আমন্ত্রণ জানান—দুজনেই পুরস্কার পাবেন!',
      '৫৮৮৮ টাকা পর্যন্ত পুরস্কার জেতার সুযোগ! প্রথম জমায়ই পাবেন।',
    ],
  },
  notification: {
    zh: ['您的账户有新的重要通知，请及时查看！','温馨提醒：您的服务即将到期，请尽快续费！','系统升级通知：我们将于近期进行系统优化。','安全提醒：检测到您的账户在新设备上登录。'],
    en: ['Important notification for your account. Please check now!','Reminder: Your service is about to expire. Please renew soon!'],
    pt: ['Notificacao importante para sua conta. Verifique agora!'],
    es: ['Notificacion importante para su cuenta. Revise ahora!'],
    vi: ['Thong bao quan trong cho tai khoan cua ban!'],
    th: ['แจ้งเตือนสำคัญสำหรับบัญชีของคุณ!'],
    id: ['Pemberitahuan penting untuk akun Anda!'],
    ja: [
      'お客様のアカウントに重要なお知らせがあります。ご確認ください。',
      'サービス有効期限が近づいています。お早めに更新をご検討ください。',
    ],
    ko: [
      '계정에 중요한 알림이 있습니다. 확인해 주세요.',
      '서비스 만료 예정입니다. 곧 갱신해 주세요.',
    ],
    bn: [
      'আপনার অ্যাকাউন্টে একটি গুরুত্বপূর্ণ বিজ্ঞপ্তি আছে, দয়া করে দেখুন।',
      'আপনার সেবার মেয়াদ শীঘ্রই শেষ হচ্ছে, নবায়ন করুন।',
    ],
  },
  verification: {
    zh: ['您的验证码是：{随机码}，5分钟内有效，请勿泄露给他人。','验证码 {随机码}，此验证码用于身份验证，请在5分钟内使用。','验证码 {随机码}，您正在进行身份验证操作，如非本人操作请忽略。'],
    en: ['Your verification code is: {code}. Valid for 5 minutes.','Code: {code}. Use this to verify your identity. Expires in 5 min.'],
    pt: ['Seu codigo de verificacao e: {code}. Valido por 5 minutos.'],
    es: ['Su codigo de verificacion es: {code}. Valido por 5 minutos.'],
    vi: ['Ma xac minh cua ban la: {code}. Co hieu luc trong 5 phut.'],
    th: ['รหัสยืนยันของคุณคือ: {code} ใช้ได้ภายใน 5 นาที'],
    id: ['Kode verifikasi Anda: {code}. Berlaku selama 5 menit.'],
    ja: [
      '認証コードは {code} です。5分以内にご入力ください。他人に教えないでください。',
      'コード：{code}。本人確認用です。5分で無効になります。',
    ],
    ko: [
      '인증 코드: {code}. 5분 이내에 입력하세요. 타인에게 알리지 마세요.',
      '코드 {code} — 본인 확인용이며 5분 후 만료됩니다.',
    ],
    bn: [
      'আপনার যাচাইকরণ কোড: {code}। ৫ মিনিটের মধ্যে ব্যবহার করুন।',
      'কোড {code} — শুধুমাত্র আপনার জন্য। কাউকে জানাবেন না।',
    ],
  },
  greeting: {
    zh: ['节日快乐！感谢您一直以来的支持和信赖！','祝您新年快乐！新的一年，新的开始，愿好运常伴！','感恩有您！祝您节日愉快，幸福美满！'],
    en: ['Happy holidays! Thank you for your continued support!','Wishing you a wonderful new year!'],
    pt: ['Boas festas! Obrigado pelo seu apoio continuo!'],
    es: ['Felices fiestas! Gracias por su continuo apoyo!'],
    vi: ['Chuc mung ngay le!'], th: ['สุขสันต์วันหยุด!'], id: ['Selamat hari raya!'],
    ja: [
      '良いお年をお迎えください。いつもご利用ありがとうございます！',
      '新春のお慶びを申し上げます。本年もよろしくお願いいたします。',
    ],
    ko: [
      '즐거운 연말 보내세요. 항상 이용해 주셔서 감사합니다!',
      '새해 복 많이 받으세요. 올해도 잘 부탁드립니다!',
    ],
    bn: ['শুভ ছুটি! আপনার সমর্থনের জন্য ধন্যবাদ!', 'নতুন বছরের শুভেচ্ছা! সুখ ও সমৃদ্ধি কামনা করি।'],
  },
  promotion: {
    zh: ['限时优惠！全场商品低至3折，错过再等一年！','会员专属：今日充值享双倍积分！','爆款活动！前100名注册即送超值大礼包！','独家折扣码已为您生成，立即使用享最高50%优惠！'],
    en: ['Flash sale! Up to 70% off everything!','Members exclusive: Double points today!','Hot deal! First 100 sign-ups get a special bonus!'],
    pt: ['Venda relampago! Ate 70% de desconto!'], es: ['Venta flash! Hasta 70% de descuento!'],
    vi: ['Flash sale! Giam den 70%!'], th: ['Flash sale! ลดสูงสุด 70%!'], id: ['Flash sale! Diskon hingga 70%!'],
    ja: ['フラッシュセール！最大70%オフのチャンス！', '会員様限定：本日ご利用でポイント2倍！'],
    ko: ['플래시 세일! 최대 70% 할인!', '회원 전용: 오늘 충전 시 포인트 2배!'],
    bn: ['ফ্ল্যাশ সেল! সর্বোচ্চ ৭০% পর্যন্ত ছাড়!', 'আজই রিচার্জ করুন, দিগুণ পয়েন্ট পান!'],
  },
  invitation: {
    zh: ['您的好友邀请您加入，新用户注册即享专属礼包！','诚挚邀请您注册体验！专属邀请码已为您生成！','好友推荐：立即注册，您和好友各获奖励！'],
    en: ['You\'ve been invited! Register now and get an exclusive bonus!','Join us today! Your invitation code is ready!'],
    pt: ['Voce foi convidado! Registre-se agora!'], es: ['Has sido invitado! Registrate ahora!'],
    vi: ['Ban duoc moi! Dang ky ngay!'], th: ['คุณได้รับเชิญ! สมัครเลย!'], id: ['Anda diundang! Daftar sekarang!'],
    ja: [
      '招待が届いています！今すぐ登録して特典を受け取りましょう。',
      '本日からご参加ください。招待コードのご準備ができています。',
    ],
    ko: [
      '초대가 도착했습니다! 지금 가입하고 특전을 받으세요.',
      '오늘 바로 참여하세요. 초대 코드가 준비되었습니다.',
    ],
    bn: [
      'আপনাকে আমন্ত্রণ জানানো হয়েছে! নিবন্ধন করুন আর বিশেষ উপহার পান।',
      'বন্ধু আপনাকে যোগ দিতে বলেছে—এখনই সাইন আপ করুন!',
    ],
  },
}

// ============ State ============

const formRef = ref<FormInstance>()
const loading = ref(false)
const result = ref<any>(null)

/**
 * 失败原因汇总：把后端 result.messages（同步路径返回的每条号码结果）按 error.message 分组，
 * 暴露给模板的 result-banner 用于「7 条号码格式无效」这种聚合提示，避免客户以为系统"少发"。
 * 异步路径（>10 条）不返回 messages，computed 自然为空数组、不渲染。
 */
const failureSummary = computed<Array<{ code: string; message: string; count: number; phones: string[]; expanded: boolean }>>(() => {
  const msgs = result.value?.messages
  if (!Array.isArray(msgs) || msgs.length === 0) return []
  const groups = new Map<string, { code: string; message: string; count: number; phones: string[]; expanded: boolean }>()
  for (const m of msgs) {
    if (m && m.success === false) {
      // 后端 error 字段两种形态：对象 {code, message} 或直接是字符串（如 "入队失败"）
      let code = 'UNKNOWN'
      let text = ''
      if (typeof m.error === 'string') {
        text = m.error
        code = m.error
      } else if (m.error && typeof m.error === 'object') {
        code = m.error.code || 'UNKNOWN'
        text = m.error.message || code
      } else {
        text = '未知错误'
      }
      const key = `${code}::${text}`
      let g = groups.get(key)
      if (!g) {
        g = { code, message: text, count: 0, phones: [], expanded: false }
        groups.set(key, g)
      }
      g.count += 1
      if (m.phone_number) g.phones.push(String(m.phone_number))
    }
  }
  return Array.from(groups.values()).sort((a, b) => b.count - a.count)
})
const channels = ref<any[]>([])
const channelBound = ref(false)
const sendProgress = ref(0)
const asyncBatchPolling = ref<{batchId: number; total: number; timer: number | null} | null>(null)
const asyncBatchProgress = ref(0)
const asyncBatchStatus = ref('')
const fileInputRef = ref<HTMLInputElement>()
const fileAccept = ref('.txt')
const draftDialogVisible = ref(false)
const drafts = ref<{ content: string; time: string }[]>([])
const msgInputRef = ref<any>(null)
const cursorPos = ref(0)

// 自定义变量
interface CustomVar { name: string; value: string; multi?: boolean }
const customVars = ref<CustomVar[]>(loadCustomVarsFromStorage())
const showCustomVarDialog = ref(false)
const showVarGuide = ref(false)
const newVarName = ref('')
const newVarValue = ref('')
const quickVarOptions = ['公司名', '链接', '优惠码', '金额', '客服电话']

const numberSource = ref<'manual' | 'store' | 'private'>('manual')
const loadingPrivate = ref(false)
const privateGroups = ref<any[]>([])
const selectedPrivateGroup = ref<any>(null)
const carrierFilterPrivate = ref('')
const unusedOnlyPrivate = ref(false)
const privateQuantity = ref(1000)

/**
 * 与后端私库取号口径一致：勾选运营商时，「仅未使用」须用接口返回的 carriers[].unused_count，
 * 不能用该运营商总条数（否则卡片显示可发、实际 Airtel 未使用为 0 时会查不到号）。
 */
function privateEffectiveStock(group: any | null): number {
  if (!group) return 0
  if (!carrierFilterPrivate.value) {
    return unusedOnlyPrivate.value ? (group.unused_count ?? 0) : (group.count ?? 0)
  }
  const c = group.carriers?.find(
    (i: any) => (i.name || 'Unknown') === carrierFilterPrivate.value,
  )
  if (!c) return 0
  if (unusedOnlyPrivate.value) {
    if (typeof c.unused_count === 'number') return Math.max(0, c.unused_count)
    return Math.min(group.unused_count ?? 0, c.count ?? 0)
  }
  return c.count ?? 0
}

const privateStockMax = computed(() => privateEffectiveStock(selectedPrivateGroup.value))

const availableCarriersPrivate = computed(() => {
  const map: Record<string, number> = {}
  privateGroups.value.forEach(g => {
    if (g.carriers && Array.isArray(g.carriers)) {
      g.carriers.forEach((c: any) => {
        const name = c.name || 'Unknown'
        map[name] = (map[name] || 0) + c.count
      })
    }
  })
  // 转换并排序：按数量降序
  return Object.entries(map)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
})

const filteredPrivateGroups = computed(() => {
  if (!carrierFilterPrivate.value) return privateGroups.value
  return privateGroups.value.filter(g => {
    if (g.carriers && Array.isArray(g.carriers)) {
      return g.carriers.some(
        (c: any) => (c.name || 'Unknown') === carrierFilterPrivate.value,
      )
    }
    return (g.carrier || 'Unknown') === carrierFilterPrivate.value
  })
})

watch([selectedPrivateGroup, carrierFilterPrivate, unusedOnlyPrivate], () => {
  const g = selectedPrivateGroup.value
  if (g) {
    const max = privateEffectiveStock(g)
    if (privateQuantity.value > max) {
      privateQuantity.value = max
    }
    if (privateQuantity.value === 0) {
      privateQuantity.value = max
    }
  }
}, { immediate: true })

async function fetchPrivateGroups() {
  loadingPrivate.value = true
  try {
    const res = await getMyNumbersSummary({ max_batches: 0 })
    if (res.success) {
      privateGroups.value = res.items || []
    }
  } catch (e) {
    ElMessage.error('获取私有库数据失败')
  } finally {
    loadingPrivate.value = false
  }
}

/** 从路由查询参数选中私库卡片（与「我的私有库」发送短信跳转一致，含 batch_id） */
async function selectPrivateGroupFromRouteQuery() {
  const q = route.query
  const cc = typeof q.data_country === 'string' ? q.data_country.trim() : ''
  const src = typeof q.data_source === 'string' ? q.data_source.trim() : ''
  const pur = typeof q.data_purpose === 'string' ? q.data_purpose.trim() : ''
  const bid =
    typeof q.data_batch_id === 'string' ? q.data_batch_id.trim() : ''
  if (!cc || !src || !pur) return
  numberSource.value = 'private'
  if (privateGroups.value.length === 0) {
    await fetchPrivateGroups()
  }
  const items = privateGroups.value
  const exact = items.find(
    (g: any) =>
      g.country_code === cc &&
      g.source === src &&
      g.purpose === pur &&
      String(g.batch_id ?? '') === bid
  )
  const fallback = items.find(
    (g: any) => g.country_code === cc && g.source === src && g.purpose === pur
  )
  selectedPrivateGroup.value = exact || fallback || null
}

watch(numberSource, (val) => {
  if (val === 'private' && privateGroups.value.length === 0) {
    fetchPrivateGroups()
  }
})
const hasDataService = ref(false)
const accountUnitPrice = ref<number | null>(null)

// 数据商店
const loadingProducts = ref(false)
const storeProducts = ref<DataProduct[]>([])
const selectedProduct = ref<DataProduct | null>(null)
const storeQuantity = ref(1000)
const storeSending = ref(false)

// 运营商筛选
const carrierList = ref<{ name: string; count: number }[]>([])
const selectedCarrier = ref('')

// AI
const aiEnabled = ref(false)
const showTemplateEngine = ref(false)
const tplAutoDetectOnOpen = ref(true)
const tplLangHint = ref('')
const tplGenCountryIso = ref('')
const tplCountryHint = ref('')
const tplForm = ref({ type: 'marketing', language: 'zh', keywords: '', count: 5, mode: 'type' as 'type' | 'rewrite', maxLen: 70 })
const tplGenerating = ref(false)
const tplResults = ref<string[]>([])
const tplSelectedSet = ref<Set<number>>(new Set())
const tplSelectAll = ref(false)
const showAiDialog = ref(false)
const showShortLinkDialog = ref(false)
function applyShortLinkResult(newMessage: string) {
  form.value.message = newMessage
}
const aiAutoDetectOnOpen = ref(true)
const aiLangHint = ref('')
const aiGenCountryIso = ref('')
const aiCountryHint = ref('')
const aiForm = ref({ prompt: '', language: 'zh', count: 5, mode: 'prompt' as 'prompt' | 'rewrite', rewriteHint: '', maxLen: 70 })
const aiGenerating = ref(false)
const aiResults = ref<string[]>([])
const aiResultsZh = ref<string[]>([])  // AI 结果中文对照
const aiZhLoading = ref(false)
// AI 对话框内嵌短链转换
const aiUseShortLink = ref(false)
const aiShortLinkMode = ref<'per_number' | 'per_copy'>('per_number')  // 一号码一链 / 一文案一链
const aiShortLinkTarget = ref('')
const aiShortLinkDomainId = ref<number | undefined>(undefined)
const aiShortLinkDomains = ref<ShortLinkDomain[]>([])
const aiShortLinkDomainLoading = ref(false)
const aiSelectedSet = ref<Set<number>>(new Set())
const aiSelectAll = ref(false)

// 多文案发送列表
const multiMessages = ref<string[]>([])
const multiMessagesZh = ref<string[]>([])  // 预览区中文翻译（点「翻译中文」后填充）
const multiZhLoading = ref(false)
// 多文案内容变化时清掉旧翻译，避免错位
watch(multiMessages, () => { multiMessagesZh.value = [] })

const stats = ref({ today_sent: 0, today_success: 0, success_rate: 0, today_cost: '0.00' })

const form = ref({
  phone_numbers_text: '',
  message: '',
  sender_id: '',
  channel_id: null as number | null,
  resetOnlyNumbers: true,
  isScheduled: false,
  scheduledTime: '',
})

// ============ Computed ============

// 通道级违禁词（选中通道后从 API 加载）
const channelGlobalBanned = ref<string[]>([])
// 国家级违禁词 map: { 'BD': 'word1,word2', 'TH': 'word3' }
const countryBannedMap = ref<Record<string, string>>({})

// 监听通道切换，重新加载违禁词
watch(() => form.value.channel_id, async (newId) => {
  channelGlobalBanned.value = []
  countryBannedMap.value = {}
  if (!newId) return
  try {
    const res = await getChannelBannedWords(newId)
    if (res?.channel_banned_words) {
      channelGlobalBanned.value = res.channel_banned_words
        .split(/[,，\n]/).map((w: string) => w.trim()).filter(Boolean)
    }
    if (res?.country_banned_words) {
      countryBannedMap.value = res.country_banned_words
    }
  } catch { /* 静默失败 */ }
})

// 合并全局 + 通道 + 所有国家违禁词（用于内容检测）
const allBannedWords = computed(() => {
  const words = new Set([...GLOBAL_BANNED_WORDS, ...channelGlobalBanned.value])
  for (const bw of Object.values(countryBannedMap.value)) {
    if (bw) {
      bw.split(/[,，\n]/).map(w => w.trim()).filter(Boolean).forEach(w => words.add(w))
    }
  }
  return [...words]
})

/** 模板引擎：当前语言对应的单条字符上限（用于输入框 max） */
const tplMaxLenLimit = computed(() => maxSmsCharsForLang(tplForm.value.language))
/** AI 生成：当前语言对应的单条字符上限 */
const aiMaxLenLimit = computed(() => maxSmsCharsForLang(aiForm.value.language))

/** 预览手机主题(android=Google信息浅色 / ios=信息深色),持久化 */
const previewTheme = ref<'android' | 'ios'>(
  (localStorage.getItem('sms_preview_theme') as 'android' | 'ios') || 'android'
)
watch(previewTheme, v => localStorage.setItem('sms_preview_theme', v))

/** 手动自定义的预览发送人(留空时自动取 SID) */
const previewSenderInput = ref('')

/** 自动发送人：优先 SID，其次首个号码 */
const senderAutoName = computed(() => {
  if (form.value.sender_id) return form.value.sender_id
  const numbers = parseNumbers()
  if (numbers.length > 0) return '+' + numbers[0].replace(/^\+/, '')
  return t('smsSend.previewDefaultSender')
})

/** 顶栏显示的发送人：自定义优先，否则自动取 SID */
const senderDisplay = computed(() => previewSenderInput.value.trim() || senderAutoName.value)

/** \u53d1\u4ef6\u4eba\u9996\u5b57\u7b26\u662f\u5426\u4e3a\u5b57\u6bcd/\u6c49\u5b57\uff1a\u662f\u5219\u5934\u50cf\u663e\u793a\u9996\u5b57\u6bcd\uff0c\u5426\u5219\u663e\u793a\u9ed8\u8ba4\u4eba\u5f62\u526a\u5f71 */
/** \u6839\u636e\u53d1\u4ef6\u4eba\u540d\u5b57\u7a33\u5b9a\u5730\u6311\u4e00\u4e2a Google \u4fe1\u606f\u98ce\u683c\u5934\u50cf\u8272 */
const senderAvatarColor = computed(() => {
  const palette = ['#8e44e6', '#1a73e8', '#12a150', '#e8710a', '#d93025', '#0b8043', '#5f6368', '#a142f4']
  const name = senderDisplay.value || 'S'
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return palette[h % palette.length]
})

/** \u9884\u89c8\u76ee\u7684\u56fd\u5bb6 ISO2(\u7528\u4e8e\u6309\u5f53\u5730\u65f6\u533a\u663e\u793a\u65f6\u95f4);\u590d\u7528 SID \u76ee\u7684\u56fd\u5bb6\u63a8\u65ad */
const previewCountryIso = computed(() => {
  const raw = (sidTargetCountry.value || '').trim()
  if (!raw) return ''
  const up = raw.toUpperCase()
  if (COUNTRY_TIMEZONE[up]) return up                                   // \u5df2\u662f ISO2
  if (/^\d+$/.test(raw)) {                                              // \u533a\u53f7 \u2192 ISO2
    const sorted = [...COUNTRY_LIST].sort((a, b) => b.dial.length - a.dial.length)
    const hit = sorted.find(c => raw.startsWith(c.dial))
    if (hit) return hit.iso.toUpperCase()
  }
  const byName = COUNTRY_LIST.find(c => c.name === raw || c.en.toLowerCase() === raw.toLowerCase())
  return byName ? byName.iso.toUpperCase() : ''
})

/** \u76ee\u7684\u56fd\u5bb6\u7684 IANA \u65f6\u533a(\u53d6\u4e0d\u5230\u5219\u7a7a = \u7528\u672c\u673a\u65f6\u533a) */
const previewTimeZone = computed(() => COUNTRY_TIMEZONE[previewCountryIso.value] || '')

/** \u6536\u4ef6\u56fd\u5bb6\u4e2d\u6587/\u82f1\u6587\u540d(\u7528\u4e8e\u300c\u6309X\u5f53\u5730\u65f6\u95f4\u300d\u63d0\u793a) */
const previewCountryName = computed(() => {
  const c = COUNTRY_LIST.find(x => x.iso.toUpperCase() === previewCountryIso.value)
  if (!c) return ''
  return String(locale.value).startsWith('zh') ? c.name : c.en
})

/** 手机界面语言：有收件国家→按国家(未列出回退英文);无国家→跟随后台界面语言 */
const previewLang = computed(() => {
  const iso = previewCountryIso.value
  if (iso) return COUNTRY_LANG[iso] || 'en'
  return String(locale.value).startsWith('zh') ? 'zh' : 'en'
})

/** 当前手机界面文案集(按收件国家语言) */
const chrome = computed(() => PREVIEW_CHROME[previewLang.value] || PREVIEW_CHROME.en)

/** 带发送人占位符的文案 */
const textingWithText = computed(() => chrome.value.textingWith.replace('{sender}', senderDisplay.value))
const saveTitleText = computed(() => chrome.value.saveTitle.replace('{sender}', senderDisplay.value))

/** now \u6bcf 20s \u66f4\u65b0\u4e00\u6b21,\u9a71\u52a8\u65f6\u533a\u65f6\u95f4\u91cd\u7b97 */
const nowTick = ref(Date.now())

/** \u5f53\u524d\u9884\u89c8\u65f6\u95f4\u5728\u76ee\u7684\u56fd\u5bb6\u65f6\u533a\u7684 {h,m}(24 \u5c0f\u65f6\u5236;\u542b\u590f\u4ee4\u65f6) */
const zoneHM = computed(() => {
  const d = new Date(nowTick.value)
  const tz = previewTimeZone.value
  try {
    const s = new Intl.DateTimeFormat('en-GB', {
      timeZone: tz || undefined, hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(d)
    const [h, m] = s.split(':')
    return { h: parseInt(h, 10) || 0, m: m || '00' }
  } catch {
    return { h: d.getHours(), m: String(d.getMinutes()).padStart(2, '0') }
  }
})

/** \u72b6\u6001\u680f 12 \u5c0f\u65f6\u5236\u65f6\u95f4(1:35,\u65e0\u4e0a\u5348/\u4e0b\u5348\u524d\u7f00,\u8d34\u5408\u72b6\u6001\u680f) */
const statusBarTime = computed(() => {
  let h12 = zoneHM.value.h % 12
  if (h12 === 0) h12 = 12
  return `${h12}:${zoneHM.value.m}`
})

/** 12 \u5c0f\u65f6\u5236\u65f6\u949f\u6807\u7b7e(\u4e0b\u53481:35 / 1:35 PM),\u8ddf\u968f\u754c\u9762\u8bed\u8a00 */
const clockLabel = computed(() => {
  const { h, m } = zoneHM.value
  const zh = String(locale.value).startsWith('zh')
  const isPM = h >= 12
  let h12 = h % 12
  if (h12 === 0) h12 = 12
  if (zh) return `${isPM ? '\u4e0b\u5348' : '\u4e0a\u5348'}${h12}:${m}`
  return `${h12}:${m} ${isPM ? 'PM' : 'AM'}`
})

/** URL \u8bc6\u522b\uff1ahttp(s):// / www. / \u5e38\u89c1 TLD \u57df\u540d(\u53ef\u5e26\u8def\u5f84) */
const URL_SPLIT_RE = /((?:https?:\/\/|www\.)[^\s]+|(?:[a-z0-9-]+\.)+(?:com|net|org|cn|io|at|ly|me|xyz|link|top|vip|club|shop|site|info|co|app|live|online|store|fun)(?:\/[^\s]*)?)/gi

/** \u5f53\u524d\u9884\u89c8\u6b63\u6587 */
const previewBody = computed(() => (hasVariables.value ? previewSms.value : form.value.message) || '')

/** \u77ed\u4fe1\u6b63\u6587\u662f\u5426\u542b\u94fe\u63a5(\u54c1\u724c\u53d1\u9001\u4eba\u771f\u673a\u4f1a\u6e32\u67d3\u94fe\u63a5\u9884\u89c8\u5361\u7247) */
const messageHasUrl = computed(() => new RegExp(URL_SPLIT_RE.source, 'i').test(previewBody.value))

/** \u628a\u6b63\u6587\u62c6\u6210 \u6587\u672c/\u94fe\u63a5 \u7247\u6bb5\uff0c\u94fe\u63a5\u7247\u6bb5\u5728\u6c14\u6ce1\u91cc\u52a0\u4e0b\u5212\u7ebf(\u4eff\u771f\u673a\u81ea\u52a8\u8bc6\u522b URL) */
const messageParts = computed<Array<{ text: string; isLink: boolean }>>(() => {
  const test = new RegExp('^(?:' + URL_SPLIT_RE.source + ')$', 'i')
  return previewBody.value
    .split(URL_SPLIT_RE)
    .filter(p => p !== undefined && p !== '')
    .map(p => ({ text: p, isLink: test.test(p) }))
})

/** \u53d1\u9001\u4eba\u662f\u5426\u50cf\u53f7\u7801(\u7528\u4e8e\u5c55\u793a\u300c\u4fdd\u5b58\u8054\u7cfb\u4eba\u300d\u5efa\u8bae\u5361/\u5934\u50cf\u914d\u8272) */
const senderLooksNumeric = computed(() => /^\+?\d/.test(senderDisplay.value.trim()))

/** \u4e00\u952e\u590d\u5236\uff1a\u628a\u9884\u89c8\u624b\u673a\u6e32\u67d3\u6210 PNG \u5e76\u590d\u5236\u5230\u526a\u8d34\u677f(\u5931\u8d25\u56de\u9000\u4e0b\u8f7d) */
const phoneCaptureRef = ref<HTMLElement | null>(null)
const capturing = ref(false)
const capturePreview = async () => {
  const el = phoneCaptureRef.value
  if (!el || capturing.value) return
  capturing.value = true
  try {
    // 只抓屏幕内容:去边框(直角)、去阴影、隐藏挖孔摄像头 → 输出为真实截图
    const blob = await toBlob(el, {
      pixelRatio: 3,
      cacheBust: true,
      backgroundColor: previewTheme.value === 'ios' ? '#ffffff' : '#f7f9fc',
      style: { borderRadius: '0', boxShadow: 'none' },
      filter: (node: HTMLElement) => !(node?.classList && node.classList.contains('punch-hole')),
    })
    if (!blob) throw new Error('empty blob')
    const clip = (navigator as any).clipboard
    const CItem = (window as any).ClipboardItem
    if (clip?.write && CItem) {
      await clip.write([new CItem({ 'image/png': blob })])
      ElMessage.success(t('smsSend.previewCopied'))
    } else {
      // \u6d4f\u89c8\u5668\u4e0d\u652f\u6301\u56fe\u7247\u526a\u8d34\u677f \u2192 \u56de\u9000\u4e3a\u4e0b\u8f7d
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      const sender = (senderDisplay.value || 'sms').replace(/[^\w\u4e00-\u9fa5-]+/g, '_').slice(0, 20)
      a.href = url
      a.download = `${previewTheme.value}-${sender}-preview.png`
      a.click()
      URL.revokeObjectURL(url)
      ElMessage.success(t('smsSend.previewCopied'))
    }
  } catch (e) {
    console.error('copy failed', e)
    ElMessage.error(t('smsSend.previewCopyFailed'))
  } finally {
    capturing.value = false
  }
}

/**
 * 把 {{TRACK_URL=target|base}} 占位符替换为「实际发送时的短链」估算长度，
 * 避免字符计数 / 计费 / 预览把超长占位符当文案算（实际发送时占位符会被
 * worker 替换为 `${base}/{7位token}`）。
 */
const TRACK_URL_RE = /\{\{TRACK_URL(?:=([^}]*))?\}\}/g
function replaceTrackPlaceholdersForPreview(msg: string): string {
  return msg.replace(TRACK_URL_RE, (_full, inner) => {
    let base = 'klsms.com'  // 兜底：占位符未配置时的合理估算
    if (inner) {
      // {{TRACK_URL=target}} → base 缺失，用估算值
      // {{TRACK_URL=target|base}} → 用真实 base 计算
      const parts = String(inner).split('|')
      if (parts.length >= 2 && parts[1].trim()) base = parts[1].trim()
    }
    return `${base.replace(/\/+$/, '')}/Ab3Xz7q`
  })
}
const messageEffectiveForCount = computed(() =>
  resolveMessageForCount(form.value.message),
)

/** 正文码点数与超限阈值（GSM-7 单条 160，否则单条 70） */
const messageSmsLen = computed(() => smsCodePointLength(messageEffectiveForCount.value))
const messageIsGsm7 = computed(() => isGsm7Message(messageEffectiveForCount.value))
const messageEncoding = computed(() => (messageIsGsm7.value ? 'GSM-7' : 'Unicode'))
const messageUnitLabel = computed(() => (
  messageIsGsm7.value ? 'septet' : 'UTF-16 ' + String(t('smsSend.codeUnits'))
))
const singleSegmentCharLimit = computed(() => (messageIsGsm7.value ? 160 : 70))
// 与单段上限同口径的长度（GSM-7 按 septet，扩展字符算 2）；用于判断是否超出单段，
// 避免含 [ ] 等扩展字符时用码点数误判超限。
const messageSegmentUnits = computed(() => smsSegmentUnitLength(messageEffectiveForCount.value))

const estimatedParts = computed(() => countSmsParts(messageEffectiveForCount.value))

// 多文案时按第一条算段数（与 buy-and-send 后端计费一致）
const storeSmsParts = computed(() =>
  multiMessages.value.length > 1
    ? countSmsParts(resolveMessageForCount(multiMessages.value[0]))
    : estimatedParts.value
)

const numberCount = computed(() => parseNumbers().length)
const totalEstimatedSegments = computed(() => numberCount.value * estimatedParts.value)

/**
 * 美金费用展示：金额绝对值小于 1 时保留最多 4 位小数，避免 0.0065 被 toFixed(2) 显示成 0.01
 */
function formatUsdEstimate(n: number): string {
  if (!Number.isFinite(n)) return '0.00'
  const a = Math.abs(n)
  if (a === 0) return '0.00'
  if (a < 1) return String(Number(n.toFixed(4)))
  return n.toFixed(2)
}

// 数据商店：数据费（仅数据包单价×数量）
const storeDataCost = computed(() => {
  if (!selectedProduct.value) return 0
  return parseFloat(selectedProduct.value.price_per_number) * storeQuantity.value
})
// 数据商店：短信费（条数×每条段数×单价，与后端 buy-and-send 计费一致）
const storeSmsCost = computed(() => {
  const price = accountUnitPrice.value ?? 0
  if (price <= 0) return 0
  return storeQuantity.value * storeSmsParts.value * price
})
// 数据商店：合计费用（数据 + 短信）
const storeTotalCost = computed(() => storeDataCost.value + storeSmsCost.value)
// 展示用字符串（与小额单价兼容）
const storeCost = computed(() => formatUsdEstimate(storeTotalCost.value))

// 私有库：数据费为 0（自有号码），短信费与商店相同逻辑（条数 × 段数 × 账户短信单价）
const privateDataCost = computed(() => 0)
const privateSmsCost = computed(() => {
  const price = accountUnitPrice.value ?? 0
  if (price <= 0) return 0
  return privateQuantity.value * storeSmsParts.value * price
})
const privateTotalCost = computed(() => privateDataCost.value + privateSmsCost.value)
const privateCostStr = computed(() => formatUsdEstimate(privateTotalCost.value))

const hasVariables = computed(() => {
  const msg = form.value.message
  if (/\{(序号|国家|日期|时间|随机码|号码后四位|号码|随机字母|index|country|date|time|code|phone|last4|letters)\}/.test(msg)) return true
  if (/\{(随机码|code|随机字母|letters)\d{1,2}\}/.test(msg)) return true
  if (msg.includes('{{TRACK_URL')) return true   // 让右侧手机 mockup 渲染替换后的短链
  return customVars.value.some(cv => msg.includes(`{${cv.name}}`))
})

const hasSensitiveWord = computed(() => {
  const msg = form.value.message.toLowerCase()
  return allBannedWords.value.some(w => msg.includes(w.toLowerCase()))
})

const matchedBannedWords = computed(() => {
  const msg = form.value.message.toLowerCase()
  return allBannedWords.value.filter(w => msg.includes(w.toLowerCase()))
})

function _previewRandDigits(n: number): string {
  return Array.from({ length: n }, () => Math.floor(Math.random() * 10)).join('')
}
function _previewRandLetters(n: number): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  return Array.from({ length: n }, () => chars[Math.floor(Math.random() * 26)]).join('')
}

// 把 {{TRACK_URL}} 与 {序号}/{国家}/... 变量都替换成"示例值",得到贴近真实发送形态的文本。
// 既用于预览,也用于计费估算 —— 变量名本身含中文({国家}/{序号}/{随机码} 等)会让编码检测把
// 整条误判为 UCS2(70字/条)从而多算段数;替换成 ASCII 示例后,编码与段数才按真实发送内容计算。
function resolveMessageForCount(rawMsg: string): string {
  let msg = replaceTrackPlaceholdersForPreview(rawMsg)
  const now = new Date()
  const today = now.toISOString().slice(0, 10)
  const time = now.toTimeString().slice(0, 5)
  msg = msg.replace(/\{序号\}/g, '1').replace(/\{index\}/g, '1')
  msg = msg.replace(/\{国家\}/g, 'BR').replace(/\{country\}/g, 'BR')
  msg = msg.replace(/\{日期\}/g, today).replace(/\{date\}/g, today)
  msg = msg.replace(/\{时间\}/g, time).replace(/\{time\}/g, time)
  msg = msg.replace(/\{随机码\}/g, '385921').replace(/\{code\}/g, '385921')
  msg = msg.replace(/\{号码\}/g, '5511999887766').replace(/\{phone\}/g, '5511999887766')
  msg = msg.replace(/\{号码后四位\}/g, '7766').replace(/\{last4\}/g, '7766')
  msg = msg.replace(/\{随机字母\}/g, 'AXKPMZ').replace(/\{letters\}/g, 'AXKPMZ')
  msg = msg.replace(/\{随机码(\d{1,2})\}/g, (_, n) => _previewRandDigits(parseInt(n)))
  msg = msg.replace(/\{code(\d{1,2})\}/g, (_, n) => _previewRandDigits(parseInt(n)))
  msg = msg.replace(/\{随机字母(\d{1,2})\}/g, (_, n) => _previewRandLetters(parseInt(n)))
  msg = msg.replace(/\{letters(\d{1,2})\}/g, (_, n) => _previewRandLetters(parseInt(n)))
  for (const cv of customVars.value) {
    const pat = new RegExp(`\\{${cv.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\}`, 'g')
    if (cv.multi && cv.value.includes('\n')) {
      const first = cv.value.split('\n').map(l => l.trim()).find(Boolean) || `[${cv.name}]`
      msg = msg.replace(pat, first)
    } else {
      msg = msg.replace(pat, cv.value || `[${cv.name}]`)
    }
  }
  return msg
}
const previewSms = computed(() => resolveMessageForCount(form.value.message))

// ============ 变量插入 ============

function saveCursorPos() {
  nextTick(() => {
    const textarea = msgInputRef.value?.$el?.querySelector?.('textarea') || msgInputRef.value?.ref
    if (textarea) cursorPos.value = textarea.selectionStart ?? form.value.message.length
  })
}

function insertVariable(tag: string) {
  const content = form.value.message
  const pos = cursorPos.value
  form.value.message = content.slice(0, pos) + tag + content.slice(pos)
  cursorPos.value = pos + tag.length
  nextTick(() => {
    const textarea = msgInputRef.value?.$el?.querySelector?.('textarea')
    if (textarea) { textarea.focus(); textarea.setSelectionRange(cursorPos.value, cursorPos.value) }
  })
}

// ============ 自定义变量管理 ============

function loadCustomVarsFromStorage(): CustomVar[] {
  try { return JSON.parse(localStorage.getItem('sms_custom_vars') || '[]') } catch { return [] }
}

function addCustomVar() {
  const name = newVarName.value.trim().replace(/[{}]/g, '')
  if (!name) return
  if (customVars.value.some(v => v.name === name)) { ElMessage.warning(`变量 {${name}} 已存在`); return }
  const builtIn = ['序号', '国家', '日期', '时间', '随机码', '号码', '随机字母', 'index', 'country', 'date', 'time', 'code', 'phone', 'letters']
  if (builtIn.includes(name)) { ElMessage.warning(`{${name}} 是系统内置变量，请换个名称`); return }
  customVars.value.push({ name, value: newVarValue.value.trim() })
  newVarName.value = ''; newVarValue.value = ''
}

function removeCustomVar(idx: number) { customVars.value.splice(idx, 1) }

function saveCustomVars() {
  localStorage.setItem('sms_custom_vars', JSON.stringify(customVars.value))
  showCustomVarDialog.value = false
  ElMessage.success('自定义变量已保存')
}

function replaceCustomVars(msg: string, index = 0): string {
  let result = msg
  for (const cv of customVars.value) {
    const pat = new RegExp(`\\{${cv.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\}`, 'g')
    if (cv.multi && cv.value.includes('\n')) {
      const lines = cv.value.split('\n').map(l => l.trim()).filter(Boolean)
      const val = lines.length > 0 ? lines[index % lines.length] : cv.value
      result = result.replace(pat, val)
    } else {
      result = result.replace(pat, cv.value)
    }
  }
  return result
}

function cvValueLines(val: string): number {
  return val.split('\n').map(l => l.trim()).filter(Boolean).length
}

const hasMultiValueVars = computed(() => customVars.value.some(cv => cv.multi && cv.value.includes('\n')))

function quickAddCustomVar(name: string, value: string) {
  if (customVars.value.some(v => v.name === name)) {
    ElMessage.warning(`变量 {${name}} 已存在`)
    return
  }
  customVars.value.push({ name, value })
}

function openCustomVarDialog() {
  showCustomVarDialog.value = true
}

// ============ 模板引擎 ============

// 构造交给后端 AI 的提示词（按类型生成 / 基于当前文案改写）
function buildTplAiPrompt(maxLen: number): string {
  const noEmojiHint = '严禁使用任何 emoji 表情符号。'
  const sensitiveHint = '内容中不得包含敏感词汇（赌博、色情、毒品、暴力等）。'
  const charHint = `每条文案不超过 ${maxLen} 个字符。`
  const linkHint = '原文中的链接、网址、数字、验证码必须原样保留，不得改写、翻译或截断。'
  if (tplForm.value.mode === 'rewrite' && form.value.message.trim()) {
    const kw = tplForm.value.keywords.trim() ? `改写时尽量融入关键词：${tplForm.value.keywords}。` : ''
    return `请基于以下短信文案改写 ${tplForm.value.count} 个不同版本，保持核心意思但变换表达方式、语气和风格，每条都要明显不同，不要只是调整词序或加个前缀。${kw}${linkHint} ${noEmojiHint} ${sensitiveHint} ${charHint}\n\n原文案：${form.value.message}`
  }
  const typeLabel = TPL_TYPES.find(t => t.value === tplForm.value.type)?.label || tplForm.value.type
  const kw = tplForm.value.keywords.trim() ? `主题关键词：${tplForm.value.keywords}。` : ''
  return `请生成 ${tplForm.value.count} 条「${typeLabel}」类营销短信，风格多样、各不相同。${kw}${linkHint} ${noEmojiHint} ${sensitiveHint} ${charHint}`
}

async function generateFromTemplateEngine() {
  tplGenerating.value = true
  tplSelectedSet.value = new Set(); tplSelectAll.value = false
  const maxLen = tplForm.value.maxLen || maxSmsCharsForLang(tplForm.value.language)

  // AI 已配置时优先走后端 AI 做真正改写/生成；未配置或失败则回退本地模板引擎
  if (aiEnabled.value) {
    try {
      const prompt = buildTplAiPrompt(maxLen)
      const res = await generateSmsContent({ prompt, count: tplForm.value.count, language: tplForm.value.language, max_length: maxLen })
      if (res.success && res.messages?.length) {
        tplResults.value = res.messages.map(m => truncateToLimit(stripEmoji(m), maxLen))
        tplGenerating.value = false
        return
      }
      ElMessage.info('AI 未返回有效文案，已改用内置模板引擎')
    } catch (e: any) {
      ElMessage.info('AI 暂不可用，已改用内置模板引擎')
    }
  }

  // 改写模式：用 Google 往返翻译做改写（适合泰语等本地引擎改不动的语言），失败再回退本地模板
  if (tplForm.value.mode === 'rewrite' && form.value.message.trim()) {
    try {
      const res = await paraphraseText({ text: form.value.message.trim(), lang: tplForm.value.language, count: tplForm.value.count })
      if (res.success && res.variants?.length >= 2) {
        tplResults.value = res.variants.map(m => truncateToLimit(stripEmoji(m), maxLen))
        tplGenerating.value = false
        if (tplResults.value.length < tplForm.value.count) {
          ElMessage.info(`原文可改写空间有限，生成了 ${tplResults.value.length} 条不同文案`)
        }
        return
      }
    } catch {
      // 忽略，走下面的本地模板引擎兜底
    }
  }

  setTimeout(() => {
    tplResults.value = localTemplateGenerate(maxLen)
    tplGenerating.value = false
    if (tplForm.value.mode === 'rewrite' && tplResults.value.length < tplForm.value.count) {
      ElMessage.warning(`原文已接近字数上限且缺少可变换内容，仅生成 ${tplResults.value.length} 条不同文案；可提高「单条最大字符数」或配置 AI 以获得更多变体`)
    }
  }, 300)
}

// 本地模板引擎生成（AI 未配置或失败时的回退）
function localTemplateGenerate(maxLen: number): string[] {
    let raw: string[] = []
    if (tplForm.value.mode === 'rewrite' && form.value.message.trim()) {
      const base = stripEmoji(form.value.message.trim())
      const langPrefixes: Record<string, string[]> = {
        zh: ['', '【限时】', '【热门】', '【推荐】', '【独家】', ''],
        en: ['', '[Limited] ', '[Hot] ', '[Exclusive] ', '[Special] ', ''],
        bn: ['', '[সীমিত] ', '[হট] ', '[বিশেষ] ', '[এক্সক্লুসিভ] ', ''],
        pt: ['', '[Limitado] ', '[Destaque] ', '[Exclusivo] ', '[Especial] ', ''],
        es: ['', '[Limitado] ', '[Destacado] ', '[Exclusivo] ', '[Especial] ', ''],
        vi: ['', '[Gioi han] ', '[Noi bat] ', '[Doc quyen] ', '[Dac biet] ', ''],
        th: ['', '[จำกัด] ', '[แนะนำ] ', '[พิเศษ] ', '[เฉพาะ] ', ''],
        id: ['', '[Terbatas] ', '[Populer] ', '[Eksklusif] ', '[Spesial] ', ''],
        ja: ['', '【限定】', '【お得】', '【注目】', '【特別】', ''],
        ko: ['', '[한정] ', '[특가] ', '[추천] ', '[특별] ', ''],
      }
      const langSuffixes: Record<string, string[]> = {
        zh: ['', ' 立即行动！', ' 不容错过！', ' 先到先得！', ' 点击了解更多！', ' 名额有限！'],
        en: ['', ' Act now!', ' Don\'t miss out!', ' First come first served!', ' Click to learn more!', ' Limited spots!'],
        bn: ['', ' এখনই করুন!', ' মিস করবেন না!', ' সীমিত সুযোগ!', ' ক্লিক করুন!', ' দ্রুত!'],
        pt: ['', ' Aja agora!', ' Nao perca!', ' Vagas limitadas!', ' Saiba mais!', ' Aproveite!'],
        es: ['', ' Actua ahora!', ' No te lo pierdas!', ' Plazas limitadas!', ' Descubre mas!', ' Aprovecha!'],
        vi: ['', ' Hanh dong ngay!', ' Dung bo lo!', ' So luong co han!', ' Tim hieu them!', ' Nhanh tay!'],
        th: ['', ' ลงมือเลย!', ' อย่าพลาด!', ' จำนวนจำกัด!', ' คลิกเลย!', ' รีบเลย!'],
        id: ['', ' Ayo sekarang!', ' Jangan lewatkan!', ' Terbatas!', ' Klik untuk info!', ' Buruan!'],
        ja: ['', ' 今すぐどうぞ！', ' お見逃しなく！', ' 詳細はこちら！', ' 数量限定！', ''],
        ko: ['', ' 지금 바로!', ' 놓치지 마세요!', ' 자세히 보기!', ' 선착순!', ''],
      }
      const lang = tplForm.value.language
      const prefixes = langPrefixes[lang] || langPrefixes.en
      const suffixes = langSuffixes[lang] || langSuffixes.en
      const hasSynonyms = !!SYNONYMS[lang]
      // 正文里的链接绝不能被装饰挤出 maxLen 而截断，预留正文长度后才允许加前后缀
      const seen = new Set<string>()
      let guard = 0
      while (raw.length < tplForm.value.count && guard < tplForm.value.count * 12) {
        guard++
        // 变体核心：① 同义词替换（有词表的语言）② 子句重排（任意语言安全，不改字）
        let body = base
        if (hasSynonyms) body = applySynonyms(body, lang)
        if (Math.random() < 0.6) body = reorderClauses(body)
        // 再叠加前后缀装饰，进一步增加多样性
        let prefix = prefixes[Math.floor(Math.random() * prefixes.length)]
        let suffix = suffixes[Math.floor(Math.random() * suffixes.length)]
        const strategy = raw.length % 3
        if (strategy === 1) body = body.replace(/[!！。]?\s*$/, '')
        else if (strategy === 2) prefix = ''  // 仅加后缀
        // 预算控制：装饰超出 maxLen 时优先丢后缀，再丢前缀，保证正文(含链接)完整
        if (body.length + prefix.length + suffix.length > maxLen) {
          suffix = ''
          if (body.length + prefix.length > maxLen) prefix = ''
        }
        const variant = (prefix + body + suffix).trim()
        if (seen.has(variant)) continue  // 去重：避免产出多条一模一样的文案
        seen.add(variant)
        raw.push(variant)
      }
    } else {
      const pool = TEMPLATE_POOL[tplForm.value.type] || TEMPLATE_POOL.marketing
      let langPool = pool[tplForm.value.language] || pool.en || pool.zh || []
      if (!langPool.length) langPool = pool.zh || []
      const shuffled = [...langPool].sort(() => Math.random() - 0.5)
      raw = shuffled.slice(0, Math.min(tplForm.value.count, shuffled.length))
      if (tplForm.value.keywords.trim()) {
        const kws = tplForm.value.keywords.split(/[,，、\s]+/).filter(Boolean)
        raw = raw.map((msg, i) => {
          const kw = kws[i % kws.length]
          return kw && !msg.includes(kw) ? msg.replace(/[!！。]?\s*$/, `，${kw}！`) : msg
        })
      }
    }
    return raw.map(m => truncateToLimit(stripEmoji(m), maxLen))
}

// 复制文案到剪贴板（兼容非 HTTPS / 旧浏览器）
async function copyText(text: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'
      document.body.appendChild(ta); ta.select(); document.execCommand('copy')
      document.body.removeChild(ta)
    }
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择文案复制')
  }
}
async function copyAll(list: string[]) {
  if (!list.length) return
  await copyText(list.join('\n'))
}
// 预览区「翻译中文」：把已加载的多条文案译成中文做对照（Google 免费翻译，自动识别语言）
async function translateMulti() {
  if (!multiMessages.value.length) return
  multiZhLoading.value = true
  try {
    const res = await translateTexts({ texts: multiMessages.value, source: 'auto', target: 'zh-CN' })
    multiMessagesZh.value = res.success ? (res.translations || []) : []
    if (!res.success || !multiMessagesZh.value.some(Boolean)) ElMessage.warning('翻译失败，请稍后重试')
  } catch {
    ElMessage.error('翻译服务暂不可用')
  } finally {
    multiZhLoading.value = false
  }
}

// ===== AI 对话框内嵌短链转换 =====
function normalizeTargetUrl(raw: string): string {
  const u = (raw || '').trim()
  if (!u) return ''
  return /^https?:\/\//i.test(u) ? u : 'https://' + u.replace(/^\/+/, '')
}
async function loadAiShortLinkDomains() {
  aiShortLinkDomainLoading.value = true
  try {
    const resp: any = await listActiveShortLinkDomains()
    aiShortLinkDomains.value = (resp?.data?.data || resp?.data || []) as ShortLinkDomain[]
    if (!aiShortLinkDomainId.value && aiShortLinkDomains.value.length) {
      aiShortLinkDomainId.value = aiShortLinkDomains.value[0].id
    }
  } catch {
    ElMessage.warning('加载短链域名失败，请稍后重试')
  } finally {
    aiShortLinkDomainLoading.value = false
  }
}
function onToggleShortLink(val: boolean) {
  if (val) {
    if (!aiShortLinkDomains.value.length) loadAiShortLinkDomains()
    // 原链接为空时，尝试从原始文案里提取首个链接作为默认目标
    if (!aiShortLinkTarget.value.trim()) {
      const m = form.value.message.match(new RegExp(URL_REGEX.source, 'i'))
      if (m) aiShortLinkTarget.value = normalizeTargetUrl(m[0])
    }
  }
}
// 把单条文案里的链接替换为短链占位符；无链接则追加到末尾
function applyShortLinkToMsg(msg: string, placeholder: string): string {
  if (new RegExp(URL_REGEX.source, 'i').test(msg)) {
    return msg.replace(new RegExp(URL_REGEX.source, 'i'), placeholder)
  }
  return msg.replace(/\s+$/, '') + ' ' + placeholder
}

// AI 结果「中文对照」：翻译生成的优化文案做参考（Google 免费翻译，自动识别语言）
async function translateAiResults() {
  if (!aiResults.value.length) return
  aiZhLoading.value = true
  try {
    const res = await translateTexts({ texts: aiResults.value, source: 'auto', target: 'zh-CN' })
    aiResultsZh.value = res.success ? (res.translations || []) : []
    if (!res.success || !aiResultsZh.value.some(Boolean)) ElMessage.warning('翻译失败，请稍后重试')
  } catch {
    ElMessage.error('翻译服务暂不可用')
  } finally {
    aiZhLoading.value = false
  }
}

// 模板引擎多选逻辑
function toggleTplSelect(idx: number) {
  const s = new Set(tplSelectedSet.value)
  if (s.has(idx)) s.delete(idx); else s.add(idx)
  tplSelectedSet.value = s
  tplSelectAll.value = s.size === tplResults.value.length
}
function toggleTplSelectAll(val: boolean) {
  if (val) { tplSelectedSet.value = new Set(tplResults.value.map((_, i) => i)) }
  else { tplSelectedSet.value = new Set() }
}
function applySingleTpl() {
  const idx = [...tplSelectedSet.value][0]
  if (idx != null && tplResults.value[idx]) {
    form.value.message = tplResults.value[idx]; multiMessages.value = []
    showTemplateEngine.value = false
  }
}
function applyMultiTpl() {
  const msgs = [...tplSelectedSet.value].sort((a, b) => a - b).map(i => tplResults.value[i]).filter(Boolean)
  if (msgs.length > 0) {
    form.value.message = msgs[0]
    multiMessages.value = msgs
    showTemplateEngine.value = false
    ElMessage.success(`已加载 ${msgs.length} 条文案，发送时将均匀分配`)
  }
}

// ============ AI 生成 ============

async function generateFromAi() {
  const base = form.value.message.trim()
  if (!base) { ElMessage.warning('请先在「短信内容」中输入要优化的原始文案'); return }
  // 短链转换校验（放在 loading 之前，避免早退留下转圈）
  let slTarget = '', slBase = '', slEnabled = false
  if (aiUseShortLink.value) {
    slTarget = normalizeTargetUrl(aiShortLinkTarget.value)
    const dom = aiShortLinkDomains.value.find(d => d.id === aiShortLinkDomainId.value)
    if (!slTarget) { ElMessage.warning('已启用短链转换，请填写要转换的原链接'); return }
    if (!dom) { ElMessage.warning('已启用短链转换，请选择短链域名'); return }
    slBase = dom.base_url
    slEnabled = true
  }
  aiGenerating.value = true; aiSelectedSet.value = new Set(); aiSelectAll.value = false; aiResults.value = []; aiResultsZh.value = []
  const maxLen = aiForm.value.maxLen || maxSmsCharsForLang(aiForm.value.language)
  const hint = aiForm.value.rewriteHint.trim()

  const prompt = [
    `请基于以下原始短信文案，生成 ${aiForm.value.count} 条优化版本，要求：`,
    `1) 保持核心含义与营销目的不变；`,
    `2) 表达更自然、更吸引人，更能促使客户点击或转化；`,
    `3) 降低运营商/反垃圾系统的拦截与误判风险：避免明显垃圾营销腔、全大写、连续感叹号、敏感词堆砌，用词自然且每条措辞明显不同；`,
    `4) 原文中的链接、网址、数字、验证码必须原样保留，不得改写、翻译或截断；`,
    `5) 严禁使用任何 emoji；不得包含赌博/色情/毒品/暴力等违禁内容；`,
    `6) 每条不超过 ${maxLen} 个字符。`,
    hint ? `额外优化方向：${hint}` : '',
    `\n原始文案：${base}`,
  ].filter(Boolean).join('\n')

  try {
    const res = await generateSmsContent({ prompt, count: aiForm.value.count, language: aiForm.value.language, max_length: maxLen })
    if (res.success && res.messages?.length) {
      aiResults.value = res.messages.map(m => truncateToLimit(stripEmoji(m), maxLen))
    } else { ElMessage.warning('AI 未返回有效文案') }
  } catch (e: any) {
    // AI 不可用时退回往返翻译改写，仍基于原文产出优化变体
    try {
      const pr = await paraphraseText({ text: base, lang: aiForm.value.language, count: aiForm.value.count })
      if (pr.success && pr.variants?.length) {
        aiResults.value = pr.variants.map(m => truncateToLimit(stripEmoji(m), maxLen))
        ElMessage.info('AI 暂不可用，已用翻译改写引擎生成替代文案')
      } else {
        ElMessage.error(e.message || 'AI 优化失败，请稍后重试')
      }
    } catch {
      ElMessage.error(e.message || 'AI 优化失败，请稍后重试')
    }
  } finally {
    aiGenerating.value = false
    // 先基于可读文案拉取中文对照（此时链接还未换成占位符，翻译更干净）
    if (aiResults.value.length) translateAiResults()
    // 再把每条结果里的链接替换成短链占位符。一文案一链时每条打独立分组号 g=，
    // 使同一条文案的所有号码共用一个短链（利于报备）；一号码一链则不带分组。
    if (aiResults.value.length && slEnabled) {
      aiResults.value = aiResults.value.map((m) => {
        const ph = aiShortLinkMode.value === 'per_copy'
          ? `{{TRACK_URL=${slTarget}|${slBase}|g=${genShortLinkGroup()}}}`
          : buildTrackUrlPlaceholder({ targetUrl: slTarget, baseUrl: slBase })
        return applyShortLinkToMsg(m, ph)
      })
    }
  }
}
// 一文案一链分组号：每条文案一个唯一 id，同文案的所有号码据此共用短链
function genShortLinkGroup(): string {
  return 'g' + Math.random().toString(36).slice(2, 10)
}

// AI 多选逻辑
function toggleAiSelect(idx: number) {
  const s = new Set(aiSelectedSet.value)
  if (s.has(idx)) s.delete(idx); else s.add(idx)
  aiSelectedSet.value = s
  aiSelectAll.value = s.size === aiResults.value.length
}
function toggleAiSelectAll(val: boolean) {
  if (val) { aiSelectedSet.value = new Set(aiResults.value.map((_, i) => i)) }
  else { aiSelectedSet.value = new Set() }
}
// ============ 长短信确认 ============
// ============ 私有库发送 ============
const privateSending = ref(false)
async function handlePrivateSend() {
  if (!selectedPrivateGroup.value) return ElMessage.warning('请选择要发送的号码组')
  if (!form.value.message) return ElMessage.warning('请输入短信内容')
  
  const currentParts = countSmsParts(resolveMessageForCount(form.value.message))
  if (currentParts > 1) {
    try {
      await ElMessageBox.confirm(
        `当前短信内容较长，将拆分为 ${currentParts} 条计费。建议缩短内容以降低费用，或确认按多条计费发送。`,
        '多条计费提醒',
        { confirmButtonText: '确认发送', cancelButtonText: '返回修改', type: 'warning' }
      )
    } catch { return }
  }
  if (privateStockMax.value < 1 || privateQuantity.value < 1) {
    return ElMessage.warning('当前分组无可用号码或发送条数须至少为 1')
  }

  const qty = Math.max(1, Math.min(privateQuantity.value, privateStockMax.value))

  privateSending.value = true
  try {
    const g = selectedPrivateGroup.value
    const filters: Record<string, any> = {
      country_code: g.country_code || undefined,
      source: g.source || undefined,
      purpose: g.purpose || undefined,
      batch_id: g.batch_id != null && g.batch_id !== undefined ? String(g.batch_id) : '',
      limit: qty,
      unused_only: unusedOnlyPrivate.value,
    }
    if (carrierFilterPrivate.value) filters.carrier = carrierFilterPrivate.value
    const res = await sendBatchSMS({
      private_library_filters: filters,
      message: form.value.message,
      messages: multiMessages.value.length > 1 ? multiMessages.value : undefined,
      sender_id: form.value.sender_id || undefined,
      channel_id: form.value.channel_id,
      batch_name: `私有库 - ${g.country_code} - ${g.sourceLabel || g.source}`,
      scheduled_at: form.value.isScheduled && form.value.scheduledTime ? form.value.scheduledTime : undefined,
    })

    if (res.async_processing && res.batch_id) {
      ElMessage.success(`批量发送任务已提交（${res.total} 条），后台处理中，请在发送任务页查看进度`)
      result.value = { ...res, success: true }
    } else if (res.success && (res.succeeded ?? 0) > 0) {
      ElMessage.success('批量发送任务已创建')
      result.value = { ...res, success: true }
    } else if (res.success && (res.total ?? 0) > 0 && (res.succeeded ?? 0) === 0) {
      const firstErr = res.messages?.find((m: any) => !m.success)?.error?.message
      ElMessage.error(firstErr || '任务已创建但号码均未成功入队，请检查号码格式、通道与余额')
      result.value = { ...res, success: false }
    } else {
      ElMessage.error(res.error?.message || '发送失败')
      result.value = { ...res, success: false }
    }
  } catch (e: any) {
    ElMessage.error('发送请求失败: ' + (e.message || ''))
  } finally {
    privateSending.value = false
  }
}
function applyMultiAi() {
  const msgs = [...aiSelectedSet.value].sort((a, b) => a - b).map(i => aiResults.value[i]).filter(Boolean)
  if (msgs.length > 0) {
    form.value.message = msgs[0]
    multiMessages.value = msgs
    showAiDialog.value = false
    ElMessage.success(`已加载 ${msgs.length} 条文案，发送时将均匀分配`)
  }
}

// ============ 号码解析 & 过滤 ============

const parseNumbers = () => {
  if (!form.value.phone_numbers_text) return []
  return form.value.phone_numbers_text.split(/[\n,;\s]+/).map(n => n.trim()).filter(n => n.length >= 5)
}

// ===== 发送者ID(SID)下拉：按"通道 + 目的国家(取首个收件号码)"拉取已审批的可用 SID =====
const availableSids = ref<{ sender_id: string; sid_type?: string; is_default?: boolean }[]>([])
/** 首个收件号码推断的目的国家 ISO2（决定可用 SID 集合） */
const sidTargetCountry = computed(() => {
  // 目的国家：手输→取首个号码识别；私库→所选库分组国家；数据源→所选产品国家。
  // 后端用 get_country_variants 跨 ISO2/区号/中文名 匹配，故此处给原值即可。
  if (numberSource.value === 'private') return selectedPrivateGroup.value?.country_code || ''
  if (numberSource.value === 'store') return (selectedProduct.value as any)?.country_code || ''
  const nums = parseNumbers()
  return nums.length ? inferCountryIsoFromPhone(nums[0]) : ''
})
async function loadSenderIds() {
  const chId = form.value.channel_id
  const cc = sidTargetCountry.value
  if (!chId || !cc) { availableSids.value = []; return }
  try {
    const res: any = await getChannelSenderIds(chId, cc)
    availableSids.value = res?.items || []
    // 当前已选 SID 不在新列表中则清空，避免发送时被白名单拒绝；有默认则自动选默认
    const cur = form.value.sender_id
    if (cur && !availableSids.value.some(s => s.sender_id === cur)) form.value.sender_id = ''
    if (!form.value.sender_id) {
      const def = availableSids.value.find(s => s.is_default)
      if (def) form.value.sender_id = def.sender_id
    }
  } catch (e) {
    availableSids.value = []
  }
}
watch([() => form.value.channel_id, sidTargetCountry], loadSenderIds, { immediate: false })

/** 模板智能生成：根据短信内容框识别语言 */
function applyTplLangFromText() {
  const txt = form.value.message.trim()
  if (!txt) {
    ElMessage.warning('请先在「短信内容」中输入或粘贴文案')
    return
  }
  const lang = detectLanguageFromText(txt)
  tplForm.value.language = lang
  tplLangHint.value = `已根据文案识别为：${getLangLabel(lang)}`
}

/** 模板智能生成：根据首个收件号码国家/区号匹配语言 */
function applyTplLangFromCountry() {
  const nums = parseNumbers()
  if (!nums.length) {
    ElMessage.warning('请先在「收件号码」中填写至少一个号码')
    return
  }
  const iso = inferCountryIsoFromPhone(nums[0])
  tplGenCountryIso.value = iso
  if (iso) {
    onTplGenCountryChange(iso)
    tplLangHint.value = `已根据首个号码 ${nums[0]} 匹配国家并同步模板语言`
  } else {
    const lang = inferLanguageFromFirstPhone(nums[0])
    tplForm.value.language = lang
    tplCountryHint.value = ''
    tplLangHint.value = `已根据首个号码 ${nums[0]} 匹配为：${getLangLabel(lang)}（未能解析国家）`
  }
}

/** 选择目标国家后：展示主要自然语言说明，并同步模板语言 */
function onTplGenCountryChange(iso: string | undefined) {
  const v = (iso ?? '').trim()
  tplGenCountryIso.value = v
  if (!v) {
    tplCountryHint.value = ''
    return
  }
  const lang = ISO_TO_TEMPLATE_LANG[v] || 'en'
  tplForm.value.language = lang
  const c = findCountryByIso(v)
  const nat = TEMPLATE_LANG_NATURAL_ZH[lang] || '当地常用语言（当前使用英语模板）'
  tplCountryHint.value = `「${c?.name || v}」主要语言：${nat}。已选用文案模板语言：${getLangLabel(lang)}`
}

/** AI 生成：根据短信内容框识别语言 */
// 在 AI 对话框里直接编辑原始文案时：开启自动识别则随输入更新语言
function onAiOriginalInput() {
  if (!aiAutoDetectOnOpen.value) return
  const txt = form.value.message.trim()
  if (txt.length >= 2) {
    aiForm.value.language = detectLanguageFromText(txt)
    aiLangHint.value = `已自动识别文案语言：${getLangLabel(aiForm.value.language)}`
  }
}

function applyAiLangFromText() {
  const txt = form.value.message.trim()
  if (!txt) {
    ElMessage.warning('请先在「短信内容」中输入或粘贴文案')
    return
  }
  const lang = detectLanguageFromText(txt)
  aiForm.value.language = lang
  aiLangHint.value = `已根据文案识别为：${getLangLabel(lang)}`
}

/** AI 生成：根据首个收件号码匹配语言 */
function applyAiLangFromCountry() {
  const nums = parseNumbers()
  if (!nums.length) {
    ElMessage.warning('请先在「收件号码」中填写至少一个号码')
    return
  }
  const iso = inferCountryIsoFromPhone(nums[0])
  aiGenCountryIso.value = iso
  if (iso) {
    onAiGenCountryChange(iso)
    aiLangHint.value = `已根据首个号码 ${nums[0]} 匹配国家并同步生成语言`
  } else {
    const lang = inferLanguageFromFirstPhone(nums[0])
    aiForm.value.language = lang
    aiCountryHint.value = ''
    aiLangHint.value = `已根据首个号码 ${nums[0]} 匹配为：${getLangLabel(lang)}（未能解析国家）`
  }
}

/** 选择目标国家后：展示主要自然语言说明，并同步 AI 生成语言 */
function onAiGenCountryChange(iso: string | undefined) {
  const v = (iso ?? '').trim()
  aiGenCountryIso.value = v
  if (!v) {
    aiCountryHint.value = ''
    return
  }
  const lang = ISO_TO_TEMPLATE_LANG[v] || 'en'
  aiForm.value.language = lang
  const c = findCountryByIso(v)
  const nat = TEMPLATE_LANG_NATURAL_ZH[lang] || '当地常用语言（当前使用英语生成）'
  aiCountryHint.value = `「${c?.name || v}」主要语言：${nat}。已选用生成语言：${getLangLabel(lang)}`
}

watch(showTemplateEngine, (open) => {
  tplLangHint.value = ''
  tplGenCountryIso.value = ''
  tplCountryHint.value = ''
  if (open && tplAutoDetectOnOpen.value) {
    const txt = form.value.message.trim()
    if (txt) {
      tplForm.value.language = detectLanguageFromText(txt)
      tplLangHint.value = `已自动识别文案语言：${getLangLabel(tplForm.value.language)}`
    }
  }
  if (open) {
    tplForm.value.maxLen = maxSmsCharsForLang(tplForm.value.language)
  }
})

watch(showAiDialog, (open) => {
  aiLangHint.value = ''
  aiGenCountryIso.value = ''
  aiCountryHint.value = ''
  if (open) {
    // 先按首个收件号码识别国家（可选展示），再用文案语言识别覆盖（更贴合实际发送内容）
    const nums = parseNumbers()
    if (nums.length) {
      const iso = inferCountryIsoFromPhone(nums[0])
      if (iso) { aiGenCountryIso.value = iso; onAiGenCountryChange(iso) }
    }
    const txt = form.value.message.trim()
    if (aiAutoDetectOnOpen.value && txt) {
      aiForm.value.language = detectLanguageFromText(txt)
      aiLangHint.value = `已自动识别文案语言：${getLangLabel(aiForm.value.language)}`
    }
    aiForm.value.maxLen = maxSmsCharsForLang(aiForm.value.language)
  }
})

watch(() => tplForm.value.language, (lang) => {
  tplForm.value.maxLen = maxSmsCharsForLang(lang)
})

watch(() => aiForm.value.language, (lang) => {
  aiForm.value.maxLen = maxSmsCharsForLang(lang)
})

const filterNumbers = (type: string) => {
  const numbers = parseNumbers()
  let filtered: string[] = []
  switch (type) {
    case 'duplicate': filtered = [...new Set(numbers)]; ElMessage.success(t('smsSend.filterDuplicateResult', { count: filtered.length })); break
    case 'invalid': filtered = numbers.filter(n => /^\+?\d{8,15}$/.test(n)); ElMessage.success(t('smsSend.filterInvalidResult', { count: filtered.length })); break
    case 'empty': filtered = numbers.filter(n => n.length > 0); ElMessage.success(t('smsSend.filterEmptyResult', { count: filtered.length })); break
    default: filtered = numbers
  }
  form.value.phone_numbers_text = filtered.join('\n')
}

const importFile = (type: string) => { fileAccept.value = type === 'txt' ? '.txt' : '.xlsx,.xls,.csv'; fileInputRef.value?.click() }

const handleFileUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]; if (!file) return
  try {
    if (file.name.endsWith('.txt')) {
      const text = await file.text()
      const numbers = text.split(/[\n,;\s]+/).filter(n => n.trim().length > 0)
      form.value.phone_numbers_text = (form.value.phone_numbers_text ? form.value.phone_numbers_text + '\n' : '') + numbers.join('\n')
      ElMessage.success(t('smsSend.importedNumbers', { count: numbers.length }))
    } else { ElMessage.info(t('smsSend.excelComingSoon')) }
  } catch { ElMessage.error(t('smsSend.fileReadFailed')) }
  target.value = ''
}

const checkEmpty = () => ElMessage.info(t('smsSend.checkEmptyComingSoon'))

// ============ 草稿 ============

const handleSelectDraft = () => { loadDrafts(); draftDialogVisible.value = true }
const handleSaveDraft = () => {
  if (!form.value.message) { ElMessage.warning(t('smsSend.pleaseEnterContent')); return }
  const d = JSON.parse(localStorage.getItem('sms_drafts') || '[]')
  d.unshift({ content: form.value.message, time: new Date().toLocaleString() })
  if (d.length > 10) d.pop()
  localStorage.setItem('sms_drafts', JSON.stringify(d))
  ElMessage.success(t('smsSend.draftSaved'))
}
const loadDrafts = () => { drafts.value = JSON.parse(localStorage.getItem('sms_drafts') || '[]') }
const selectDraft = (draft: { content: string; time: string }) => { form.value.message = draft.content; draftDialogVisible.value = false; ElMessage.success(t('smsSend.draftSelected')) }
const deleteDraft = (index: number) => { drafts.value.splice(index, 1); localStorage.setItem('sms_drafts', JSON.stringify(drafts.value)); ElMessage.success(t('common.deleted')) }
const handlePreview = () => {
  if (!form.value.message) { ElMessage.warning(t('smsSend.pleaseEnterContent')); return }
  ElMessageBox.alert(hasVariables.value ? previewSms.value : form.value.message, t('smsSend.previewTitle'), { confirmButtonText: t('common.confirm') })
}

// ============ 提交审核（单条） ============

const approvalSubmitting = ref(false)
const handleSubmitApproval = async () => {
  if (!form.value.message?.trim()) {
    ElMessage.warning(t('smsSend.pleaseEnterContent'))
    return
  }
  const currentParts = countSmsParts(resolveMessageForCount(form.value.message))
  if (currentParts > 1) {
    try {
      await ElMessageBox.confirm(
        `当前短信内容较长，将拆分为 ${currentParts} 条计费。建议缩短内容以降低费用，或确认按多条计费提交审核。`,
        '多条计费提醒',
        { confirmButtonText: '确认提交', cancelButtonText: '返回修改', type: 'warning' }
      )
    } catch { return }
  }
  if (hasSensitiveWord.value) {
    const words = matchedBannedWords.value.join('、')
    try {
      await ElMessageBox.confirm(
        `短信内容包含违禁词：${words}\n\n含违禁词的短信可能被运营商拦截，确定继续提交？`,
        '违禁词提醒',
        { confirmButtonText: '仍然提交', cancelButtonText: '返回修改', type: 'warning' }
      )
    } catch { return }
  }
  approvalSubmitting.value = true
  try {
    const payload: { message: string; phone_number?: string } = {
      message: stripEmoji(replaceCustomVars(form.value.message)),
    }
    const numbers = parseNumbers()
    if (numbers.length === 1) {
      let phone = numbers[0].trim()
      if (!phone.startsWith('+')) phone = '+' + phone
      payload.phone_number = phone
    }
    const res: any = await submitSmsApproval(payload)
    const ticketHint = res?.ticket_no ? ` ${t('smsApprovalsPage.ticketNo', { no: res.ticket_no })}` : ''
    ElMessage.success(`${t('smsApprovalsPage.submitOk')}${ticketHint}`)
    handleReset()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('smsApprovalsPage.submitFailed'))
  } finally {
    approvalSubmitting.value = false
  }
}

// ============ 手动发送 ============

const handleSend = async () => {
  const isPrivate = numberSource.value === 'private'
  const numbers = isPrivate ? [] : parseNumbers()

  if (!isPrivate && numbers.length === 0) { ElMessage.warning(t('smsSend.pleaseEnterNumbers')); return }
  if (isPrivate && !selectedPrivateGroup.value) { ElMessage.warning('请选择私有库分组'); return }
  if (!form.value.message) { ElMessage.warning(t('smsSend.pleaseEnterContent')); return }

  const currentParts = countSmsParts(resolveMessageForCount(form.value.message))
  if (currentParts > 1) {
    try {
      await ElMessageBox.confirm(
        `当前短信内容较长，将拆分为 ${currentParts} 条计费。建议缩短内容以降低费用，或确认按多条计费发送。`,
        '多条计费提醒',
        { confirmButtonText: '确认发送', cancelButtonText: '返回修改', type: 'warning' }
      )
    } catch { return }
  }

  if (!isPrivate && numbers.length > 2000000) {
    ElMessage.warning('单次最多提交 200 万个号码')
    return
  }

  if (hasSensitiveWord.value) {
    const words = matchedBannedWords.value.join('、')
    try {
      await ElMessageBox.confirm(
        `短信内容包含违禁词：${words}\n\n含违禁词的短信可能被运营商拦截，确定继续发送？`,
        '违禁词提醒',
        { confirmButtonText: '仍然发送', cancelButtonText: '返回修改', type: 'warning' }
      )
    } catch { return }
  }

  loading.value = true; result.value = null; sendProgress.value = 0

  // 多文案轮发 + 多值变量展开 + 清理 emoji
  let msgs: string[]
  if (hasMultiValueVars.value && !isPrivate) {
    const base = multiMessages.value.length > 1 ? multiMessages.value : [form.value.message]
    msgs = numbers.map((_, ni) => {
      const tpl = base[ni % base.length]
      return stripEmoji(replaceCustomVars(tpl, ni))
    })
  } else {
    msgs = (multiMessages.value.length > 1 ? multiMessages.value.map(m => replaceCustomVars(m)) : [replaceCustomVars(form.value.message)])
      .map(m => stripEmoji(m))
  }

  const e164List = numbers.map((n) => {
    let p = n.trim()
    if (!p.startsWith('+')) p = '+' + p
    return p
  })

  try {
    const payload: any = {
      message: msgs[0],
      batch_name: isPrivate
        ? `私有库发送-${selectedPrivateGroup.value.country_code}-${new Date().toLocaleString('zh-CN', { hour12: false })}`
        : `发送页-${new Date().toLocaleString('zh-CN', { hour12: false })}`,
    }
    if (isPrivate) {
      const pg = selectedPrivateGroup.value
      const pf: Record<string, any> = {
        country_code: pg.country_code || undefined,
        source: pg.source || undefined,
        purpose: pg.purpose || undefined,
        batch_id: pg.batch_id != null && pg.batch_id !== undefined ? String(pg.batch_id) : '',
        limit: Math.max(1, Math.min(privateQuantity.value, privateStockMax.value)),
        unused_only: unusedOnlyPrivate.value,
      }
      if (carrierFilterPrivate.value) pf.carrier = carrierFilterPrivate.value
      payload.private_library_filters = pf
    } else {
      payload.phone_numbers = e164List
    }

    if (msgs.length > 1) payload.messages = msgs
    if (form.value.sender_id) payload.sender_id = form.value.sender_id
    if (form.value.channel_id) payload.channel_id = form.value.channel_id
    if (form.value.isScheduled && form.value.scheduledTime) payload.scheduled_at = form.value.scheduledTime

    const res = await sendBatchSMS(payload)
    const successCount = res?.succeeded ?? 0
    const failCount = res?.failed ?? 0
    const apiOk = res?.success !== false
    const totalQueued = res?.total ?? 0
    sendProgress.value = isPrivate ? privateQuantity.value : e164List.length

    const isAsyncBatch = res?.async_processing || (totalQueued > 500 && successCount === 0 && failCount === 0 && apiOk)

    if (isAsyncBatch) {
      result.value = { success: true, successCount: 0, failCount: 0, batchId: res?.batch_id }
      if (form.value.isScheduled && form.value.scheduledTime) {
        ElMessage.success(`已创建定时任务 ${totalQueued.toLocaleString()} 条，将于 ${form.value.scheduledTime} 自动发送，可在「发送任务」页查看`)
      } else {
        ElMessage.success(`已提交 ${totalQueued.toLocaleString()} 条，后台异步处理中，可在「发送任务」页查看进度`)
      }
      if (res?.batch_id) startBatchPolling(res.batch_id, totalQueued)
      if (form.value.resetOnlyNumbers) form.value.phone_numbers_text = ''
      else handleReset()
      loadStats()
    } else if (isPrivate) {
      if (!apiOk || totalQueued === 0) {
        result.value = { success: false, successCount: 0, failCount: 0, batchId: res?.batch_id }
        ElMessage.error(res?.error?.message || '未找到可发送的私库号码，请检查筛选条件或刷新私库')
      } else if (successCount > 0) {
        result.value = { success: true, successCount, failCount, batchId: res?.batch_id }
        ElMessage.success('任务已提交，可在发送任务页查看进度')
        if (form.value.resetOnlyNumbers) form.value.phone_numbers_text = ''
        else handleReset()
        loadStats()
      } else {
        const firstErr = res?.messages?.find((m: any) => !m.success)?.error?.message
        result.value = { success: false, successCount, failCount, batchId: res?.batch_id }
        ElMessage.error(firstErr || `已提交 ${totalQueued} 条均未成功入队，请检查号码、通道与余额`)
      }
    } else {
      result.value = {
        success: successCount > 0,
        successCount,
        failCount,
        batchId: res?.batch_id,
      }
      if (successCount > 0) {
        ElMessage.success(t('smsSend.sendCompleteResult', { success: successCount, fail: failCount }))
        if (form.value.resetOnlyNumbers) form.value.phone_numbers_text = ''
        else handleReset()
        loadStats()
      } else {
        const firstErr = res?.messages?.find((m: any) => !m.success)?.error?.message
        if (firstErr?.toLowerCase().includes('balance') || firstErr?.includes('余额')) {
          ElMessage.error(t('smsSend.insufficientBalance'))
        } else {
          ElMessage.error(firstErr || t('smsSend.sendFailedCheckBalance', { count: failCount }))
        }
      }
    }
  } catch (error: any) {
    result.value = { success: false, error: { message: error.message } }
    ElMessage.error(t('smsSend.sendFailed') + ': ' + (error.response?.data?.detail || error.message))
  } finally { loading.value = false }
}

// ============ 大批量异步进度轮询 ============

function startBatchPolling(batchId: number, total: number) {
  stopBatchPolling()
  asyncBatchProgress.value = 0
  asyncBatchStatus.value = 'processing'
  const poll = async () => {
    try {
      const detail = await getBatchDetail(batchId)
      asyncBatchProgress.value = detail.progress ?? 0
      asyncBatchStatus.value = detail.status ?? 'processing'
      const processed = (detail.success_count ?? 0) + (detail.failed_count ?? 0)

      if (detail.status === 'completed' || detail.status === 'failed') {
        stopBatchPolling()
        if (detail.status === 'completed') {
          ElMessage.success(`批次 #${batchId} 处理完成：成功 ${detail.success_count?.toLocaleString()}，失败 ${detail.failed_count?.toLocaleString()}`)
        } else {
          ElMessage.error(`批次 #${batchId} 处理失败：${detail.error_message || '未知错误'}`)
        }
        result.value = {
          success: (detail.success_count ?? 0) > 0,
          successCount: detail.success_count ?? 0,
          failCount: detail.failed_count ?? 0,
          batchId,
        }
        loadStats()
        return
      }

      asyncBatchPolling.value!.timer = window.setTimeout(poll, 3000)
    } catch {
      asyncBatchPolling.value!.timer = window.setTimeout(poll, 5000)
    }
  }
  asyncBatchPolling.value = { batchId, total, timer: window.setTimeout(poll, 2000) }
}

function stopBatchPolling() {
  if (asyncBatchPolling.value?.timer) {
    clearTimeout(asyncBatchPolling.value.timer)
  }
  asyncBatchPolling.value = null
}

onUnmounted(() => stopBatchPolling())

// ============ 商店购买发送 ============

const selectProduct = (product: DataProduct) => {
  selectedProduct.value = product
  storeQuantity.value = Math.max(product.min_purchase || 100, 1000)
}

const handleStoreSend = async () => {
  const currentParts = countSmsParts(resolveMessageForCount(form.value.message))
  if (currentParts > 1) {
    try {
      await ElMessageBox.confirm(
        `当前短信内容较长，将拆分为 ${currentParts} 条计费。建议缩短内容以降低费用，或确认按多条计费发送。`,
        '多条计费提醒',
        { confirmButtonText: '确认发送', cancelButtonText: '返回修改', type: 'warning' }
      )
    } catch { return }
  }

  try {
    await ElMessageBox.confirm(
      storeSmsCost.value > 0
        ? `确认购买 ${storeQuantity.value.toLocaleString()} 条数据并发送短信？\n数据费: $${formatUsdEstimate(storeDataCost.value)} + 短信费: $${formatUsdEstimate(storeSmsCost.value)} = 合计: $${storeCost.value}`
        : `确认购买 ${storeQuantity.value.toLocaleString()} 条数据并发送短信？\n费用: $${storeCost.value}`,
      '确认购买发送', { type: 'warning' },
    )
  } catch { return }

  storeSending.value = true; result.value = null
  try {
    const payload: any = {
      product_id: selectedProduct.value.id,
      quantity: storeQuantity.value,
      message: stripEmoji(replaceCustomVars(form.value.message)),
    }
    if (selectedCarrier.value) payload.carrier = selectedCarrier.value
    if (form.value.channel_id) payload.channel_id = form.value.channel_id
    if (multiMessages.value.length > 1) {
      payload.messages = multiMessages.value.map(m => stripEmoji(replaceCustomVars(m)))
    }
    if (form.value.isScheduled && form.value.scheduledTime) payload.scheduled_at = form.value.scheduledTime
    const res = await buyAndSend(payload)
    if (res.success) {
      const asyncHint = res.async ? '（后台处理中，请稍后查看发送统计）' : ''
      result.value = { success: true, message: `已购买 ${storeQuantity.value} 条数据并创建发送任务${asyncHint}，批次: ${res.batch_id}` }
      ElMessage.success(`订单创建成功！${asyncHint}`)
      loadStats()
      loadStoreProducts()
    }
  } catch (error: any) {
    const detail = error?.response?.data?.detail || error.message || '购买发送失败'
    result.value = { success: false, error: { message: detail } }
    ElMessage.error(detail)
  } finally { storeSending.value = false }
}

// ============ 重置 ============

const handleReset = () => {
  form.value.phone_numbers_text = ''; form.value.message = ''; form.value.sender_id = ''; form.value.channel_id = null; result.value = null
  selectedProduct.value = null
}

// ============ 数据加载 ============

const loadChannels = async () => {
  try { const res = await getChannels(); channels.value = res.channels || []; channelBound.value = res.bound === true; if (channelBound.value && channels.value.length >= 1) form.value.channel_id = channels.value[0].id } catch (e) { console.error('Load channels failed', e) }
}

const loadStats = async () => {
  try { const res = await request.get('/sms/stats'); if (res) stats.value = { today_sent: res.today_sent || 0, today_success: res.today_success || 0, success_rate: res.success_rate || 0, today_cost: res.today_cost || '0.00' } } catch (e) { console.error('Load stats failed', e) }
}

const loadStoreProducts = async () => {
  loadingProducts.value = true
  try {
    const params: any = {}
    if (selectedCarrier.value) params.carrier = selectedCarrier.value
    const res = await getDataProducts(params)
    if (res.success) storeProducts.value = res.items
  } catch (e) { console.error('Load products failed', e) } finally { loadingProducts.value = false }
}

const loadCarriers = async () => {
  try {
    const res = await getCarriers()
    if (res.success) carrierList.value = res.carriers || []
  } catch (e) { console.error('Load carriers failed', e) }
}

const selectCarrier = (name: string) => {
  selectedCarrier.value = name
  selectedProduct.value = null
  loadStoreProducts()
}

function formatCount(count: number): string {
  if (count >= 10000) return (count / 10000).toFixed(1) + 'w'
  if (count >= 1000) return (count / 1000).toFixed(1) + 'k'
  return count.toString()
}

function getGroupName(group: any) {
  const remarks = group.remarks ? ` (${group.remarks})` : ''
  if (group.batch_name) return `${group.batch_name}${remarks}`
  const country = findCountryByIso(group.country_code)
  const countryName = country ? country.name : group.country_code
  const base = `${countryName}-${group.source_label || group.source}-${group.purpose_label || group.purpose}`
  return `${base}${remarks}`
}

function privateLibraryOriginLabel(o: string) {
  if (o === 'manual') return t('dataMyNumbers.libraryOriginManual')
  if (o === 'purchased') return t('dataMyNumbers.libraryOriginPurchased')
  if (o === 'mixed') return t('dataMyNumbers.libraryOriginMixed')
  return o
}

const checkServices = async () => {
  try {
    const info = await request.get('/account/info')
    const svc = info?.services || info?.account?.services || ''
    hasDataService.value = svc.includes('data')
    accountUnitPrice.value = info?.unit_price != null ? Number(info.unit_price) : null
    if (hasDataService.value) loadCarriers()
  } catch { hasDataService.value = false; accountUnitPrice.value = null }
}

const checkAiConfig = async () => { try { const cfg = await getAiConfig(); aiEnabled.value = cfg.ai_enabled } catch { aiEnabled.value = false } }

const updateTime = () => { nowTick.value = Date.now() }

let timeInterval: number

/** 从短信审核页跳转时一次性写入文案与号码 */
const SMS_SEND_PREFILL_KEY = 'sms_send_prefill_from_approval'
function consumeApprovalPrefill() {
  try {
    const raw = sessionStorage.getItem(SMS_SEND_PREFILL_KEY)
    if (!raw) return
    sessionStorage.removeItem(SMS_SEND_PREFILL_KEY)
    const data = JSON.parse(raw) as { message?: string; phone_numbers_text?: string }
    let filled = false
    if (typeof data.message === 'string') {
      form.value.message = data.message
      if (data.message.length > 0) filled = true
    }
    if (typeof data.phone_numbers_text === 'string' && data.phone_numbers_text.trim()) {
      form.value.phone_numbers_text = data.phone_numbers_text.trim()
      filled = true
    }
    numberSource.value = 'manual'
    if (filled) {
      nextTick(() => {
        ElMessage.success(t('smsSend.approvalPrefillFromAudit'))
      })
    }
  } catch {
    /* 忽略损坏的 session 数据 */
  }
}

onMounted(() => {
  loadChannels(); loadStats(); updateTime(); checkAiConfig(); checkServices(); loadStoreProducts()
  timeInterval = window.setInterval(updateTime, 1000)
  consumeApprovalPrefill()
  void selectPrivateGroupFromRouteQuery()
})
onUnmounted(() => clearInterval(timeInterval))
</script>

<style scoped>
.send-page { width: 100%; min-height: 100%; }

.stats-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.stat-card { display: flex; align-items: center; gap: 14px; padding: 18px 20px; background: var(--bg-card); border: 1px solid var(--border-default); border-radius: 14px; transition: all 0.2s; }
.stat-card:hover { border-color: var(--border-hover); transform: translateY(-2px); }
.stat-icon { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; }
.stat-icon.today { background: rgba(102, 126, 234, 0.12); color: #667EEA; }
.stat-icon.success { background: rgba(56, 239, 125, 0.12); color: #38EF7D; }
.stat-icon.rate { background: rgba(255, 193, 7, 0.12); color: #FFC107; }
.stat-icon.cost { background: rgba(245, 87, 108, 0.12); color: #F5576C; }
.stat-info { display: flex; flex-direction: column; gap: 2px; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); }
.stat-label { font-size: 12px; color: var(--text-tertiary); }
.stat-label-hint {
  cursor: help;
  border-bottom: 1px dashed var(--text-tertiary);
}

.page-grid { display: grid; grid-template-columns: 1fr 320px; gap: 24px; }
.form-panel { display: flex; flex-direction: column; background: var(--bg-card); border: 1px solid var(--border-default); border-radius: 16px; overflow: hidden; }
.panel-header { padding: 20px 24px; border-bottom: 1px solid var(--border-default); }
.panel-title { font-size: 18px; font-weight: 600; color: var(--text-primary); margin: 0 0 4px; }
.panel-desc { font-size: 13px; color: var(--text-tertiary); margin: 0; }
.form-body { flex: 1; padding: 20px 24px; }
.field-group { margin-bottom: 18px; }
.field-label { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 8px; }
.field-label.required::before { content: '*'; color: #F5576C; }
.field-label .optional { font-weight: 400; font-size: 11px; color: var(--text-quaternary); margin-left: auto; }
.field-toolbar { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; flex-wrap: wrap; gap: 8px; }
.stats-info { font-size: 12px; color: var(--text-tertiary); }
.highlight { color: #FFC107; font-weight: 600; }
.toolbar-actions { display: flex; gap: 4px; }
.number-actions { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border-default); }
.action-group { display: flex; gap: 8px; }

/* 变量工具栏 */
.var-toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; padding: 8px 12px; background: var(--bg-input, #f5f7fa); border-radius: 10px 10px 0 0; border: 1px solid var(--border-default); border-bottom: none; }
.var-toolbar-left, .var-toolbar-right { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.toolbar-tip { font-size: 12px; color: var(--text-tertiary); white-space: nowrap; }

/* 变量预览 */
.var-preview { margin-top: 8px; padding: 10px 12px; background: rgba(102, 126, 234, 0.06); border: 1px dashed var(--border-default); border-radius: 8px; }
.preview-tag { font-size: 12px; color: var(--text-tertiary); }
.preview-msg { font-size: 13px; color: var(--text-primary); margin-top: 4px; line-height: 1.5; word-break: break-all; }
.preview-multi-hint { font-size: 11px; color: var(--el-color-warning); margin-top: 4px; }

/* 号码来源切换 */
.source-tabs { display: flex; gap: 10px; margin-bottom: 12px; }
.source-tab { display: flex; align-items: center; gap: 6px; padding: 10px 16px; border-radius: 10px; border: 1px solid var(--border-default); cursor: pointer; font-size: 13px; font-weight: 500; color: var(--text-secondary); transition: all 0.2s; background: var(--bg-input, #f9fafb); }
.source-tab:hover { border-color: var(--el-color-primary-light-5, #79bbff); }
.source-tab.active { border-color: var(--el-color-primary, #409eff); background: rgba(64, 158, 255, 0.06); color: var(--el-color-primary, #409eff); }

/* 数据商店区 */
.store-section { border: 1px solid var(--border-default); border-radius: 10px; padding: 14px; background: var(--bg-input, #f9fafb); }

/* 运营商筛选 */
.carrier-filter { margin-bottom: 12px; }
.carrier-label { font-size: 12px; font-weight: 500; color: var(--text-secondary); margin-bottom: 6px; display: block; }
.carrier-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.carrier-tag { display: inline-flex; align-items: center; gap: 4px; padding: 6px 16px; font-size: 13px; border-radius: 20px; border: 1px solid var(--border-default); background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); cursor: pointer; transition: all 0.15s; white-space: nowrap; }
.carrier-tag:hover { border-color: var(--el-color-primary-light-5, #79bbff); color: var(--el-color-primary, #409eff); }
.carrier-tag.active { border-color: var(--el-color-primary, #409eff); background: rgba(64, 158, 255, 0.1); color: var(--el-color-primary, #409eff); font-weight: 600; box-shadow: 0 0 0 1px var(--el-color-primary); }
.carrier-count { font-size: 11px; opacity: 0.6; margin-left: 4px; }
.sp-carrier-badge { display: inline-block; margin-left: 8px; padding: 1px 8px; border-radius: 10px; background: rgba(64, 158, 255, 0.15); color: var(--el-color-primary, #409eff); font-size: 11px; font-weight: 600; border: 1px solid rgba(64, 158, 255, 0.2); }

.store-products { max-height: 240px; overflow-y: auto; margin-bottom: 12px; }
.store-product-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 14px; border: 1px solid var(--border-default); border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all 0.15s; background: var(--bg-card, white); }
.store-product-item:hover { border-color: var(--el-color-primary-light-5, #79bbff); }
.store-product-item.selected { border-color: var(--el-color-primary, #409eff); background: rgba(64, 158, 255, 0.06); }
.sp-info { flex: 1; }
.sp-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.sp-meta { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; }
.sp-check { width: 22px; height: 22px; border-radius: 50%; background: var(--el-color-primary, #409eff); color: white; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
.sp-rating-badge { display: inline-flex; align-items: center; gap: 3px; background: #fdf6ec; color: #e6a23c; padding: 0 5px; border-radius: 3px; font-size: 11px; font-weight: 600; margin-left: 6px; }
.sp-rating-recent { color: #409eff; font-weight: 400; font-size: 10px; }
.store-quantity { display: flex; align-items: center; gap: 12px; padding-top: 12px; border-top: 1px dashed var(--border-default); flex-wrap: wrap; }
.store-quantity label { font-size: 13px; font-weight: 500; color: var(--text-secondary); }
.store-cost { font-size: 13px; color: var(--text-secondary); }
.store-cost strong { color: var(--el-color-success, #67c23a); font-size: 16px; }

/* 选项 */
.options-row { display: flex; gap: 16px; margin-bottom: 16px; }
.options-row > .field-group { flex: 1; min-width: 0; margin-bottom: 0; }
.options-row > .field-group .el-select { width: 100%; }
:deep(.channel-popper .el-select-dropdown__item) { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
:deep(.channel-popper .ch-opt-name) { color: var(--text-primary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:deep(.channel-popper .ch-opt-code) { color: var(--text-tertiary); font-size: 12px; flex-shrink: 0; }
.checkbox-options { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; margin-bottom: 20px; font-size: 13px; }
.schedule-picker { margin-left: 8px; }

:deep(.custom-input .el-input__wrapper), :deep(.custom-select .el-input__wrapper) { background: var(--bg-input) !important; border: 1px solid var(--border-default) !important; border-radius: 10px !important; box-shadow: none !important; }
:deep(.custom-textarea .el-textarea__inner) { background: var(--bg-input) !important; border: 1px solid var(--border-default) !important; border-radius: 10px !important; color: var(--text-primary) !important; font-size: 14px !important; line-height: 1.5 !important; }

.form-footer { display: flex; gap: 12px; margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-default); }
.btn-reset, .btn-send, .btn-audit { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px 20px; border-radius: 10px; font-size: 14px; font-weight: 500; cursor: pointer; border: none; transition: all 0.2s; }
.btn-reset { background: var(--bg-input); color: var(--text-secondary); border: 1px solid var(--border-default); }
.btn-reset:hover { background: var(--bg-hover); }
.btn-send { flex: 1; background: var(--gradient-primary); color: white; }
.btn-audit { background: var(--el-color-warning); color: white; }
.btn-audit:hover:not(:disabled) { opacity: 0.9; }
.btn-audit:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-send:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(102, 126, 234, 0.4); }
.btn-send:disabled { opacity: 0.5; cursor: not-allowed; }
.spinner { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.result-banner { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-radius: 10px; margin-top: 16px; }
.result-banner.success { background: rgba(56, 239, 125, 0.1); border: 1px solid rgba(56, 239, 125, 0.2); }
.result-banner.error { background: rgba(245, 87, 108, 0.1); border: 1px solid rgba(245, 87, 108, 0.2); }
.result-icon { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.result-banner.success .result-icon { background: rgba(56, 239, 125, 0.2); color: var(--success); }
.result-banner.error .result-icon { background: rgba(245, 87, 108, 0.2); color: var(--danger); }
.result-text { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--text-secondary); }
.result-text .result-title { color: var(--text-primary); }
.result-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }
.result-task-link { color: var(--el-color-primary); font-weight: 500; text-decoration: none; }
.result-task-link:hover { text-decoration: underline; }

.preview-panel { display: flex; flex-direction: column; }
.preview-title { font-size: 13px; font-weight: 500; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.08em; }
.preview-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 4px; }
.preview-theme-toggle { display: inline-flex; background: var(--bg-hover, #f0f2f5); border-radius: 8px; padding: 2px; gap: 2px; }
.preview-theme-toggle button { border: none; background: transparent; color: var(--text-secondary); font-size: 12px; font-weight: 500; padding: 4px 12px; border-radius: 6px; cursor: pointer; transition: all 0.15s; }
.preview-theme-toggle button.active { background: var(--el-color-primary, #667eea); color: #fff; }

.preview-sender-field { display: flex; align-items: center; gap: 8px; margin: 10px 0 4px; }
.psf-label { font-size: 12px; color: var(--text-tertiary); white-space: nowrap; }
.psf-input { flex: 1; min-width: 0; background: var(--bg-hover, #f0f2f5); border: 1px solid var(--border-color, #e0e0e6); border-radius: 8px; padding: 6px 10px; font-size: 13px; color: var(--text-primary); outline: none; transition: border-color 0.15s; }
.psf-input:focus { border-color: var(--el-color-primary, #667eea); }
.preview-tz-hint { display: flex; align-items: center; gap: 5px; margin: 4px 0 2px; font-size: 11px; color: var(--text-tertiary); }

.preview-actions { display: flex; align-items: center; gap: 8px; }
.preview-shot-btn { display: inline-flex; align-items: center; gap: 5px; border: 1px solid var(--border-color, #dcdfe6); background: var(--bg-hover, #f5f7fa); color: var(--text-secondary); font-size: 12px; font-weight: 500; padding: 4px 10px; border-radius: 8px; cursor: pointer; transition: all 0.15s; }
.preview-shot-btn:hover:not(:disabled) { border-color: var(--el-color-primary, #667eea); color: var(--el-color-primary, #667eea); }
.preview-shot-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* 气泡内自动识别的链接(下划线) */
.msg-link { color: inherit; text-decoration: underline; text-underline-offset: 2px; cursor: pointer; }
.msg-link.ios { color: #007AFF; }

.phone-container { flex: 1; display: flex; justify-content: center; padding: 8px; }

/* ===== iOS · 真实短信截图(浅色,无边框机身) ===== */
.iphone-l {
  width: 290px; height: 600px; background: #fff; border-radius: 30px; overflow: hidden; position: relative;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  box-shadow: 0 0 0 1px rgba(0,0,0,0.06), 0 18px 50px rgba(0, 0, 0, 0.35);
}
.iphone-l-screen { width: 100%; height: 100%; background: #fff; display: flex; flex-direction: column; }
.il-status-bar { display: flex; justify-content: space-between; align-items: center; padding: 13px 24px 3px 26px; height: 40px; box-sizing: border-box; color: #000; }
.il-time { display: inline-flex; align-items: center; gap: 5px; font-size: 15px; font-weight: 600; letter-spacing: 0.2px; font-variant-numeric: tabular-nums; }
.il-icons { display: flex; align-items: center; gap: 6px; }
.il-battery { display: flex; align-items: center; }
.il-battery-body { width: 22px; height: 11px; border: 1px solid rgba(0,0,0,0.35); border-radius: 3.5px; padding: 1.5px; box-sizing: border-box; }
.il-battery-fill { width: 62%; height: 100%; background: #000; border-radius: 1.5px; }
.il-battery-cap { width: 1.5px; height: 4px; background: rgba(0,0,0,0.35); border-radius: 0 2px 2px 0; margin-left: 1px; }

/* 会话顶栏 */
.il-nav { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; padding: 2px 10px 8px; border-bottom: 0.5px solid #E3E3E6; }
.il-back { display: flex; align-items: center; gap: 4px; justify-self: start; }
.il-unread { min-width: 19px; height: 19px; padding: 0 5px; box-sizing: border-box; background: #007AFF; border-radius: 10px; color: #fff; font-size: 12px; font-weight: 500; display: flex; align-items: center; justify-content: center; }
.il-contact { display: flex; flex-direction: column; align-items: center; gap: 3px; }
.il-avatar { width: 48px; height: 48px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 20px; font-weight: 500; overflow: hidden; }
.il-avatar svg { margin-bottom: -8px; }
.il-name-row { display: flex; align-items: center; gap: 3px; }
.il-name { font-size: 12px; color: #000; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.il-nav-right { justify-self: end; }

/* 会话区(消息顶部对齐,下方留白) */
.il-chat { flex: 1; padding: 10px 14px 6px; display: flex; flex-direction: column; overflow: hidden; }
.il-date { display: flex; flex-direction: column; align-items: center; gap: 1px; font-size: 11px; color: #8A8A8E; margin: 2px 0 14px; }
.il-date span:first-child { font-weight: 500; color: #7C7C81; }
.il-bubble { position: relative; align-self: flex-start; max-width: 76%; background: #E9E9EB; color: #000; padding: 8px 13px; border-radius: 18px; font-size: 15.5px; line-height: 1.32; word-break: break-word; }
.il-bubble::before { content: ''; position: absolute; z-index: 0; bottom: 0; left: -7px; height: 19px; width: 19px; background: #E9E9EB; border-bottom-right-radius: 15px; }
.il-bubble::after { content: ''; position: absolute; z-index: 1; bottom: 0; left: -11px; width: 11px; height: 19px; background: #fff; border-bottom-right-radius: 11px; }
.il-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: #C4C4C8; font-size: 13px; }

/* 输入栏 */
.il-input-bar { display: flex; align-items: center; gap: 9px; padding: 6px 12px 6px; }
.il-plus { width: 32px; height: 32px; border-radius: 50%; background: #E4E4E9; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.il-field { flex: 1; display: flex; align-items: center; justify-content: space-between; border: 1px solid #D3D3D8; border-radius: 17px; padding: 6px 8px 6px 13px; font-size: 15px; color: #A2A2A8; }
.il-home { width: 128px; height: 5px; background: #000; border-radius: 3px; margin: 6px auto 9px; flex-shrink: 0; }

/* ===== Android 机身(居中挖孔) ===== */
.android-phone {
  width: 290px; height: 600px; background: #0c1524; border-radius: 34px; padding: 6px; position: relative;
  font-family: 'Roboto', 'Google Sans', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Noto Sans', sans-serif;
  box-shadow:
    0 0 0 1.5px #263042,
    0 0 0 2.4px rgba(255, 255, 255, 0.14),
    0 24px 60px rgba(0, 0, 0, 0.5);
}
/* 右侧电源/音量键 */
.android-phone::after { content: ''; position: absolute; right: -3px; top: 150px; width: 3px; height: 40px; background: #263042; border-radius: 0 2px 2px 0; box-shadow: 0 -58px 0 #263042; }
.android-screen { width: 100%; height: 100%; background: #f7f9fc; border-radius: 28px; overflow: hidden; display: flex; flex-direction: column; position: relative; }

/* 居中挖孔摄像头 */
.punch-hole { position: absolute; top: 11px; left: 50%; transform: translateX(-50%); width: 9px; height: 9px; border-radius: 50%; background: radial-gradient(circle at 35% 35%, #223, #000 70%); z-index: 100; box-shadow: 0 0 0 1.5px rgba(0,0,0,0.35); }

/* 状态栏 */
.gm-status-bar { display: flex; justify-content: space-between; align-items: center; padding: 9px 15px 5px; height: 30px; box-sizing: border-box; background: #f7f9fc; color: #202124; }
.gm-sb-time { font-size: 13px; font-weight: 600; letter-spacing: 0.2px; font-variant-numeric: tabular-nums; }
.gm-sb-right { display: flex; align-items: center; gap: 4px; }
.gm-sb-net { font-size: 9px; font-weight: 700; letter-spacing: 0.3px; }
.gm-battery { display: flex; align-items: center; gap: 2px; }
.gm-battery-pct { font-size: 10px; font-weight: 600; font-variant-numeric: tabular-nums; }
.gm-battery-body { width: 20px; height: 10.5px; border: 1px solid #202124; border-radius: 3px; padding: 1.3px; box-sizing: border-box; }
.gm-battery-fill { height: 100%; background: #202124; border-radius: 1px; }
.gm-battery-cap { width: 1.4px; height: 4px; background: #202124; border-radius: 0 2px 2px 0; margin-left: 0.8px; }

/* 顶栏 */
.gm-appbar { display: flex; align-items: center; gap: 11px; padding: 7px 14px 9px; background: #f7f9fc; }
.gm-back { flex-shrink: 0; }
.gm-avatar { width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 14px; font-weight: 500; flex-shrink: 0; overflow: hidden; }
.gm-sender { flex: 1; font-size: 16px; font-weight: 500; color: #1f1f1f; letter-spacing: 0.2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gm-call, .gm-more { flex-shrink: 0; }

/* 会话区 */
.gm-conversation { flex: 1; display: flex; flex-direction: column; padding: 0 12px; overflow: hidden; min-height: 0; background: #f7f9fc; }
.gm-spacer { flex: 1; min-height: 8px; }

/* 保存联系人建议卡 */
.gm-save-card { background: #eceef4; border-radius: 18px; padding: 12px 12px 10px; margin: 8px 2px 0; }
.gm-save-top { display: flex; align-items: flex-start; gap: 11px; }
.gm-save-icon { width: 34px; height: 34px; border-radius: 50%; background: #1a73e8; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.gm-save-text { flex: 1; min-width: 0; }
.gm-save-title { font-size: 13.5px; font-weight: 600; color: #1f1f1f; line-height: 1.3; }
.gm-save-sub { font-size: 12px; color: #5f6368; margin-top: 2px; line-height: 1.3; }
.gm-save-x { flex-shrink: 0; margin-top: 2px; }
.gm-save-actions { display: flex; justify-content: flex-end; gap: 22px; margin-top: 8px; padding-right: 4px; }
.gm-save-actions span { font-size: 13px; font-weight: 600; color: #1a73e8; }

/* 时间 / 会话副标题 / 未读分隔线 */
.gm-time-center { text-align: center; font-size: 11px; color: #5f6368; margin: 6px 0 8px; }
.gm-texting-with { text-align: center; font-size: 11.5px; color: #5f6368; margin: 0 0 12px; padding: 0 8px; line-height: 1.35; }
.gm-unread { display: flex; align-items: center; text-align: center; margin: 2px 0 8px; }
.gm-unread::before, .gm-unread::after { content: ''; flex: 1; height: 1px; background: #3f6ad8; opacity: 0.5; }
.gm-unread span { padding: 0 10px; font-size: 11px; color: #3f6ad8; font-weight: 500; }

/* 收信气泡 */
.gm-bubble { align-self: flex-start; max-width: 82%; background: #e7e9f1; color: #1f1f1f; padding: 9px 14px; border-radius: 20px 20px 20px 6px; font-size: 14.5px; line-height: 1.4; word-break: break-word; }

/* 链接预览加载卡(品牌发送人) */
.gm-link-card { align-self: flex-start; max-width: 82%; width: 236px; margin-top: 4px; box-sizing: border-box; border: 1px solid #dadce0; border-radius: 14px; background: #fff; padding: 18px 14px; display: flex; flex-direction: column; align-items: center; gap: 9px; }
.gm-link-card span { font-size: 12.5px; color: #5f6368; }
.gm-time-left { align-self: flex-start; font-size: 11px; color: #5f6368; margin: 8px 2px 4px; }

/* 业务提示条(品牌单向发送人,不可回复) */
.gm-footer { margin: 4px 10px 8px; padding: 9px 14px; background: #eceef4; border-radius: 16px; font-size: 11.5px; line-height: 1.45; color: #5f6368; text-align: center; }
.gm-footer a { color: #1a73e8; text-decoration: none; }

/* 智能回复建议 */
.gm-replies { display: flex; flex-wrap: wrap; gap: 7px; margin: 10px 0 2px; }
.gm-reply-chip { border: 1px solid #c9ccd6; border-radius: 16px; padding: 6px 15px; font-size: 13px; color: #1a73e8; font-weight: 500; background: transparent; }
.gm-reply-emoji { padding: 4px 10px; font-size: 15px; }

.gm-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: #bcc0c4; font-size: 13px; }
.empty-icon { opacity: 0.5; }

/* 输入栏 */
.gm-inputbar { display: flex; align-items: center; gap: 8px; padding: 6px 12px 8px; background: #f7f9fc; }
.gm-input-plus { width: 30px; height: 30px; border-radius: 50%; background: #e4e7ee; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.gm-input-field { flex: 1; display: flex; align-items: center; justify-content: space-between; background: #eceef4; border-radius: 20px; padding: 8px 12px; min-width: 0; }
.gm-input-field > span { font-size: 14px; color: #5f6368; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gm-input-icons { display: flex; align-items: center; gap: 10px; flex-shrink: 0; padding-left: 8px; }
.gm-input-mic { width: 38px; height: 38px; border-radius: 50%; background: #e9ddff; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }

/* Android 三键导航 */
.gm-navbar { display: flex; align-items: center; justify-content: space-around; padding: 9px 0 11px; background: #f7f9fc; }

.empty-drafts { text-align: center; padding: 40px; color: var(--text-tertiary); }
.draft-list { max-height: 400px; overflow-y: auto; }
.draft-item { display: flex; align-items: center; gap: 12px; padding: 12px; border-radius: 8px; cursor: pointer; transition: background 0.2s; }
.draft-item:hover { background: var(--bg-hover); }
.draft-content { flex: 1; font-size: 14px; color: var(--text-primary); }
.draft-time { font-size: 12px; color: var(--text-quaternary); }

/* 生成结果 */
.gen-results { margin-top: 16px; max-height: 300px; overflow-y: auto; }
.gen-result-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; border: 1px solid var(--el-border-color-lighter, #ebeef5); border-radius: 6px; margin-bottom: 8px; cursor: pointer; transition: all 0.15s; }
.gen-result-item:hover { border-color: var(--el-color-primary-light-5, #79bbff); background: rgba(64, 158, 255, 0.04); }
.gen-result-item.selected { border-color: var(--el-color-primary, #409eff); background: rgba(64, 158, 255, 0.06); }
.gen-idx { flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%; background: var(--el-fill-color, #f0f2f5); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; color: var(--text-tertiary); }
.gen-result-item.selected .gen-idx { background: var(--el-color-primary, #409eff); color: white; }
.gen-body { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.gen-text { font-size: 13px; line-height: 1.5; flex: 1; word-break: break-word; white-space: pre-wrap; }
.gen-zh { font-size: 12px; line-height: 1.4; color: var(--el-text-color-secondary); word-break: break-word; padding-left: 8px; border-left: 2px solid var(--el-border-color, #dcdfe6); }
.gen-char-count { flex-shrink: 0; font-size: 11px; color: var(--el-text-color-secondary); white-space: nowrap; margin-left: auto; }

/* 字符计数 & 敏感词提示 */
.msg-meta-bar { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; font-size: 12px; }
.char-counter { color: var(--el-text-color-secondary); }
.char-counter.over-limit { color: var(--el-color-warning, #e6a23c); font-weight: 500; }
.sensitive-warn { color: var(--el-color-danger, #f56c6c); font-weight: 500; }
.banned-word-warn { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; font-size: 12px; color: var(--el-color-danger); padding: 6px 10px; background: rgba(245, 87, 108, 0.06); border-radius: 6px; margin-top: 4px; }
.bw-icon { margin-right: 4px; }
.bw-highlight { background: rgba(245, 87, 108, 0.15); color: var(--el-color-danger); padding: 1px 6px; border-radius: 3px; font-weight: 600; }
.bw-hint { color: var(--el-text-color-secondary); font-size: 11px; margin-left: 4px; }

/* 大批量异步进度 */
.async-batch-progress { padding: 12px 16px; background: var(--el-fill-color-light, #f5f7fa); border-radius: 8px; margin-bottom: 12px; }
.async-batch-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; font-weight: 500; }
.async-batch-pct { color: var(--el-color-primary); font-weight: 700; }
.async-batch-tip { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 4px; }

/* 自定义变量对话框 */
.cv-list { margin-bottom: 16px; }
.cv-item { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cv-eq { font-size: 14px; color: var(--el-text-color-secondary); font-weight: 600; }
.cv-add { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding-top: 16px; border-top: 1px dashed var(--el-border-color-lighter, #ebeef5); }

/* 生成结果头部 */
.gen-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5); }
.gen-header-actions { margin-left: auto; display: flex; align-items: center; gap: 4px; }
.ai-original-tools { margin-top: 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ai-original-tools-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.gen-selected-tip { font-size: 12px; color: var(--el-text-color-secondary); }

/* 智能生成：语言自动识别与按国家匹配 */
.lang-smart-row { margin-top: 8px; }
.lang-smart-actions { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 4px; }
.lang-smart-hint { margin: 6px 0 0; font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.4; }

/* 多文案配置 */
.multi-msg-config { margin-top: 16px; padding: 12px; background: rgba(64, 158, 255, 0.04); border: 1px solid var(--el-border-color-lighter, #ebeef5); border-radius: 8px; }
.mmc-title { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
.mmc-desc { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.mmc-row { display: flex; align-items: flex-start; gap: 8px; padding: 4px 0; font-size: 13px; }
.mmc-label { font-weight: 500; white-space: nowrap; min-width: 52px; }
.mmc-preview { color: var(--el-text-color-secondary); word-break: break-word; white-space: pre-wrap; flex: 1; }
.mmc-summary { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--el-border-color-lighter, #ebeef5); font-size: 13px; font-weight: 500; color: var(--el-color-primary, #409eff); }

/* 多文案提示横幅 */
.multi-msg-banner { margin-top: 8px; padding: 10px 12px; background: rgba(64, 158, 255, 0.06); border: 1px solid rgba(64, 158, 255, 0.2); border-radius: 8px; }
.mmb-header { display: flex; justify-content: space-between; align-items: center; font-size: 13px; margin-bottom: 6px; }
.mmb-header strong { color: var(--el-color-primary, #409eff); }
.mmb-actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.mmb-list { display: flex; flex-direction: column; gap: 4px; }
.mmb-item { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; padding: 4px 8px; border-radius: 4px; background: var(--el-fill-color-light, #f5f7fa); }
.mmb-item.current { background: rgba(64, 158, 255, 0.1); }
.mmb-idx { width: 18px; height: 18px; border-radius: 50%; background: var(--el-color-primary, #409eff); color: white; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; flex-shrink: 0; }
.mmb-body { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.mmb-text { word-break: break-word; white-space: pre-wrap; color: var(--el-text-color-secondary); }
.mmb-zh { font-size: 11px; line-height: 1.4; color: var(--el-text-color-secondary); word-break: break-word; padding-left: 6px; border-left: 2px solid var(--el-border-color, #dcdfe6); }
.mmb-char-count { flex-shrink: 0; font-size: 11px; color: var(--el-text-color-secondary); white-space: nowrap; }
.mmb-copy-btn { flex-shrink: 0; padding: 0 2px; height: 18px; }

.slide-enter-active, .slide-leave-active { transition: all 0.3s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(-10px); }

@media (max-width: 1200px) {
  .stats-cards { grid-template-columns: repeat(2, 1fr); }
  .page-grid { grid-template-columns: 1fr; }
  .preview-panel { display: none; }
}

/* ===== 手机端（≤768px）适配 ===== */
@media (max-width: 768px) {
  /* 顶部 KPI：2 列保持密度，单卡更紧凑 */
  .stats-cards { grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 14px; }
  .stat-card { padding: 12px 14px; gap: 10px; border-radius: 12px; }
  .stat-icon { width: 36px; height: 36px; border-radius: 10px; }
  .stat-value { font-size: 18px; }
  .stat-label { font-size: 11px; }

  /* 表单容器内边距收紧 */
  .panel-header { padding: 14px 16px; }
  .panel-title { font-size: 16px; }
  .form-body { padding: 14px 16px; }
  .field-group { margin-bottom: 14px; }

  /* 字段堆叠 */
  .options-row { flex-direction: column; gap: 14px; }
  .options-row > .field-group { width: 100%; }
  .number-actions { flex-direction: column; align-items: stretch; gap: 8px; }
  .action-group { flex-wrap: wrap; gap: 4px 12px; }
  .source-tabs { flex-direction: column; gap: 8px; }
  .source-tab { padding: 12px 14px; justify-content: flex-start; }

  /* 变量工具栏：内距收紧，按钮换行 */
  .var-toolbar { padding: 6px 10px; gap: 6px; }
  .var-toolbar-left, .var-toolbar-right { gap: 4px; }

  /* 计划发送：在自己一行（避免 picker 被挤压） */
  .checkbox-options { gap: 12px; }
  .schedule-picker { margin-left: 0; width: 100%; }
  .schedule-picker :deep(.el-date-editor) { width: 100% !important; }

  /* 私有库 / 数据商店内的数量输入：占满 */
  .store-quantity { gap: 8px; }
  .store-quantity :deep(.el-input-number) { width: 100% !important; }
  .store-cost { width: 100%; line-height: 1.6; }
  .store-cost > span[style*="margin-left"] { display: block; margin-left: 0 !important; padding-top: 4px; }

  /* 运营商筛选：横向滚动避免高度爆炸 */
  .carrier-tags > .tag-row {
    flex-wrap: nowrap !important;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 4px;
  }
  .carrier-tag { flex-shrink: 0; }

  /* 底部操作按钮：主按钮独占一行且更高，便于拇指点击 */
  .form-footer {
    flex-direction: column-reverse;
    gap: 10px;
    padding-top: 16px;
    margin-top: 16px;
  }
  .form-footer > .btn-send { width: 100%; min-height: 48px; font-size: 15px; }
  .form-footer > .btn-audit { width: 100%; min-height: 44px; }
  .form-footer > .btn-reset { width: 100%; min-height: 40px; }

  /* 发送结果横幅：减小内距 */
  .result-banner { padding: 12px; }
}

/* ========== 失败原因汇总 ========== */
.failure-summary {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed rgba(var(--el-color-danger-rgb, 245, 108, 108), 0.3);
}
.failure-summary-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-danger);
  margin-bottom: 6px;
}
.failure-group {
  margin-bottom: 6px;
  font-size: 13px;
}
.failure-group:last-child { margin-bottom: 0; }
.failure-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.failure-count {
  display: inline-block;
  min-width: 38px;
  padding: 1px 8px;
  background: var(--el-color-danger-light-9, #fef0f0);
  color: var(--el-color-danger);
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
}
.failure-reason {
  color: var(--el-text-color-regular);
  flex: 1;
  min-width: 0;
  word-break: break-word;
}
.failure-phones {
  margin-top: 6px;
  padding: 8px 10px;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  max-height: 240px;
  overflow-y: auto;
}
.failure-phone-chip {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 2px 6px;
  background: var(--el-bg-color, #fff);
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter, #eee);
}
.failure-phones-more {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  align-self: center;
}

@media (max-width: 380px) {
  .stats-cards { grid-template-columns: 1fr; }
}

/* ========== 自定义变量对话框 ========== */
.cv-empty { margin-bottom: 12px; }
.cv-empty-desc { font-size: 13px; color: var(--el-text-color-secondary); margin: 0 0 12px; line-height: 1.6; }
.cv-empty-desc code { background: var(--el-fill-color, #f5f7fa); padding: 1px 5px; border-radius: 3px; font-size: 12px; color: var(--el-color-primary); }
.cv-quick-tags { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cv-quick-label { font-size: 12px; color: var(--el-text-color-placeholder); }
.cv-quick-tag { cursor: pointer; transition: all 0.15s; }
.cv-quick-tag:hover { transform: scale(1.05); }

.cv-item-block { margin-bottom: 14px; padding: 10px 12px; background: var(--el-fill-color-light, #f5f7fa); border-radius: 8px; }
.cv-item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cv-item-value { }
.cv-multi-info { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 4px; }
.cv-footer { display: flex; justify-content: space-between; align-items: center; width: 100%; }

/* 变量教程（轻量） */
.guide-lite { }
.guide-lite-section { margin-bottom: 16px; }
.guide-lite-section:last-child { margin-bottom: 0; }
.guide-lite-title { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 6px; }
.guide-lite-section p { font-size: 13px; color: var(--el-text-color-regular); line-height: 1.6; margin: 0 0 8px; }
.guide-lite-section code { background: var(--el-fill-color, #f5f7fa); padding: 1px 5px; border-radius: 3px; font-size: 12px; color: var(--el-color-primary); }
.guide-lite-example { padding: 10px 12px; background: var(--el-fill-color-light, #f5f7fa); border-radius: 8px; font-size: 12px; line-height: 1.8; }
.guide-lite-arrow { color: var(--el-text-color-placeholder); text-align: center; font-size: 11px; }
.guide-lite-example strong { color: var(--el-color-success); }
</style>
