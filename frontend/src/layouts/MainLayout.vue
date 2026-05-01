<template>
  <div class="app-layout" :class="{ 'light-mode': theme === 'light' }">
    <!-- 背景装饰 -->
    <div class="bg-decoration">
      <div class="orb orb-1"></div>
      <div class="orb orb-2"></div>
    </div>
    
    <el-container class="layout-container">
      <!-- 侧边栏 -->
      <el-aside :width="sidebarCollapsed ? '80px' : '240px'" class="sidebar" :class="{ collapsed: sidebarCollapsed }">
        <!-- Logo区域 -->
        <div class="logo-area">
          <div class="logo-wrapper" @click="toggleSidebar">
            <div class="logo-icon">
              <img src="/favicon.svg?v=koala2" alt="考拉出海" width="30" height="30" />
            </div>
            <transition name="fade">
              <span class="logo-text" v-if="!sidebarCollapsed">{{ $t('brand.name') }}</span>
            </transition>
          </div>
        </div>
        
        <!-- 导航菜单 -->
        <nav class="nav-menu">
          <!-- 1. 概览 -->
          <div class="nav-section">
            <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.overview') }}</span>
            <div class="nav-item" :class="{ active: isActive('/dashboard') }" @click="navigate('/dashboard')">
              <div class="nav-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <rect x="2" y="2" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.5"/>
                  <rect x="11" y="2" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.5"/>
                  <rect x="2" y="11" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.5"/>
                  <rect x="11" y="11" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.5"/>
                </svg>
              </div>
              <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.dashboard') }}</span>
            </div>
          </div>

          <!-- ========== 客户菜单 (根据开通业务显示) ========== -->
          <template v-if="!isStaff">
            <!-- 短信业务 -->
            <div class="nav-section" v-if="hasSmsService">
              <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.smsBusiness') }}</span>
              <div
                v-for="item in customerSmsNavItems"
                :key="item.path"
                class="nav-item"
                :class="{ active: isActive(item.path) }"
                @click="navigate(item.path)"
              >
                <div class="nav-icon">
                  <template v-if="item.icon === 'plane'">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M18 2L9 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <path d="M18 2L12 18L9 11L2 8L18 2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                    </svg>
                  </template>
                  <template v-else-if="item.icon === 'tasks' || item.icon === 'records'">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 6H13M7 10H13M7 14H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </template>
                  <template v-else-if="item.icon === 'stats'">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M2 16H18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <path d="M4 16V10M8 16V6M12 16V8M16 16V4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </template>
                  <template v-else-if="item.icon === 'approvals'">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M4 10L8 14L16 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                      <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5"/>
                    </svg>
                  </template>
                </div>
                <span class="nav-label" v-if="!sidebarCollapsed">{{ $t(item.titleKey) }}</span>
              </div>
            </div>


            <!-- 数据业务 -->
            <div class="nav-section" v-if="hasDataService">
              <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.dataBusiness') }}</span>
              <div class="nav-item" :class="{ active: isActive('/data/store') }" @click="navigate('/data/store')">
                <div class="nav-icon">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M3 6L5 2H15L17 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <rect x="3" y="6" width="14" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M8 10H12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.dataStore') }}</span>
              </div>

              <div class="nav-item" :class="{ active: isActive('/data/my-numbers') }" @click="navigate('/data/my-numbers')">
                <div class="nav-icon">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <rect x="4" y="2" width="12" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
                    <circle cx="10" cy="14" r="1" fill="currentColor"/>
                    <path d="M7 5H13M7 8H11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.myNumbers') }}</span>
              </div>
              
              <div class="nav-item" :class="{ active: isActive('/data/orders') }" @click="navigate('/data/orders')">
                <div class="nav-icon">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M7 7H13M7 10H13M7 13H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.myOrders') }}</span>
              </div>

            </div>
          </template>

          <!-- ========== 员工菜单 (根据角色显示) ========== -->
          <template v-if="isStaff">
            
            <!-- 销售角色：我的客户 -->
            <div class="nav-section" v-if="isSales">
              <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.myWork') }}</span>

              <div class="nav-item" :class="{ active: isActive('/admin/accounts') }" @click="navigate('/admin/accounts')">
                <div class="nav-icon">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <circle cx="7" cy="7" r="3" stroke="currentColor" stroke-width="1.5"/>
                    <circle cx="13" cy="7" r="3" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M2 17C2 14.5 4.2 13 7 13M18 17C18 14.5 15.8 13 13 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.myCustomers') }}</span>
              </div>

              <div class="nav-item" :class="{ active: isActive('/reports') }" @click="navigate('/reports')">
                <div class="nav-icon">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M2 16H18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    <path d="M4 16V10M8 16V6M12 16V8M16 16V4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.performance') }}</span>
              </div>

              <div class="nav-item" :class="{ active: isActive('/admin/bot/invites') }" @click="navigate('/admin/bot/invites')">
                <div class="nav-icon">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M7 6H13M7 10H13M7 14H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.invitations') }}</span>
              </div>
            </div>

            <!-- 财务角色：财务管理 -->
            <div class="nav-section" v-if="isFinance">
              <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.financeManage') }}</span>

              <div class="nav-item" :class="{ active: isActive('/reports') }" @click="navigate('/reports')">
                <div class="nav-icon">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M2 16H18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    <path d="M4 16V10M8 16V6M12 16V8M16 16V4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.financeReport') }}</span>
              </div>

              <div class="nav-item" :class="{ active: isActive('/admin/accounts') }" @click="navigate('/admin/accounts')">
                <div class="nav-icon">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <circle cx="7" cy="7" r="3" stroke="currentColor" stroke-width="1.5"/>
                    <circle cx="13" cy="7" r="3" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M2 17C2 14.5 4.2 13 7 13M18 17C18 14.5 15.8 13 13 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.customerBalance') }}</span>
              </div>
            </div>

            <!-- 管理员/技术角色：完整菜单 -->
            <template v-if="isAdmin">
              <!-- 1. 运营中心 -->
              <div class="nav-section">
                <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.operationCenter') }}</span>

                <div class="nav-item" :class="{ active: isActive('/admin/reports/business') }" @click="navigate('/admin/reports/business')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M2 16H18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <path d="M4 16V10M8 16V6M12 16V8M16 16V4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.businessReport') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/accounts') }" @click="navigate('/admin/accounts')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="7" cy="7" r="3" stroke="currentColor" stroke-width="1.5"/>
                      <circle cx="13" cy="7" r="3" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M2 17C2 14.5 4.2 13 7 13M18 17C18 14.5 15.8 13 13 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.customerManage') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/staff') }" @click="navigate('/admin/staff')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="6" r="3" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M4 17C4 14 6.5 12 10 12C13.5 12 16 14 16 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <path d="M15 6L17 8L15 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.staffManage') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/business-knowledge') }" @click="navigate('/admin/business-knowledge')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M4 4h12v12H4V4z" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 8h6M7 11h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.businessKnowledge') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/tickets') }" @click="navigate('/admin/tickets')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 7H13M7 10H13M7 13H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.ticketManage') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/suppliers') }" @click="navigate('/admin/suppliers')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="5" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M3 9H17" stroke="currentColor" stroke-width="1.5"/>
                      <circle cx="10" cy="12" r="1" fill="currentColor"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.supplierQuote') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/account-templates') }" @click="navigate('/admin/account-templates')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 6H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <path d="M7 10H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <path d="M7 14H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <circle cx="15" cy="15" r="4" fill="var(--bg-card)" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M15 13V17M13 15H17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.accountTemplates') }}</span>
                </div>

              </div>

              <!-- 2. 短信业务 -->
              <div class="nav-section">
                <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.smsBusiness') }}</span>

                <div class="nav-item" :class="{ active: isActive('/admin/sms-accounts') }" @click="navigate('/admin/sms-accounts')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="6" r="3" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M3 17C3 13.5 6 11 10 11C14 11 17 13.5 17 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.smsAccounts') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/channels') }" @click="navigate('/channels')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="5" cy="10" r="2" stroke="currentColor" stroke-width="1.5"/>
                      <circle cx="15" cy="5" r="2" stroke="currentColor" stroke-width="1.5"/>
                      <circle cx="15" cy="15" r="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 10H13M13 5L7 10M13 15L7 10" stroke="currentColor" stroke-width="1.5"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.channelConfig') }}</span>
                </div>
                
                <div class="nav-item" :class="{ active: isActive('/sms/records') }" @click="navigate('/sms/records')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 6H13M7 10H13M7 14H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.sendRecords') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/reports') }" @click="navigate('/reports')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M2 16H18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <path d="M4 16V10M8 16V6M12 16V8M16 16V4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.dataReport') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/sms/recharge-records') }" @click="navigate('/sms/recharge-records')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="2" y="5" width="16" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M2 11H18" stroke="currentColor" stroke-width="1.5"/>
                      <circle cx="14" cy="14" r="2" stroke="currentColor" stroke-width="1.5"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.rechargeRecords') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/sms/send-stats') }" @click="navigate('/sms/send-stats')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M2 16H18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <path d="M4 16V10M8 16V6M12 16V8M16 16V4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.sendStats') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/sms/tasks') }" @click="navigate('/admin/sms/tasks')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 8H13M7 11H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <path d="M13 13L15 15L17 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.smsTaskManagement') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/sms/refund-audit') }" @click="navigate('/admin/sms/refund-audit')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="2" y="5" width="16" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M2 9H18" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 13H9M11 13H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.smsRefundAudit') }}</span>
                </div>
              </div>


              <!-- 5. 数据业务 -->
              <div class="nav-section">
                <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.dataBusiness') }}</span>
                
                <div class="nav-item" :class="{ active: isActive('/admin/data/accounts') }" @click="navigate('/admin/data/accounts')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="6" r="3" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M4 17C4 14 6.5 12 10 12C13.5 12 16 14 16 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.dataAccounts') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/data/private-library') }" @click="navigate('/admin/data/private-library')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 8H13M7 11H13M7 14H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.adminCustomerData') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/data/upload') }" @click="navigate('/admin/data/upload')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M10 3V13M10 3L6 7M10 3L14 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                      <path d="M3 13V15C3 16.1046 3.89543 17 5 17H15C16.1046 17 17 16.1046 17 15V13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.dataUpload') }}</span>
                </div>
                
                <div class="nav-item" :class="{ active: isActive('/admin/data/products') }" @click="navigate('/admin/data/products')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="2" y="4" width="16" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M6 9H14M6 12H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.dataProducts') }}</span>
                </div>
                
                <div class="nav-item" :class="{ active: isActive('/admin/data/orders') }" @click="navigate('/admin/data/orders')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 7H13M7 10H13M7 13H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.dataOrders') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/data/pricing') }" @click="navigate('/admin/data/pricing')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M4 4H16V16H4V4Z" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M4 8H16M4 12H16M8 4V16M12 4V16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.dataPricing') }}</span>
                </div>
              </div>

              <!-- 6. TG助手 -->
              <div class="nav-section">
                <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.tgBot') }}</span>

                <div class="nav-item" :class="{ active: isActive('/admin/bot/config') }" @click="navigate('/admin/bot/config')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="10" r="3" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M10 2V4M10 16V18M18 10H16M4 10H2M15.66 4.34L14.24 5.76M5.76 14.24L4.34 15.66" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.botConfig') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/bot/messages') }" @click="navigate('/admin/bot/messages')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M3 5C3 3.9 3.9 3 5 3H15C16.1 3 17 3.9 17 5V12C17 13.1 16.1 14 15 14H7L3 17V5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                      <path d="M7 7H13M7 10H11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.botMessages') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/bot/invites') }" @click="navigate('/admin/bot/invites')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 6H13M7 10H13M7 14H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.invitations') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/bot/templates') }" @click="navigate('/admin/bot/templates')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M16 6L8 14L4 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.templateWhitelist') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/bot/recharge-audit') }" @click="navigate('/admin/bot/recharge-audit')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="2" y="5" width="16" height="10" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M2 9H18" stroke="currentColor" stroke-width="1.5"/>
                      <circle cx="10" cy="10" r="2" stroke="currentColor" stroke-width="1.5"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.rechargeAudit') }}</span>
                </div>

                <div class="nav-item" :class="{ active: isActive('/admin/bot/batch-audit') }" @click="navigate('/admin/bot/batch-audit')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M4 10L8 14L16 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                      <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.batchAudit') }}</span>
                </div>
              </div>

              <!-- 自动注水 -->
              <div class="nav-section">
                <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.waterInjection') }}</span>
                <div class="nav-item" :class="{ active: isActive('/admin/water/proxies') }" @click="navigate('/admin/water/proxies')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M10 6V10L13 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.waterProxies') }}</span>
                </div>
                <div class="nav-item" :class="{ active: isActive('/admin/water/tasks') }" @click="navigate('/admin/water/tasks')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.waterTasks') }}</span>
                </div>
                <div class="nav-item" :class="{ active: isActive('/admin/water/logs') }" @click="navigate('/admin/water/logs')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M4 4H16V16H4Z" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M7 8H13M7 11H11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.waterLogs') }}</span>
                </div>
                <div class="nav-item" :class="{ active: isActive('/admin/water/scripts') }" @click="navigate('/admin/water/scripts')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M6 4L14 4C15.1 4 16 4.9 16 6V14C16 15.1 15.1 16 14 16H6C4.9 16 4 15.1 4 14V6C4 4.9 4.9 4 6 4Z" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M8 9L10 11L12 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.waterScripts') }}</span>
                </div>
              </div>

              <!-- 7. 系统设置 -->
              <div class="nav-section">
                <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.systemSettings') }}</span>
                
                <div class="nav-item" :class="{ active: isActive('/admin/profile') }" @click="navigate('/admin/profile')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="6" r="3" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M4 17C4 14 6.5 12 10 12C13.5 12 16 14 16 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.accountManage') }}</span>
                </div>
                <div class="nav-item" :class="{ active: isActive('/admin/system/config') }" @click="navigate('/admin/system/config')">
                  <div class="nav-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="10" r="3" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M10 2V4M10 16V18M18 10H16M4 10H2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.systemConfig') }}</span>
                </div>
              </div>
            </template>
          </template>

          <!-- 4. 账户管理 (客户专用) -->
          <div class="nav-section" v-if="!isStaff">
            <span class="nav-section-title" v-if="!sidebarCollapsed">{{ $t('menu.myAccount') }}</span>
            
            <div class="nav-item" :class="{ active: isActive('/account/balance') }" @click="navigate('/account/balance')">
              <div class="nav-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <rect x="2" y="4" width="16" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M2 8H18" stroke="currentColor" stroke-width="1.5"/>
                </svg>
              </div>
              <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.balance') }}</span>
            </div>

            <div class="nav-item" :class="{ active: isAccountManageActive() }" @click="navigate('/account/settings')">
              <div class="nav-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <circle cx="10" cy="7" r="4" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M3 17C3 14 6 12 10 12C14 12 17 14 17 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
              </div>
              <span class="nav-label" v-if="!sidebarCollapsed">{{ $t('menu.accountManagement') }}</span>
            </div>
          </div>
        </nav>
        
        <!-- 底部操作区 -->
        <div class="sidebar-footer">
          <!-- 主题切换 -->
          <div class="theme-toggle" @click="toggleTheme" v-if="!sidebarCollapsed">
            <div class="theme-icon">
              <svg v-if="theme === 'dark'" width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="4" stroke="currentColor" stroke-width="1.5"/>
                <path d="M9 1V3M9 15V17M17 9H15M3 9H1M14.66 3.34L13.24 4.76M4.76 13.24L3.34 14.66M14.66 14.66L13.24 13.24M4.76 4.76L3.34 3.34" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              <svg v-else width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M16 10.5C15.17 13.67 12.33 16 9 16C5 16 2 13 2 9C2 5.67 4.33 2.83 7.5 2C6.67 3.17 6 4.83 6 6.5C6 10.08 8.92 13 12.5 13C14.17 13 15.83 12.33 16 10.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <span class="theme-label">{{ theme === 'dark' ? $t('header.lightMode') : $t('header.darkMode') }}</span>
          </div>
          <button class="theme-btn" @click="toggleTheme" v-else>
            <svg v-if="theme === 'dark'" width="18" height="18" viewBox="0 0 18 18" fill="none">
              <circle cx="9" cy="9" r="4" stroke="currentColor" stroke-width="1.5"/>
              <path d="M9 1V3M9 15V17M17 9H15M3 9H1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            <svg v-else width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M16 10.5C15.17 13.67 12.33 16 9 16C5 16 2 13 2 9C2 5.67 4.33 2.83 7.5 2C6.67 3.17 6 4.83 6 6.5C6 10.08 8.92 13 12.5 13C14.17 13 15.83 12.33 16 10.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          
          <!-- 用户信息 -->
          <el-dropdown v-if="isStaff" trigger="click" @command="handleUserMenuCommand" placement="top-start">
            <div class="user-card user-card-clickable">
              <div class="user-avatar">
                {{ accountName.charAt(0).toUpperCase() }}
              </div>
              <div class="user-info" v-if="!sidebarCollapsed">
                <span class="user-name">{{ accountName }}</span>
                <span class="user-role">{{ roleDisplayName }}</span>
              </div>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <svg width="14" height="14" viewBox="0 0 20 20" fill="none" style="vertical-align: -2px; margin-right: 6px">
                    <circle cx="10" cy="6" r="3" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M4 17C4 14 6.5 12 10 12C13.5 12 16 14 16 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                  {{ $t('menu.accountManage') }}
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <svg width="14" height="14" viewBox="0 0 18 18" fill="none" style="vertical-align: -2px; margin-right: 6px">
                    <path d="M6 15H3.5C3 15 2.5 14.5 2.5 14V4C2.5 3.5 3 3 3.5 3H6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    <path d="M12 12L15 9L12 6M6.5 9H15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                  {{ $t('header.logout') }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <div v-else class="user-card user-card-clickable" @click="toggleUserMenu">
            <div class="user-avatar">
              {{ customerSidebarDisplay.charAt(0).toUpperCase() }}
            </div>
            <div class="user-info" v-if="!sidebarCollapsed">
              <span class="user-name" :title="customerSidebarDisplay">{{ customerSidebarDisplay }}</span>
              <span class="user-role">{{ roleDisplayName }}</span>
            </div>
          </div>
        </div>
      </el-aside>
      
      <!-- 主内容区 -->
      <el-container class="main-container">
        <!-- 顶部栏 -->
        <header class="header">
          <div class="header-left">
            <button class="menu-toggle" @click="toggleSidebar">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M3 5H17M3 10H17M3 15H17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
            </button>
            <div class="page-info">
              <h1 class="page-title">{{ currentTitle }}</h1>
            </div>
          </div>
          <div class="header-right">
            <div class="header-status">
              <span class="status-dot"></span>
              <span class="status-text">{{ $t('header.systemNormal') }}</span>
            </div>
            <!-- 语言切换按钮 -->
            <el-dropdown trigger="click" @command="handleLocaleChange">
              <button class="lang-btn-header">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <circle cx="9" cy="9" r="7" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M2 9H16" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M9 2C11.5 4 12.5 6.5 12.5 9C12.5 11.5 11.5 14 9 16" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M9 2C6.5 4 5.5 6.5 5.5 9C5.5 11.5 6.5 14 9 16" stroke="currentColor" stroke-width="1.5"/>
                </svg>
                <span class="lang-text-header">{{ currentLocale === 'zh-CN' ? $t('language.shortZh') : $t('language.shortEn') }}</span>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="zh-CN" :class="{ active: currentLocale === 'zh-CN' }">
                    🇨🇳 {{ $t('language.zh') }}
                  </el-dropdown-item>
                  <el-dropdown-item command="en-US" :class="{ active: currentLocale === 'en-US' }">
                    🇺🇸 {{ $t('language.en') }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <button class="theme-btn-header" @click="toggleTheme">
              <svg v-if="theme === 'dark'" width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="4" stroke="currentColor" stroke-width="1.5"/>
                <path d="M9 1V3M9 15V17M17 9H15M3 9H1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              <svg v-else width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M16 10.5C15.17 13.67 12.33 16 9 16C5 16 2 13 2 9C2 5.67 4.33 2.83 7.5 2C6.67 3.17 6 4.83 6 6.5C6 10.08 8.92 13 12.5 13C14.17 13 15.83 12.33 16 10.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
            <button class="logout-btn" @click="handleLogout">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M6 15H3.5C3 15 2.5 14.5 2.5 14V4C2.5 3.5 3 3 3.5 3H6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <path d="M12 12L15 9L12 6M6.5 9H15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
          </div>
        </header>
        
        <!-- 内容区域 -->
        <main class="main-content">
          <div class="content-wrapper">
            <router-view v-slot="{ Component }">
              <transition name="page" mode="out-in">
                <component :is="Component" />
              </transition>
            </router-view>
          </div>
        </main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getAccountInfo } from '@/api/account'
import { setLocale, getLocale } from '@/i18n'
import { CUSTOMER_SMS_NAV } from '@/config/customerSmsNav'

const customerSmsNavItems = CUSTOMER_SMS_NAV

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const sidebarCollapsed = ref(false)
const isMobile = ref(false)
const theme = ref<'dark' | 'light'>('dark')
const currentLocale = ref(getLocale())

const currentTitle = computed(() => {
  const titleKey = route.meta.titleKey as string
  return titleKey ? t(titleKey) : t('menu.dashboard')
})

// 切换语言
const handleLocaleChange = (locale: string) => {
  const newLocale = locale as LocaleType
  // 先保存到 localStorage
  localStorage.setItem('locale', newLocale)
  // 然后调用 setLocale 更新 i18n
  setLocale(newLocale)
  currentLocale.value = newLocale
  // 强制刷新页面（清除缓存）
  window.location.href = window.location.pathname + '?t=' + Date.now()
}

// 响应式存储用户信息（从 localStorage/sessionStorage 读取）
const accountName = ref('Admin')
const adminRole = ref('')
const adminToken = ref('')
const isImpersonateMode = ref(false)
const isStaffImpersonateMode = ref(false)

// 刷新用户信息
const refreshUserInfo = () => {
  isImpersonateMode.value = sessionStorage.getItem('impersonate_mode') === '1'
  isStaffImpersonateMode.value = sessionStorage.getItem('impersonate_staff_mode') === '1'
  adminToken.value = localStorage.getItem('admin_token') || ''
  adminRole.value = localStorage.getItem('admin_role') || ''
  
  if (isImpersonateMode.value) {
    accountName.value = sessionStorage.getItem('impersonate_account_name') || t('roles.customer')
  } else {
    accountName.value = localStorage.getItem('account_name') || 'Admin'
  }
}

// 是否为员工（有 admin_token 且不是模拟客户登录）
const isStaff = computed(() => !isImpersonateMode.value && !!adminToken.value)

// 是否为管理员角色（super_admin、admin 或 tech 技术）
const isAdmin = computed(() => isStaff.value && ['super_admin', 'admin', 'tech'].includes(adminRole.value))

// 是否为销售角色
const isSales = computed(() => isStaff.value && adminRole.value === 'sales')

// 是否为财务角色
const isFinance = computed(() => isStaff.value && adminRole.value === 'finance')

// 客户开通的业务类型
const customerServices = ref<string[]>(['sms'])
/** 侧栏展示名（优先客户名称/公司名） */
const customerSidebarName = ref('')

// 是否开通短信业务
const hasSmsService = computed(() => customerServices.value.includes('sms'))

// 是否开通数据业务
const hasDataService = computed(() => customerServices.value.includes('data'))

// 获取角色显示名称
const roleDisplayName = computed(() => {
  if (isImpersonateMode.value) return t('roles.customer')
  if (!isStaff.value) return t('roles.customer')
  const roleMap: Record<string, string> = {
    'super_admin': t('roles.superAdmin'),
    'admin': t('roles.admin'),
    'sales': t('roles.sales'),
    'finance': t('roles.finance'),
    'tech': t('roles.tech')
  }
  return roleMap[adminRole.value] || t('roles.staff')
})

const isActive = (path: string) => route.path === path

const isAccountManageActive = () =>
  ['/account/settings', '/account/manage', '/account/info'].includes(route.path)

/** 客户侧栏标题：接口返回的客户名称优先，避免仅显示 TG 前缀 ID */
const customerSidebarDisplay = computed(() => {
  if (isStaff.value) return accountName.value
  const n = customerSidebarName.value.trim()
  return n || accountName.value
})
const expandedMenus = ref<string[]>([])

const toggleSubmenu = (menu: string) => {
  const index = expandedMenus.value.indexOf(menu)
  if (index > -1) {
    expandedMenus.value.splice(index, 1)
  } else {
    expandedMenus.value.push(menu)
  }
}

const navigate = (path: string) => {
  router.push(path)
}

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

const toggleUserMenu = () => {
  if (isStaff.value) return
  router.push('/account/settings')
}

const handleUserMenuCommand = (command: string) => {
  if (command === 'profile') router.push('/admin/profile')
  else if (command === 'logout') handleLogout()
}

const toggleTheme = () => {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.setAttribute('data-theme', theme.value)
  localStorage.setItem('theme', theme.value)
}

const initTheme = () => {
  const savedTheme = localStorage.getItem('theme') as 'dark' | 'light' | null
  if (savedTheme) {
    theme.value = savedTheme
  }
  document.documentElement.setAttribute('data-theme', theme.value)
}

const handleLogout = () => {
  // 检查是否为模拟登录模式
  if (sessionStorage.getItem('impersonate_mode') === '1') {
    // 模拟登录模式：只清理 sessionStorage 并关闭窗口
    sessionStorage.removeItem('impersonate_mode')
    sessionStorage.removeItem('impersonate_api_key')
    sessionStorage.removeItem('impersonate_account_id')
    sessionStorage.removeItem('impersonate_account_name')
    ElMessage.success(t('header.exitImpersonate'))
    window.close()
    return
  }
  
  // 正常登出
  localStorage.removeItem('api_key')
  localStorage.removeItem('account_name')
  localStorage.removeItem('admin_token')
  localStorage.removeItem('admin_id')
  ElMessage.success(t('header.loggedOut'))
  router.push('/login')
}

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
  if (isMobile.value) {
    sidebarCollapsed.value = true
  }
}

