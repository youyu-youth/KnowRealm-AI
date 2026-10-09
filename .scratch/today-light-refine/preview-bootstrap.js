const { mockIPC, mockWindows } = await import('/node_modules/@tauri-apps/api/mocks.js');
mockIPC((cmd) => cmd === 'get_sidecar_config' ? {baseUrl:'http://127.0.0.1:43127',token:'visual-preview'} : cmd === 'get_onboarding_state' ? true : null, {shouldMockEvents:true});
mockWindows('main');
const originalFetch = window.fetch;
const previewSummaries = [
 {record_id:'preview-one',title:'进程与线程：调度机制与上下文切换',course_id:'os',course_name:'操作系统',ready_at:'2026-10-09T01:12:00Z'},
 {record_id:'preview-two',title:'缓存与并发控制：第二份待确认总结',course_id:'spring',course_name:'Spring Boot 高级教程',ready_at:'2026-10-09T00:50:00Z'},
];
let previewPlans = [
 {item_id:'preview-task-one',plan_id:'plan',course_id:'os',course_name:'操作系统',goal_id:'goal',goal_title:'复习调度算法与比较指标',action_type:'STUDY_RECORD',content:'进程调度复习：比较多种调度策略并解释适用场景',estimated_minutes:60,scheduled_date:'2026-10-09',user_locked:false},
 {item_id:'preview-task-two',plan_id:'plan',course_id:'spring',course_name:'Spring Boot 高级教程',goal_id:'goal-two',goal_title:'巩固并发控制基础',action_type:'STUDY_RECORD',content:'缓存与验证两部分自测：写出 8～10 道概念题并作答',estimated_minutes:45,scheduled_date:'2026-10-08',user_locked:false},
];
window.__PREVIEW_COMPLETIONS__ = 0;
window.fetch = async (input, init) => {
  const url = String(input instanceof Request ? input.url : input);
  if (!url.startsWith('http://127.0.0.1:43127/')) return originalFetch(input, init);
  const path = new URL(url).pathname;
  let data = [];
  if(path === '/api/today/pending-summaries') data = previewSummaries;
  if(path === '/api/today/plan-items') data = previewPlans;
  if(path.endsWith('/summary')) data = {action_required:'NONE',active_job_id:null,blocked_reason:null,summary:{abstract:'这是用于交互验收的示例长总结，不是用户真实学习数据。'.repeat(8),sections:Array.from({length:12},(_,i)=>({heading:'调度机制 '+(i+1),points:['比较不同调度策略，并记录适用条件。'.repeat(4)]}))}};
  if(path.endsWith('/complete')) {
    await new Promise(resolve=>setTimeout(resolve,900));
    const itemId = path.split('/').at(-2);
    const completed = previewPlans.find(p=>p.item_id===itemId);
    previewPlans = previewPlans.filter(p=>p.item_id!==itemId);
    window.__PREVIEW_COMPLETIONS__++;
    data = {...completed,status:'DONE'};
  }
  if(path.endsWith('/preferences')) data = {theme:'LIGHT',font_scale:'M',language:'zh',timezone:null,close_behavior:'TRAY',quick_note_shortcut:'Ctrl+Alt+N',autostart:false,quiz_last_count:5};
  if(path === '/api/today/stats') data = {total_learning_ms:36000000,record_count:39,course_count:13,ai_summary_count:20,quiz_generated_count:50,quiz_answered_count:24,chat_turn_count:135};
  if(path === '/api/today/stats/trend') data = Array.from({length:30},(_,i)=>({date:new Date(Date.UTC(2026,8,10+i)).toISOString().slice(0,10),total_ms:[1,1.5,.5,2,1,1.5,2.5][i%7]*3600000}));
  return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
};
const React = (await import('/node_modules/.vite/deps/react.js')).default;
const {createRoot} = (await import('/node_modules/.vite/deps/react-dom_client.js')).default;
const {default:App} = await import('/src/App.tsx');
document.querySelector('#root').style.display='none';
const preview = document.createElement('div');
preview.id='light-refine-preview';
document.body.appendChild(preview);
createRoot(preview).render(React.createElement(App));
window.__TODAY_VISUAL_MOCK__ = true;

