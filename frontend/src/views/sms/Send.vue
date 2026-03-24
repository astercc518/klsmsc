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
          <span class="stat-label">{{ $t('smsSend.successRate') }}</span>
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
                  <span class="toolbar-tip">系统变量:</span>
                  <el-button v-for="v in VARIABLES" :key="v.tag" size="small" @click="insertVariable(v.tag)">{{ v.label }}</el-button>
                  <el-divider direction="vertical" />
                  <el-button v-for="cv in customVars" :key="cv.name" size="small" type="warning" @click="insertVariable(`{${cv.name}}`)">
                    {{ cv.name }}
                  </el-button>
                  <el-button size="small" type="info" plain @click="showCustomVarDialog = true">+ 自定义</el-button>
                </div>
                <div class="var-toolbar-right">
                  <el-button size="small" type="success" @click="showTemplateEngine = true">
                    <el-icon><MagicStick /></el-icon> 智能生成
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
                <span class="char-counter" :class="{ 'over-limit': form.message.length > 160 }">
                  {{ form.message.length }} 字符
                  <template v-if="form.message.length > 160"> (超过160字符可能被拆分为多条)</template>
                </span>
                <span v-if="hasSensitiveWord" class="sensitive-warn">含敏感词，发送时将自动替换为 ***</span>
              </div>

              <!-- 变量预览 -->
              <div v-if="hasVariables" class="var-preview">
                <span class="preview-tag">预览效果:</span>
                <div class="preview-msg">{{ previewSms }}</div>
              </div>

              <!-- 多文案提示 -->
              <div v-if="multiMessages.length > 1" class="multi-msg-banner">
                <div class="mmb-header">
                  <span>已加载 <strong>{{ multiMessages.length }}</strong> 条文案，发送时均匀分配号码</span>
                  <el-button link type="danger" size="small" @click="multiMessages = []">清除多文案</el-button>
                </div>
                <div class="mmb-list">
                  <div v-for="(msg, idx) in multiMessages" :key="idx" class="mmb-item" :class="{ current: idx === 0 }">
                    <span class="mmb-idx">{{ idx + 1 }}</span>
                    <span class="mmb-text">{{ msg.length > 50 ? msg.substring(0, 50) + '...' : msg }}</span>
                  </div>
                </div>
              </div>

              <div class="field-toolbar">
                <div class="stats-info">
                  {{ $t('smsSend.totalChars') }} <span class="highlight">{{ form.message.length }}</span> {{ $t('smsSend.chars') }}，
                  {{ $t('smsSend.estimatedParts') }}：<span class="highlight">{{ estimatedParts }}</span> {{ $t('smsSend.parts') }}
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
              </div>

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
                      费用: 数据 ${{ storeDataCost.toFixed(2) }}
                      <template v-if="storeSmsCost > 0"> + 短信 ${{ storeSmsCost.toFixed(2) }}</template>
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
                <el-input
                  v-model="form.sender_id"
                  :placeholder="$t('smsSend.senderIdPlaceholder')"
                  size="default"
                  class="custom-input"
                />
              </div>
            </div>

            <!-- 4. 其他选项 -->
            <div class="checkbox-options">
              <el-checkbox v-if="numberSource === 'manual'" v-model="form.resetOnlyNumbers">
                {{ $t('smsSend.resetNumbersOnly') }}
              </el-checkbox>
              
              <el-checkbox v-if="numberSource === 'manual'" v-model="form.isScheduled">
                {{ $t('smsSend.scheduleSend') }}
              </el-checkbox>
              
              <div v-if="form.isScheduled && numberSource === 'manual'" class="schedule-picker">
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
              <!-- 单条时可提交审核 -->
              <button v-if="numberSource === 'manual' && numberCount === 1" type="button" class="btn-audit" :disabled="loading || !form.phone_numbers_text || !form.message || approvalSubmitting" @click="handleSubmitApproval">
                <template v-if="!approvalSubmitting">📋 提交审核</template>
                <template v-else>提交中...</template>
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
                    <span v-else-if="result.success && result.message">{{ result.message }}</span>
                    <span v-else-if="!result.success">{{ result.error?.message || result.message }}</span>
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
        </div>
        
        <div class="phone-container">
          <div class="iphone">
            <div class="dynamic-island"></div>
            
            <div class="iphone-screen">
              <div class="ios-status-bar">
                <span class="time">{{ currentTime }}</span>
                <div class="status-icons">
                  <div class="battery">
                    <div class="battery-body">
                      <div class="battery-level"></div>
                    </div>
                    <div class="battery-cap"></div>
                  </div>
                </div>
              </div>
              
              <div class="ios-messages">
                <div class="ios-nav">
                  <div class="nav-back">
                    <svg width="10" height="18" viewBox="0 0 10 18" fill="none">
                      <path d="M9 1L1 9L9 17" stroke="#007AFF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </div>
                  <div class="nav-contact">
                    <div class="contact-avatar-ios">
                      <span>{{ senderInitial }}</span>
                    </div>
                    <div class="contact-info">
                      <span class="contact-name">{{ senderDisplay }}</span>
                      <span class="contact-label">{{ $t('menu.smsBusiness') }}</span>
                    </div>
                  </div>
                </div>
                
                <div class="ios-chat">
                  <div class="chat-date">{{ currentDate }}</div>
                  
                  <div class="ios-bubble" v-if="form.message">
                    <div class="bubble-text">{{ hasVariables ? previewSms : form.message }}</div>
                    <div class="bubble-meta">
                      <span>{{ currentTime }}</span>
                    </div>
                  </div>
                  
                  <div class="empty-chat" v-else>
                    <div class="empty-icon">
                      <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                        <path d="M42 6H6C4.34 6 3 7.34 3 9V33C3 34.66 4.34 36 6 36H12V45L24 36H42C43.66 36 45 34.66 45 33V9C45 7.34 43.66 6 42 6Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
                      </svg>
                    </div>
                    <span>{{ $t('smsSend.enterToPreview') }}</span>
                  </div>
                </div>
                
                <div class="ios-input-bar">
                  <div class="input-bubble">
                    <span>{{ $t('menu.sms') }}</span>
                  </div>
                </div>
              </div>
            </div>
            
            <div class="home-indicator"></div>
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
    <el-dialog v-model="showCustomVarDialog" title="自定义变量" width="520px" destroy-on-close>
      <p style="font-size: 13px; color: var(--el-text-color-secondary); margin: 0 0 16px;">
        自定义变量会在发送时统一替换为设定的值。变量名不含大括号。
      </p>

      <!-- 已有变量列表 -->
      <div v-if="customVars.length" class="cv-list">
        <div v-for="(cv, idx) in customVars" :key="idx" class="cv-item">
          <el-tag closable @close="removeCustomVar(idx)">{{ '{' + cv.name + '}' }}</el-tag>
          <span class="cv-eq">=</span>
          <el-input v-model="cv.value" size="small" style="flex: 1" placeholder="替换值" />
        </div>
      </div>

      <el-empty v-if="customVars.length === 0" description="暂无自定义变量" :image-size="50" />

      <!-- 新增变量 -->
      <div class="cv-add">
        <el-input v-model="newVarName" size="small" placeholder="变量名，如：公司名" style="width: 140px" @keyup.enter="addCustomVar" />
        <el-input v-model="newVarValue" size="small" placeholder="替换值，如：ABC科技" style="flex: 1" @keyup.enter="addCustomVar" />
        <el-button size="small" type="primary" @click="addCustomVar" :disabled="!newVarName.trim()">添加</el-button>
      </div>

      <template #footer>
        <el-button @click="showCustomVarDialog = false">关闭</el-button>
        <el-button type="primary" @click="saveCustomVars">保存</el-button>
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
          <span class="mmc-preview">{{ tplResults[idx]?.substring(0, 30) }}...</span>
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

    <!-- ========== AI 生成对话框 ========== -->
    <el-dialog v-model="showAiDialog" title="AI 智能生成短信文案" width="680px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="生成方式">
          <el-radio-group v-model="aiForm.mode">
            <el-radio value="prompt">自由描述</el-radio>
            <el-radio value="rewrite" :disabled="!form.message.trim()">基于当前文案改写</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="aiForm.mode === 'prompt'">
          <el-form-item label="描述你的需求">
            <el-input v-model="aiForm.prompt" type="textarea" :rows="3" placeholder="如：巴西博彩推广短信，吸引用户注册，风格热情" />
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="原始文案（AI 将基于此改写多个变体）">
            <el-input :model-value="form.message" type="textarea" :rows="2" disabled />
          </el-form-item>
          <el-form-item label="改写要求（可选）">
            <el-input v-model="aiForm.rewriteHint" placeholder="如：换几种不同的表达风格" />
          </el-form-item>
        </template>
        <el-form-item label="目标国家（可选）">
          <el-select
            v-model="aiGenCountryIso"
            filterable
            clearable
            placeholder="选择后显示该国主要语言，并同步生成语言"
            style="width: 100%"
            @change="onAiGenCountryChange"
          >
            <el-option
              v-for="c in countrySelectOptions"
              :key="c.iso"
              :label="`${c.name} (+${c.dial})`"
              :value="c.iso"
            />
          </el-select>
          <p v-if="aiCountryHint" class="lang-smart-hint">{{ aiCountryHint }}</p>
        </el-form-item>
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
        <el-button type="primary" @click="generateFromAi" :loading="aiGenerating" :disabled="aiForm.mode === 'prompt' && !aiForm.prompt.trim()">
          <el-icon><MagicStick /></el-icon> 调用 AI 生成
        </el-button>
      </el-form>

      <div v-if="aiResults.length" class="gen-results">
        <div class="gen-header">
          <el-checkbox v-model="aiSelectAll" @change="toggleAiSelectAll">全选</el-checkbox>
          <span class="gen-selected-tip">已选 {{ aiSelectedSet.size }} 条</span>
        </div>
        <div v-for="(msg, idx) in aiResults" :key="idx" class="gen-result-item" :class="{ selected: aiSelectedSet.has(idx) }" @click="toggleAiSelect(idx)">
          <el-checkbox :model-value="aiSelectedSet.has(idx)" @click.stop @change="toggleAiSelect(idx)" />
          <span class="gen-idx">{{ idx + 1 }}</span>
          <span class="gen-text">{{ msg }}</span>
          <span class="gen-char-count">{{ msg.length }}字符</span>
        </div>
      </div>

      <div v-if="aiSelectedSet.size > 1" class="multi-msg-config">
        <div class="mmc-title">多文案发送分配</div>
        <div class="mmc-row" v-for="idx in [...aiSelectedSet]" :key="idx">
          <span class="mmc-label">文案 {{ idx + 1 }}:</span>
          <span class="mmc-preview">{{ aiResults[idx]?.substring(0, 30) }}...</span>
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
import type { FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { sendBatchSMS, submitSmsApproval } from '@/api/sms'
import { getChannels } from '@/api/channel'
import { getDataProducts, buyAndSend, getCarriers, type DataProduct } from '@/api/data'
import { getAiConfig, generateSmsContent } from '@/api/ai'
import request from '@/api/index'
import { COUNTRY_LIST, findCountryByIso } from '@/constants/countries'

const { t } = useI18n()

// ============ 常量 ============

const VARIABLES = [
  { tag: '{序号}', label: '序号' },
  { tag: '{国家}', label: '国家' },
  { tag: '{日期}', label: '日期' },
  { tag: '{随机码}', label: '随机码' },
  { tag: '{号码}', label: '号码' },
]

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

// 敏感词列表（发送前自动过滤替换）
const SENSITIVE_WORDS = [
  'casino', 'gambling', 'porn', 'sex', 'drug', 'kill', 'bomb', 'terror',
  '赌博', '色情', '毒品', '暴力', '杀', '炸弹', '恐怖',
  'free money', 'dinero gratis', 'dinheiro grátis',
]

// 去除 emoji 的工具函数
function stripEmoji(str: string): string {
  return str.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{27BF}\u{FE00}-\u{FE0F}\u{1F900}-\u{1F9FF}\u{200D}\u{20E3}\u{2702}-\u{27B0}\u{E0020}-\u{E007F}]/gu, '').replace(/\s{2,}/g, ' ').trim()
}

