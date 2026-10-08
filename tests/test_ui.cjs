const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(require('path').join(__dirname, '../app/static/app.js'), 'utf8');
const context = {document: {addEventListener() {}}};
vm.createContext(context); vm.runInContext(source, context);
assert.match(context.jobLabel({status:'processing',stage:'synthesizing',total_chunks:3,done_chunks:0,elapsed_seconds:65}), /parte 1 de 3.*1 min 5 s/);
assert.match(context.jobLabel({status:'processing',stage:'exporting',elapsed_seconds:65}), /archivo de audio/);
assert.equal(context.jobLabel({status:'error',error:'Fallo'}), 'Fallo');
console.log('3 comprobaciones de interfaz correctas');

(async () => {
  let retries = 0;
  context.fetch = async () => ({ok:false,status:503});
  context.setTimeout = () => { retries++; };
  const state = {textContent:''};
  const wrap = {querySelector:() => state};
  await context.pollJob('test', wrap);
  assert.equal(retries, 1);
  context.fetch = async () => ({ok:false,status:404});
  await context.pollJob('test', wrap);
  assert.equal(retries, 1);
  assert.match(state.textContent, /no está disponible/);
  console.log('Reintento temporal y trabajo no disponible: correctos');
})().catch(error => { console.error(error); process.exitCode = 1; });