// 加载客户服务信息
const loadCustomerServices = async () => {
  // 只有客户需要加载服务信息
  if (isStaff.value) return
  
  try {
    const info = await getAccountInfo()
    if (info?.services) {
      customerServices.value = info.services.split(',').map((s: string) => s.trim())
    }
    const display =
      (info as { client_name?: string; company_name?: string; account_name?: string })?.client_name ||
      info?.company_name ||
      info?.account_name ||
      ''
    customerSidebarName.value = String(display || '').trim()
  } catch {
    // 默认显示短信业务
    customerServices.value = ['sms']
    customerSidebarName.value = ''
  }
}

onMounted(() => {
  initTheme()
  checkMobile()
  refreshUserInfo()
  loadCustomerServices()
  window.addEventListener('resize', checkMobile)
  
  // 监听 storage 变化（其他标签页登录/登出）
  window.addEventListener('storage', refreshUserInfo)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
  window.removeEventListener('storage', refreshUserInfo)
})

// 监听路由变化，刷新用户信息
watch(() => route.path, () => {
  refreshUserInfo()
})
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  background: var(--bg-primary);
  position: relative;
  transition: background-color 0.3s ease;
}

/* 背景装饰 */
.bg-decoration {
  position: fixed;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 0;
  transition: opacity 0.3s ease;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(120px);
  opacity: 0.5;
  transition: opacity 0.3s ease;
}

