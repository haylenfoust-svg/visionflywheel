<script setup lang="ts">
/**
 * App shell — minimal wrapper.
 *
 * Brand lives in the sidebar (Layout.vue), page title in the main content
 * (PageHeader). The top bar is reserved for global actions (theme toggle,
 * notifications, user menu) — see Layout.vue.
 */
</script>

<template>
  <router-view />
</template>

<style>
/* Global app shell styles (unscoped — applies to html/body via design-system.scss) */
#app {
  min-height: 100vh;
}
</style>
