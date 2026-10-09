from pathlib import Path
import base64
import json
import time

out = Path('.scratch/today-light-refine')
results = []

def click_named(name, role):
    node = next(n for n in cdp('Accessibility.getFullAXTree')['nodes'] if n.get('name',{}).get('value') == name and n.get('role',{}).get('value') == role)
    cdp('DOM.scrollIntoViewIfNeeded',backendNodeId=node['backendDOMNodeId'])
    box = cdp('DOM.getBoxModel',backendNodeId=node['backendDOMNodeId'])['model']['content']
    click_at_xy(sum(box[0::2])/4,sum(box[1::2])/4)

def capture(name,w,h,size,dark):
    cdp('Emulation.setDeviceMetricsOverride',width=w,height=h,deviceScaleFactor=1,mobile=False)
    js(f"document.documentElement.classList.toggle('dark',{str(dark).lower()});document.documentElement.classList.toggle('light',{str(not dark).lower()});document.documentElement.style.fontSize='{size}px';document.querySelector('main').scrollTop=0;document.querySelector('.today-center-content').scrollTop=0")
    time.sleep(1.8)
    (out/(name+'.png')).write_bytes(base64.b64decode(cdp('Page.captureScreenshot',format='png',fromSurface=True,captureBeyondViewport=True,clip={'x':0,'y':0,'width':w,'height':h,'scale':1},_response_timeout=30)['data']))
    info = json.loads(js("JSON.stringify({viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,font:getComputedStyle(document.documentElement).fontSize,bodyOverflow:document.body.scrollWidth>innerWidth,mainOverflow:document.querySelector('main').scrollHeight>document.querySelector('main').clientHeight+1,gridHeight:document.querySelector('.today-grid').clientHeight,previewHeight:document.querySelector('.today-preview').clientHeight,confirmBottom:[...document.querySelectorAll('.today-preview-actions a')].find(e=>!e.classList.contains('today-preview-source-shortcut'))?.getBoundingClientRect().bottom})"))
    info.update(file=name+'.png',runtime='Chrome browser with IPC/API substitutes',tauri=False)
    assert not info['bodyOverflow'],info
    if not dark: assert not info['mainOverflow'],info
    results.append(info)
    print(info)

for args in [('light',1920,1080,16,False),('light-large',1586,992,18,False),('light-narrow',1066,800,18,False),('light-small',1440,900,15,False),('dark-regression',1586,992,16,True)]:
    capture(*args)

capture('interaction',1920,1080,16,False)
click_named('预览总结「缓存与并发控制：第二份待确认总结」','button')
time.sleep(.5)
assert js("document.querySelector('.today-preview h3').textContent") == '缓存与并发控制：第二份待确认总结'
assert js("document.querySelector('.today-preview-actions a:not(.today-preview-source-shortcut)').getAttribute('href')") == '/records/preview-two'
before = js("document.querySelector('.today-workspace header').getBoundingClientRect().top")
js("document.querySelector('.today-preview-content').scrollTop=600")
assert js("document.querySelector('main').scrollTop") == 0
assert js("document.querySelector('.today-workspace header').getBoundingClientRect().top") == before
assert js("document.querySelector('.today-preview-actions').getBoundingClientRect().bottom") < 1080

click_named('完成计划项「进程调度复习：比较多种调度策略并解释适用场景」','checkbox')
assert '正在完成' in js("document.querySelector('.today-center').innerText")
time.sleep(1.4)
assert js("window.__PREVIEW_COMPLETIONS__") == 1
assert '进程调度复习：比较多种调度策略并解释适用场景' not in js("document.querySelector('.today-center').innerText")
click_named('开始','button')
click_named('学习轨道 Ctrl 2','tab')
time.sleep(1.2)
assert js("document.querySelector('[role=timer]').textContent") < '25:00'
click_named('工作台 Ctrl 1','tab')
click_named('暂停','button')
click_named('结束','button')
print('Selection, scroll containment, visible confirm, completion feedback and cross-view timer passed')
(out/'matrix.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