.orb-1 {
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba(42, 157, 143, 0.2) 0%, transparent 70%);
  top: -200px;
  right: -100px;
}

.orb-2 {
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(45, 212, 191, 0.15) 0%, transparent 70%);
  bottom: -150px;
  left: 20%;
}

.light-mode .bg-decoration {
  opacity: 0.6;
}

.light-mode .orb-1 {
  background: radial-gradient(circle, rgba(0, 122, 255, 0.06) 0%, transparent 70%);
}

.light-mode .orb-2 {
  background: radial-gradient(circle, rgba(52, 199, 89, 0.05) 0%, transparent 70%);
}

/* 布局容器 */
.layout-container {
  height: 100vh;
  position: relative;
  z-index: 1;
}

/* 侧边栏 */
.sidebar {
  background: rgba(10, 12, 16, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  transition: width 0.25s var(--ease-default), background-color 0.3s ease;
  position: relative;
  z-index: 100;
}

.light-mode .sidebar {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-right: 0.5px solid rgba(0, 0, 0, 0.1);
}

/* Logo */
.logo-area {
  padding: 20px 16px;
  border-bottom: 1px solid var(--border-default);
}

.logo-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  padding: 8px;
  border-radius: 12px;
  transition: background 0.2s;
}

.logo-wrapper:hover {
  background: var(--bg-hover);
}

