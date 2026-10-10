from pathlib import Path
import json

# 使用生产根状态/事件流程验证消费者；不注入业务数据，也不调用私有 React/ECharts 方法。
result = js(r"""(async()=>{
 const charts=[...document.querySelectorAll('[_echarts_instance_]')];
 if(charts.length!==5)throw Error('five charts required');
 const metadata={native:!!window.__TAURI_INTERNALS__,viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,focused:document.hasFocus()};
 const results=[];
 for(const id of ['LIGHT_SAGE','LIGHT_DEFAULT','LIGHT_SAGE','DARK_INK','DARK_DEFAULT','DARK_INK']){
  const root=document.documentElement;if(root.dataset.theme===id)continue;
  const old=charts.map(c=>c.innerHTML),changes=charts.map(()=>null),start=performance.now();
  const observers=charts.map((c,i)=>new MutationObserver(()=>{
   if(changes[i]===null&&c.innerHTML!==old[i])changes[i]=performance.now()-start;
  }));
  observers.forEach((o,i)=>o.observe(charts[i],{subtree:true,childList:true,attributes:true,characterData:true}));
  root.dataset.themeSwitching='';
  root.classList.toggle('dark',id.startsWith('DARK'));
  root.classList.toggle('light',!id.startsWith('DARK'));
  root.dataset.theme=id;
  window.dispatchEvent(new Event('knowrealm:appearance-changed'));
  requestAnimationFrame(()=>requestAnimationFrame(()=>delete root.dataset.themeSwitching));
  await new Promise(resolve=>setTimeout(resolve,100));
  observers.forEach(o=>o.disconnect());
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  results.push({id,chartUpdateMs:changes,instancesRetained:charts.every(c=>c.isConnected),transitionRestored:!root.hasAttribute('data-theme-switching')});
 }
 return {metadata,results};
})()""")
Path('.scratch/desktop-theme-system/native/chart-timing-final.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
assert result['metadata']['native']
assert all(r['instancesRetained'] and r['transitionRestored'] and all(t is not None and t<120 for t in r['chartUpdateMs']) for r in result['results'])
print('six switches, five retained charts; max ms:',max(t for r in result['results'] for t in r['chartUpdateMs']))
