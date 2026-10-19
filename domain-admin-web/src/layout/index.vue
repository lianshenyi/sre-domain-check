<template>
  <div class="app-layout">
    <Header @toggle-mobile-menu="toggleMobileMenu"></Header>

    <div class="app-layout__main">
      <button
        v-if="isMobileMenuOpen"
        class="app-layout__menu-mask"
        type="button"
        aria-label="关闭导航菜单"
        @click="closeMobileMenu"
      ></button>
      <Menu
        :mobile-open="isMobileMenuOpen"
        @close-mobile-menu="closeMobileMenu"
      ></Menu>

      <div class="app-layout__body">

        <el-alert
          v-if="isDefaultPassword"
          :title="$t('请及时修改 admin（超级管理员）的默认密码')"
          type="error"
          show-icon
        />

        <!-- <div class="app-layout__path">{{ currentPathName }}</div> -->
        <div class="app-layout__view">
          <router-view v-slot="{ Component }">
            <transition
              name="fade-transform"
              mode="out-in"
            >
              <component
                :is="Component"
                :key="key"
              />
            </transition>
          </router-view>
        </div>
      </div>
    </div>
    <Footer></Footer>
  </div>
</template>

<script>
// created at 2022-10-01
import Menu from './Menu.vue'
import Footer from './Footer.vue'
import Header from './Header.vue'
import { useUserStore } from '@/store/user-store.js'
import { useSystemStore } from '@/store/system-store.js'
import { mapState, mapActions } from 'pinia'

export default {
  name: 'index',

  props: {},

  components: {
    Menu,
    Footer,
    Header,
  },

  data() {
    return {
      isMobileMenuOpen: false,
    }
  },

  computed: {
    ...mapState(useUserStore, {
      userInfo: 'userInfo',
      isAdmin: 'isAdmin',
      isDefaultPassword: 'isDefaultPassword',
    }),

    currentPathName() {
      // console.log(this.$route)
      return this.$route.meta.title
    },

    key() {
      return this.$route.fullPath
    },
  },

  methods: {
    toggleMobileMenu() {
      this.isMobileMenuOpen = !this.isMobileMenuOpen
    },

    closeMobileMenu() {
      this.isMobileMenuOpen = false
    },

    async getData() {},
  },

  created() {
    this.getData()
  },
}
</script>

<style lang="less">
.app-layout {
  // width: 1000px;
  height: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
}

.app-layout__main {
  display: flex;
  flex: 1;
  height: 0;
  min-width: 0;
}

.app-layout__body {
  flex: 1;
  height: 100%;
  min-width: 0;
  overflow: auto;
  overflow-y: overlay;
  padding: 10px 20px 20px;
}

.app-layout__path {
  color: #333;
  font-size: 12px;
}

.app-layout__view {
  padding-top: 10px;
}

@media (max-width: 767px) {
  .app-layout__menu-mask {
    position: fixed;
    z-index: 1000;
    inset: 0;
    width: 100%;
    border: 0;
    background: rgba(15, 23, 42, 0.45);
    cursor: default;
  }

  .app-layout__body {
    padding: 10px;
  }
}

/* fade-transform */
// .fade-transform-leave-active,
// .fade-transform-enter-active {
//   transition: all 0.5s;
// }

// .fade-transform-enter-from {
//   opacity: 0;
//   transform: translateX(-30px);
// }

// .fade-transform-leave-to {
//   opacity: 0;
//   transform: translateX(30px);
// }

/* fade-transform */
.fade-transform-leave-active,
.fade-transform-enter-active {
  transition: all 0.5s;
}

.fade-transform-enter {
  opacity: 0;
  transform: translateX(-30px);
}

.fade-transform-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

// 黑色主题
.theme--dark {
  .app-layout__body {
    background-color: #f6f8fa;
  }
}

// 蓝色主题
.theme--blue {
  .app-layout__body {
    background-color: #f3f4f7;
  }
}
</style>