.logo-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

/* 导航菜单 */
.nav-menu {
  flex: 1;
  padding: 16px 12px;
  overflow-y: auto;
  overflow-x: hidden;
}

.nav-section {
  margin-bottom: 24px;
}

.nav-section + .nav-section {
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.nav-section:last-child {
  margin-bottom: 0;
}

.nav-section-title {
  display: block;
  padding: 0 12px;
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-quaternary);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  margin: 4px 6px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s var(--ease-default);
  color: var(--text-tertiary);
  position: relative;
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  box-shadow: 4px 4px 10px rgba(0, 0, 0, 0.3), -2px -2px 6px rgba(255, 255, 255, 0.01);
  transform: translateY(-1px);
}

.nav-item.active {
  background: rgba(42, 157, 143, 0.1);
  color: var(--primary);
  box-shadow: var(--shadow-soft-in);
}

.light-mode .nav-item.active {
  background: rgba(42, 157, 143, 0.08);
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: -12px;
  top: 50%;
  transform: translateY(-50%);
  width: 6px;
  height: 24px;
  border-radius: 0 4px 4px 0;
  background: var(--gradient-primary);
  box-shadow: 0 0 15px rgba(42, 157, 143, 0.5);
}

.nav-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-label {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

/* 子菜单样式 */
.nav-item.has-submenu {
  justify-content: space-between;
}

.submenu-arrow {
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.submenu-arrow.rotated {
  transform: rotate(180deg);
}

.submenu {
  padding-left: 32px;
  margin: 4px 0;
}

.submenu-item {
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.submenu-item:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.submenu-item.active {
  color: var(--primary);
  background: rgba(42, 157, 143, 0.08);
}

.collapsed .nav-item {
  justify-content: center;
  padding: 12px;
}

.collapsed .nav-item.active::before {
  display: none;
}

.collapsed .nav-section-title {
  display: none;
}

/* 侧边栏底部 */
.sidebar-footer {
  padding: 16px;
  border-top: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 主题切换 */
.theme-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
  color: var(--text-tertiary);
}

.theme-toggle:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.theme-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.theme-label {
  font-size: 14px;
  font-weight: 500;
}

.theme-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  margin: 0 auto;
  border: none;
  background: var(--bg-input);
  border-radius: 10px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.2s;
}

.theme-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* 用户卡片 */
.user-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.2s;
}

.user-card:hover {
  background: var(--bg-hover);
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  font-size: 11px;
  color: var(--text-quaternary);
}

/* 主容器 */
.main-container {
  flex-direction: column;
  background: transparent;
  min-width: 0;
}

/* 头部 */
.header {
  height: 72px;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(10, 12, 16, 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border-default);
  flex-shrink: 0;
  transition: all 0.3s var(--ease-default);
}

.light-mode .header {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.1);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.menu-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: var(--bg-secondary);
  border-radius: 10px;
  color: var(--text-tertiary);
  box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
  cursor: pointer;
  transition: all 0.2s;
}

