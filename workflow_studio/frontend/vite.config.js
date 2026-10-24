import {defineConfig} from 'vite';
import {svelte} from '@sveltejs/vite-plugin-svelte';
import {vitePreprocess} from '@sveltejs/vite-plugin-svelte';
import tailwindcss from '@tailwindcss/vite';
import {fileURLToPath} from 'node:url';

export default defineConfig({
  plugins: [tailwindcss(), svelte({preprocess:vitePreprocess()})],
  resolve:{alias:{$lib:fileURLToPath(new URL('./lib',import.meta.url))}},
  build: {
    outDir: '../assets',
    lib: {entry: 'main.js', formats: ['es'], fileName: () => 'view.js'},
    cssCodeSplit: false,
    rollupOptions: {output: {inlineDynamicImports: true, assetFileNames: 'components.css'}}
  }
});
