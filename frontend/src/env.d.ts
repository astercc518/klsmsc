/// <reference types="vite/client" />

declare const __APP_BUILD_STAMP__: string

declare module '*.vue' {
    import type { DefineComponent } from 'vue'
    const component: DefineComponent<{}, {}, any>
    export default component
}

declare module 'element-plus'