.menu-toggle:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  box-shadow: 4px 4px 8px rgba(0,0,0,0.4);
  transform: translateY(-1px);
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: rgba(56, 239, 125, 0.08);
  border-radius: 20px;
}

.light-mode .header-status {
  background: rgba(52, 199, 89, 0.1);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--success);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-size: 12px;
  font-weight: 500;
  color: var(--success);
}

/* 语言切换按钮 - 右上角 */
.lang-btn-header {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 36px;
  padding: 0 12px;
  border: none;
  background: var(--bg-input);
  border-radius: 10px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.2s;
}

.lang-btn-header:hover {
  background: var(--bg-hover);
  color: var(--primary);
}

.lang-text-header {
  font-size: 12px;
  font-weight: 600;
}

/* 语言下拉菜单样式 */
.el-dropdown-menu__item.active {
  color: var(--primary);
  background: var(--bg-hover);
}

.theme-btn-header {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: var(--bg-input);
  border-radius: 10px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.2s;
}

.theme-btn-header:hover {
  background: var(--bg-hover);
  color: var(--warning);
}

.logout-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: var(--bg-input);
  border-radius: 10px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.2s;
}

.logout-btn:hover {
  background: rgba(245, 87, 108, 0.12);
  color: var(--danger);
}

/* 主内容区 */
.main-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.content-wrapper {
  width: 100%;
  height: 100%;
  padding: 16px;
  box-sizing: border-box;
}

.content-wrapper > * {
  width: 100%;
}

/* 页面过渡 */
.page-enter-active,
.page-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* 淡入淡出 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(0);
}

/* 响应式 */
@media (max-width: 768px) {
  .header {
    padding: 0 16px;
  }
  
  .content-wrapper {
    padding: 16px;
  }
  
  .header-status {
    display: none;
  }
}
</style>