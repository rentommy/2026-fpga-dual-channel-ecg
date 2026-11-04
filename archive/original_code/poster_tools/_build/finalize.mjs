import { finalizePresentation } from 'file:///C:/Users/rentommy/.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations/container_tools/artifact_tool_utils.mjs';
import fs from 'node:fs/promises';
const root='D:/ecg_fpga/海报';
process.env.RUNTIME_NODE_MODULES='C:/Users/rentommy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const skill='C:/Users/rentommy/.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations';
await fs.mkdir(`${root}/交付`,{recursive:true});
for(const name of ['项目海报_中文版','Project_Poster_English']) {
const result=await finalizePresentation({workspaceDir:root,candidatePath:`${root}/${name}.pptx`,finalPath:`${root}/交付/${name}.pptx`,pythonExecutable:'C:/Users/rentommy/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:`${skill}/container_tools/inspect_presentation_package_integrity.py`,layoutValidatorPath:`${skill}/container_tools/inspect_presentation_layout_geometry.py`,explicitTotalSlideCount:1,layoutArgs:['--expected-slide-size-emu','12192000,6858000'],verifyArtifactToolImport:true,receiptPath:`${root}/_build/${name}.validation.json`});
console.log(JSON.stringify(result));
}
