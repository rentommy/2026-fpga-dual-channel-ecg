import fs from 'node:fs/promises';
import { FileBlob, PresentationFile } from 'file:///C:/Users/rentommy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const p=await PresentationFile.importPptx(await FileBlob.load('D:/Desktop/AMD_poster_template.pptx'));
console.log('SLIDES',p.slides.items.length);
const info=await p.inspect({select:'$.slides[*].elements[*]',include:['id','kind','text','position']});
await fs.writeFile('D:/ecg_fpga/海报/_build/inspect.json',JSON.stringify(info.records,null,2));
const blob=await p.export({slide:p.slides.items[0],format:'png',scale:1});
await fs.writeFile('D:/ecg_fpga/海报/_build/template.png',new Uint8Array(await blob.arrayBuffer()));
