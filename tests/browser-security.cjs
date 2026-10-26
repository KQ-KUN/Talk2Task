const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root=__dirname;
(async()=>{
 const launchOptions={headless:true};
 if(process.env.TALK2TASK_BROWSER_CHANNEL)launchOptions.channel=process.env.TALK2TASK_BROWSER_CHANNEL;
 else if(process.platform==='win32')launchOptions.channel='msedge';
 const browser=await chromium.launch(launchOptions);
 try{
  const page=await browser.newPage();
  let statusRequest;
  await page.route('**/*',r=>{
   if(r.request().url().endsWith('/api/tasks/status'))statusRequest={json:r.request().postDataJSON(),header:r.request().headers()['x-talk2task-request']};
   return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify([])});
  });
  await page.goto('http://127.0.0.1:5000/');
  await page.setContent(fs.readFileSync(path.join(root,'../frontend/index.html'),'utf8'));
  const results={};
  for(const kind of ['tasks','risks','memos']){
   await page.evaluate(kind=>{
    window.__auditXss=false;
    const payload='<img src="/synthetic-invalid-image" onerror="window.__auditXss=true">';
    if(kind==='tasks')renderTasks([{task_id:'synthetic',task_name:payload,owner:payload,deadline:payload,priority:payload}],1);
    if(kind==='risks')renderRisks([payload]);
    if(kind==='memos')renderMemos([{created_at:payload,summary:payload,tasks:[{task_name:payload,owner:payload,deadline:payload,status:payload}],risks:[payload]}]);
   },kind);
   await page.waitForTimeout(80);
   results[kind+'_script_executed']=await page.evaluate(()=>window.__auditXss);
  }
  await page.evaluate(()=>{
   window.__idXss=false;
   renderTasks([{task_id:"x');window.__idXss=true;//",task_name:'Synthetic task',owner:'Synthetic owner',deadline:'Synthetic deadline',priority:'Normal'}],1);
   document.querySelector('#tasksList select').dispatchEvent(new Event('change',{bubbles:true}));
  });
  await page.waitForTimeout(80);
  results.task_id_script_executed=await page.evaluate(()=>window.__idXss);
  if(true){
   results.task_status_handler_preserves_id=statusRequest?.json?.task_id==="x');window.__idXss=true;//";
   results.task_status_request_has_header=statusRequest?.header==='1';
   if(!results.task_status_handler_preserves_id||!results.task_status_request_has_header)process.exitCode=1;
  }
  results.browser=await browser.version();
  console.log(JSON.stringify(results));
  if(Object.entries(results).some(([k,v])=>k.endsWith('_executed')&&v))process.exitCode=1;
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
