import {mkdir, copyFile, readFile, writeFile} from 'node:fs/promises';
await mkdir('dist/assets', {recursive:true});
for (const name of ['index.html','app.js','style.css','demo.json','assistant.js','assistant-data.js']) await copyFile(`web/${name}`,`dist/${name}`);
await copyFile('dashboard/floor_plan/floor.css','dist/assets/floor.css');
const floor = (await readFile('dashboard/floor_plan/floor.js','utf8'))
  .replace('Each guest is a live detection', 'Illustrative service scenario')
  .replace('live: "Live",', 'demo: "Demo", live: "Live",');
await writeFile('dist/assets/floor.js',floor+'\nexport { createApp };\n');
await copyFile('dashboard/static/fonts/archivo-latin-wdth-normal.woff2','dist/assets/archivo.woff2');
await copyFile('dashboard/static/fonts/OFL.txt','dist/assets/OFL.txt');
await copyFile('output/restaurant_output.MOV','dist/assets/restaurant-output.mp4');
console.log('DineAssist built in dist/. Only public demo assets are included.');