// 敏感词检测 & 替换
function sanitizeMessage(msg: string): string {
  let result = msg
  for (const w of SENSITIVE_WORDS) {
    const regex = new RegExp(w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')
    result = result.replace(regex, '***')
  }
  return result
}

// 截断到指定字符数
function truncateToLimit(msg: string, maxLen: number): string {
  return msg.length > maxLen ? msg.substring(0, maxLen) : msg
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
const channels = ref<any[]>([])
const channelBound = ref(false)
const currentTime = ref('')
const currentDate = ref('')
const sendProgress = ref(0)
const fileInputRef = ref<HTMLInputElement>()
const fileAccept = ref('.txt')
const draftDialogVisible = ref(false)
const drafts = ref<{ content: string; time: string }[]>([])
const msgInputRef = ref<any>(null)
const cursorPos = ref(0)

// 自定义变量
interface CustomVar { name: string; value: string }
const customVars = ref<CustomVar[]>(loadCustomVarsFromStorage())
const showCustomVarDialog = ref(false)
const newVarName = ref('')
const newVarValue = ref('')

const numberSource = ref<'manual' | 'store'>('manual')
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
const aiAutoDetectOnOpen = ref(true)
const aiLangHint = ref('')
const aiGenCountryIso = ref('')
const aiCountryHint = ref('')
const aiForm = ref({ prompt: '', language: 'zh', count: 5, mode: 'prompt' as 'prompt' | 'rewrite', rewriteHint: '', maxLen: 70 })
const aiGenerating = ref(false)
const aiResults = ref<string[]>([])
const aiSelectedSet = ref<Set<number>>(new Set())
const aiSelectAll = ref(false)

// 多文案发送列表
const multiMessages = ref<string[]>([])

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

/** 模板引擎：当前语言对应的单条字符上限（用于输入框 max） */
const tplMaxLenLimit = computed(() => maxSmsCharsForLang(tplForm.value.language))
/** AI 生成：当前语言对应的单条字符上限 */
const aiMaxLenLimit = computed(() => maxSmsCharsForLang(aiForm.value.language))

const senderDisplay = computed(() => {
  if (form.value.sender_id) return form.value.sender_id
  const numbers = parseNumbers()
  if (numbers.length > 0) return numbers[0]
  return t('menu.sms')
})

const senderInitial = computed(() => {
  const name = senderDisplay.value
  if (!name) return 'S'
  const first = name.charAt(0)
  return /[a-zA-Z\u4e00-\u9fa5]/.test(first) ? first.toUpperCase() : '#'
})

const estimatedParts = computed(() => {
  const len = form.value.message.length
  if (len === 0) return 0
  if (len <= 70) return 1
  return Math.ceil(len / 67)
})

// 与后端 _count_sms_parts 一致：用于商店模式短信费计算（多文案时取第一条）
function countPartsForMessage(msg: string): number {
  if (!msg || msg.length === 0) return 0
  if (msg.length <= 70) return 1
  return Math.ceil(msg.length / 67)
}
const storeSmsParts = computed(() =>
  multiMessages.value.length > 1 ? countPartsForMessage(multiMessages.value[0]) : estimatedParts.value
)

const numberCount = computed(() => parseNumbers().length)
const totalEstimatedSegments = computed(() => numberCount.value * estimatedParts.value)

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
// 展示用字符串
const storeCost = computed(() => storeTotalCost.value.toFixed(2))

const hasVariables = computed(() => {
  if (/\{(序号|国家|日期|随机码|号码|index|country|date|code|phone)\}/.test(form.value.message)) return true
  return customVars.value.some(cv => form.value.message.includes(`{${cv.name}}`))
})

const hasSensitiveWord = computed(() => {
  const msg = form.value.message.toLowerCase()
  return SENSITIVE_WORDS.some(w => msg.includes(w.toLowerCase()))
})

const previewSms = computed(() => {
  let msg = form.value.message
  const today = new Date().toISOString().slice(0, 10)
  msg = msg.replace(/\{序号\}/g, '1').replace(/\{index\}/g, '1')
  msg = msg.replace(/\{国家\}/g, 'BR').replace(/\{country\}/g, 'BR')
  msg = msg.replace(/\{日期\}/g, today).replace(/\{date\}/g, today)
  msg = msg.replace(/\{随机码\}/g, '385921').replace(/\{code\}/g, '385921')
  msg = msg.replace(/\{号码\}/g, '5511999887766').replace(/\{phone\}/g, '5511999887766')
  // 替换自定义变量
  for (const cv of customVars.value) {
    msg = msg.replace(new RegExp(`\\{${cv.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\}`, 'g'), cv.value || `[${cv.name}]`)
  }
  return msg
})

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
  const builtIn = ['序号', '国家', '日期', '随机码', '号码', 'index', 'country', 'date', 'code', 'phone']
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

function replaceCustomVars(msg: string): string {
  let result = msg
  for (const cv of customVars.value) {
    result = result.replace(new RegExp(`\\{${cv.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\}`, 'g'), cv.value)
  }
  return result
}

// ============ 模板引擎 ============

function generateFromTemplateEngine() {
  tplGenerating.value = true
  tplSelectedSet.value = new Set(); tplSelectAll.value = false
  const maxLen = tplForm.value.maxLen || maxSmsCharsForLang(tplForm.value.language)

  setTimeout(() => {
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
      for (let i = 0; i < tplForm.value.count; i++) {
        const prefix = prefixes[Math.floor(Math.random() * prefixes.length)]
        const suffix = suffixes[Math.floor(Math.random() * suffixes.length)]
        let variant = base
        const strategy = i % 3
        if (strategy === 0) variant = prefix + variant + suffix
        else if (strategy === 1) variant = prefix + variant.replace(/[!！。]?\s*$/, '') + suffix
        else variant = variant + suffix
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
    tplResults.value = raw.map(m => truncateToLimit(sanitizeMessage(stripEmoji(m)), maxLen))
    tplGenerating.value = false
  }, 300)
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
  aiGenerating.value = true; aiSelectedSet.value = new Set(); aiSelectAll.value = false; aiResults.value = []
  const maxLen = aiForm.value.maxLen || maxSmsCharsForLang(aiForm.value.language)

  let prompt = ''
  const noEmojiHint = '严禁使用任何 emoji 表情符号。'
  const sensitiveHint = '内容中不得包含敏感词汇（赌博、色情、毒品、暴力等）。'
  const charHint = `每条文案不超过 ${maxLen} 个字符。`
  if (aiForm.value.mode === 'rewrite' && form.value.message.trim()) {
    prompt = `请基于以下短信文案改写 ${aiForm.value.count} 个不同版本，保持核心意思但变换表达方式、语气和风格。${noEmojiHint} ${sensitiveHint} ${charHint}\n\n原文案：${form.value.message}\n\n${aiForm.value.rewriteHint ? '改写要求：' + aiForm.value.rewriteHint : ''}`
  } else {
    prompt = aiForm.value.prompt
    if (!prompt.trim()) { aiGenerating.value = false; return }
    prompt = `${prompt}\n\n注意：${noEmojiHint} ${sensitiveHint} ${charHint}`
  }

  try {
    const res = await generateSmsContent({ prompt, count: aiForm.value.count, language: aiForm.value.language, max_length: maxLen })
    if (res.success && res.messages?.length) {
      aiResults.value = res.messages.map(m => truncateToLimit(sanitizeMessage(stripEmoji(m)), maxLen))
    } else { ElMessage.warning('AI 未返回有效文案') }
  } catch (e: any) {
    ElMessage.error(e.message || 'AI 生成失败')
    tplForm.value.type = 'marketing'; tplForm.value.language = aiForm.value.language; tplForm.value.keywords = prompt; tplForm.value.mode = 'type'
    generateFromTemplateEngine(); aiResults.value = tplResults.value
    if (aiResults.value.length) ElMessage.info('已使用内置模板引擎生成替代文案')
  } finally { aiGenerating.value = false }
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
function applySingleAi() {
  const idx = [...aiSelectedSet.value][0]
  if (idx != null && aiResults.value[idx]) {
    form.value.message = aiResults.value[idx]; multiMessages.value = []
    showAiDialog.value = false
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
  if (open && aiAutoDetectOnOpen.value) {
    const txt = form.value.message.trim()
    if (txt) {
      aiForm.value.language = detectLanguageFromText(txt)
      aiLangHint.value = `已自动识别文案语言：${getLangLabel(aiForm.value.language)}`
    }
  }
  if (open) {
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
  const numbers = parseNumbers()
  if (numbers.length !== 1) {
    ElMessage.warning('提交审核仅支持单条，请先输入一个号码')
    return
  }
  if (!form.value.message) {
    ElMessage.warning(t('smsSend.pleaseEnterContent'))
    return
  }
  let phone = numbers[0].trim()
  if (!phone.startsWith('+')) phone = '+' + phone
  approvalSubmitting.value = true
  try {
    await submitSmsApproval({
      phone_number: phone,
      message: sanitizeMessage(stripEmoji(replaceCustomVars(form.value.message))),
    })
    ElMessage.success('已提交审核，审核通过后可点击「立即发送」')
    handleReset()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '提交失败')
  } finally {
    approvalSubmitting.value = false
  }
}

// ============ 手动发送 ============

const handleSend = async () => {
  const numbers = parseNumbers()
  if (numbers.length === 0) { ElMessage.warning(t('smsSend.pleaseEnterNumbers')); return }
  if (!form.value.message) { ElMessage.warning(t('smsSend.pleaseEnterContent')); return }
  if (numbers.length > 1000) {
    ElMessage.warning('单次最多提交 1000 个号码，请分批发送')
    return
  }
  loading.value = true; result.value = null; sendProgress.value = 0

  // 多文案轮发 + 清理 emoji / 敏感词（与后端 /sms/batch 一致）
  const msgs = (multiMessages.value.length > 1 ? multiMessages.value.map(replaceCustomVars) : [replaceCustomVars(form.value.message)])
    .map(m => sanitizeMessage(stripEmoji(m)))

  const e164List = numbers.map((n) => {
    let p = n.trim()
    if (!p.startsWith('+')) p = '+' + p
    return p
  })

  try {
    const payload: {
      phone_numbers: string[]
      message: string
      messages?: string[]
      sender_id?: string
      channel_id?: number
      batch_name?: string
    } = {
      phone_numbers: e164List,
      message: msgs[0],
      batch_name: `发送页-${new Date().toLocaleString('zh-CN', { hour12: false })}`,
    }
    if (msgs.length > 1) payload.messages = msgs
    if (form.value.sender_id) payload.sender_id = form.value.sender_id
    if (form.value.channel_id) payload.channel_id = form.value.channel_id

    const res = await sendBatchSMS(payload)
    const successCount = res?.succeeded ?? 0
    const failCount = res?.failed ?? 0
    sendProgress.value = e164List.length

    result.value = {
      success: successCount > 0,
      successCount,
      failCount,
      batchId: res?.batch_id,
    }
    if (successCount > 0) {
      ElMessage.success(t('smsSend.sendCompleteResult', { success: successCount, fail: failCount }))
      if (form.value.resetOnlyNumbers) form.value.phone_numbers_text = ''; else handleReset()
      loadStats()
    } else {
      const firstErr = res?.messages?.find((m) => !m.success)?.error?.message
      if (firstErr?.toLowerCase().includes('balance') || firstErr?.includes('余额')) {
        ElMessage.error(t('smsSend.insufficientBalance'))
      } else {
        ElMessage.error(firstErr || t('smsSend.sendFailedCheckBalance', { count: failCount }))
      }
    }
  } catch (error: any) {
    result.value = { success: false, error: { message: error.message } }
    ElMessage.error(t('smsSend.sendFailed') + ': ' + (error.response?.data?.detail || error.message))
  } finally { loading.value = false }
}

// ============ 商店购买发送 ============

const selectProduct = (product: DataProduct) => {
  selectedProduct.value = product
  storeQuantity.value = Math.max(product.min_purchase || 100, 1000)
}

const handleStoreSend = async () => {
  if (!selectedProduct.value || !form.value.message) return
  try {
    await ElMessageBox.confirm(
      storeSmsCost.value > 0
        ? `确认购买 ${storeQuantity.value.toLocaleString()} 条数据并发送短信？\n数据费: $${storeDataCost.value.toFixed(2)} + 短信费: $${storeSmsCost.value.toFixed(2)} = 合计: $${storeCost.value}`
        : `确认购买 ${storeQuantity.value.toLocaleString()} 条数据并发送短信？\n费用: $${storeCost.value}`,
      '确认购买发送', { type: 'warning' },
    )
  } catch { return }

  storeSending.value = true; result.value = null
  try {
    const payload: any = {
      product_id: selectedProduct.value.id,
      quantity: storeQuantity.value,
      message: sanitizeMessage(stripEmoji(replaceCustomVars(form.value.message))),
    }
    if (selectedCarrier.value) payload.carrier = selectedCarrier.value
    if (multiMessages.value.length > 1) {
      payload.messages = multiMessages.value.map(m => sanitizeMessage(stripEmoji(replaceCustomVars(m))))
    }
    const res = await buyAndSend(payload)
    if (res.success) {
      result.value = { success: true, message: `已购买 ${storeQuantity.value} 条数据并创建发送任务，批次: ${res.batch_id}` }
      ElMessage.success('订单创建成功！')
      loadStats()
      loadStoreProducts()
    }
  } catch (error: any) {
    result.value = { success: false, error: { message: error.message } }
    ElMessage.error(error.message || '购买发送失败')
  } finally { storeSending.value = false }
}

// ============ 重置 ============

const handleReset = () => {
  form.value.phone_numbers_text = ''; form.value.message = ''; form.value.sender_id = ''; form.value.channel_id = null; result.value = null
  selectedProduct.value = null
}

// ============ 数据加载 ============

const loadChannels = async () => {
  try { const res = await getChannels(); channels.value = res.channels || []; channelBound.value = res.bound === true; if (channelBound.value && channels.value.length === 1) form.value.channel_id = channels.value[0].id } catch (e) { console.error('Load channels failed', e) }
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

const formatCount = (n: number) => {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}w`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
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

const updateTime = () => {
  const now = new Date()
  currentTime.value = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  currentDate.value = now.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

let timeInterval: number

onMounted(() => {
  loadChannels(); loadStats(); updateTime(); checkAiConfig(); checkServices(); loadStoreProducts()
  timeInterval = window.setInterval(updateTime, 1000)
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
.carrier-tag { display: inline-flex; align-items: center; gap: 4px; padding: 4px 12px; font-size: 12px; border-radius: 14px; border: 1px solid var(--border-default); background: var(--bg-card, white); color: var(--text-secondary); cursor: pointer; transition: all 0.15s; white-space: nowrap; }
.carrier-tag:hover { border-color: var(--el-color-primary-light-5, #79bbff); color: var(--el-color-primary, #409eff); }
.carrier-tag.active { border-color: var(--el-color-primary, #409eff); background: rgba(64, 158, 255, 0.1); color: var(--el-color-primary, #409eff); font-weight: 600; }
.carrier-count { font-size: 10px; opacity: 0.7; }
.sp-carrier-badge { display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 8px; background: rgba(64, 158, 255, 0.12); color: var(--el-color-primary, #409eff); font-size: 10px; font-weight: 500; }

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
.preview-header { margin-bottom: 12px; }
.preview-title { font-size: 13px; font-weight: 500; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.08em; }
.phone-container { flex: 1; display: flex; justify-content: center; padding: 8px; }
.iphone { width: 280px; height: 560px; background: linear-gradient(145deg, #1C1C1E 0%, #000000 100%); border-radius: 44px; padding: 10px; position: relative; box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12), 0 20px 60px rgba(0, 0, 0, 0.6); }
.dynamic-island { position: absolute; top: 16px; left: 50%; transform: translateX(-50%); width: 90px; height: 28px; background: #000; border-radius: 16px; z-index: 100; }
.iphone-screen { width: 100%; height: 100%; background: linear-gradient(180deg, #000000 0%, #0A0A0A 100%); border-radius: 34px; overflow: hidden; display: flex; flex-direction: column; }
.ios-status-bar { display: flex; justify-content: space-between; align-items: center; padding: 14px 24px 6px; color: white; font-size: 14px; font-weight: 600; }
.status-icons { display: flex; align-items: center; gap: 5px; }
.battery { display: flex; align-items: center; }
.battery-body { width: 20px; height: 10px; border: 1.5px solid white; border-radius: 3px; padding: 1px; }
.battery-level { width: 100%; height: 100%; background: #32D74B; border-radius: 1px; }
.battery-cap { width: 2px; height: 4px; background: white; border-radius: 0 1px 1px 0; margin-left: 1px; }
.ios-messages { flex: 1; display: flex; flex-direction: column; background: #000; }
.ios-nav { display: flex; align-items: center; padding: 6px 12px 10px; gap: 10px; }
.nav-back { padding: 4px; }
.nav-contact { flex: 1; display: flex; align-items: center; gap: 8px; }
.contact-avatar-ios { width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(135deg, #667EEA 0%, #764BA2 100%); display: flex; align-items: center; justify-content: center; color: white; font-size: 14px; font-weight: 600; }
.contact-info { display: flex; flex-direction: column; }
.contact-name { font-size: 15px; font-weight: 600; color: white; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.contact-label { font-size: 10px; color: #8E8E93; }
.ios-chat { flex: 1; padding: 8px 14px; overflow-y: auto; display: flex; flex-direction: column; }
.chat-date { text-align: center; font-size: 11px; color: #8E8E93; margin: 6px 0 12px; }
.ios-bubble { align-self: flex-start; max-width: 85%; }
.bubble-text { background: #2C2C2E; color: white; padding: 10px 12px; border-radius: 16px 16px 16px 4px; font-size: 15px; line-height: 1.35; word-break: break-word; }
.bubble-meta { margin-top: 4px; padding-left: 6px; font-size: 10px; color: #8E8E93; }
.empty-chat { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: #48484A; font-size: 13px; }
.empty-icon { opacity: 0.3; }
.ios-input-bar { display: flex; align-items: center; gap: 8px; padding: 6px 10px 22px; background: #1C1C1E; }
.input-bubble { flex: 1; background: #3A3A3C; border-radius: 18px; padding: 8px 14px; font-size: 15px; color: #8E8E93; }
.home-indicator { position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%); width: 120px; height: 4px; background: rgba(255, 255, 255, 0.4); border-radius: 3px; }

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
.gen-text { font-size: 13px; line-height: 1.5; flex: 1; }
.gen-char-count { flex-shrink: 0; font-size: 11px; color: var(--el-text-color-secondary); white-space: nowrap; margin-left: auto; }

/* 字符计数 & 敏感词提示 */
.msg-meta-bar { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; font-size: 12px; }
.char-counter { color: var(--el-text-color-secondary); }
.char-counter.over-limit { color: var(--el-color-warning, #e6a23c); font-weight: 500; }
.sensitive-warn { color: var(--el-color-danger, #f56c6c); font-weight: 500; }

/* 自定义变量对话框 */
.cv-list { margin-bottom: 16px; }
.cv-item { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cv-eq { font-size: 14px; color: var(--el-text-color-secondary); font-weight: 600; }
.cv-add { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding-top: 16px; border-top: 1px dashed var(--el-border-color-lighter, #ebeef5); }

/* 生成结果头部 */
.gen-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5); }
.gen-selected-tip { font-size: 12px; color: var(--el-text-color-secondary); }

/* 智能生成：语言自动识别与按国家匹配 */
.lang-smart-row { margin-top: 8px; }
.lang-smart-actions { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 4px; }
.lang-smart-hint { margin: 6px 0 0; font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.4; }

/* 多文案配置 */
.multi-msg-config { margin-top: 16px; padding: 12px; background: rgba(64, 158, 255, 0.04); border: 1px solid var(--el-border-color-lighter, #ebeef5); border-radius: 8px; }
.mmc-title { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
.mmc-desc { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.mmc-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
.mmc-label { font-weight: 500; white-space: nowrap; min-width: 52px; }
.mmc-preview { color: var(--el-text-color-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.mmc-summary { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--el-border-color-lighter, #ebeef5); font-size: 13px; font-weight: 500; color: var(--el-color-primary, #409eff); }

/* 多文案提示横幅 */
.multi-msg-banner { margin-top: 8px; padding: 10px 12px; background: rgba(64, 158, 255, 0.06); border: 1px solid rgba(64, 158, 255, 0.2); border-radius: 8px; }
.mmb-header { display: flex; justify-content: space-between; align-items: center; font-size: 13px; margin-bottom: 6px; }
.mmb-header strong { color: var(--el-color-primary, #409eff); }
.mmb-list { display: flex; flex-direction: column; gap: 4px; }
.mmb-item { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 4px 8px; border-radius: 4px; background: var(--el-fill-color-light, #f5f7fa); }
.mmb-item.current { background: rgba(64, 158, 255, 0.1); }
.mmb-idx { width: 18px; height: 18px; border-radius: 50%; background: var(--el-color-primary, #409eff); color: white; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; flex-shrink: 0; }
.mmb-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--el-text-color-secondary); }

.slide-enter-active, .slide-leave-active { transition: all 0.3s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(-10px); }

@media (max-width: 1200px) { .stats-cards { grid-template-columns: repeat(2, 1fr); } .page-grid { grid-template-columns: 1fr; } .preview-panel { display: none; } }
@media (max-width: 768px) { .stats-cards { grid-template-columns: 1fr; } .options-row { flex-direction: column; } .number-actions { flex-direction: column; } .source-tabs { flex-direction: column; } }
</style>
