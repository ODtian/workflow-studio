import {readFile, writeFile} from 'node:fs/promises';
import {transform} from 'esbuild';

const path = new URL('../assets/view.js', import.meta.url);
const result = await transform(await readFile(path, 'utf8'), {
  minify: true, format: 'esm', target: 'es2022', legalComments: 'none'
});
await writeFile(path, result.code);
