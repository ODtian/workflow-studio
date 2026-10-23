import {defineConfig} from 'vite';
import {svelte} from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  build: {
    outDir: '../assets',
    lib: {entry: 'main.js', formats: ['es'], fileName: () => 'view.js'},
    cssCodeSplit: false,
    rollupOptions: {output: {inlineDynamicImports: true, assetFileNames: 'components.css'}}
  }
});
