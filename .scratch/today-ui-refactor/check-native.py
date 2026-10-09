from pathlib import Path
import base64
import time
import json

out = Path('.scratch/today-ui-refactor/screenshots')
results = []

def click_named(name, role):
    nodes = cdp('Accessibility.getFullAXTree')['nodes']
    node = next(n for n in nodes if n.get('name', {}).get('value') == name and n.get('role', {}).get('value') == role)
    cdp('DOM.scrollIntoViewIfNeeded', backendNodeId=node['backendDOMNodeId'])
    bounds = cdp('DOM.getBoxModel', backendNodeId=node['backendDOMNodeId'])['model']['content']
    click_at_xy(sum(bounds[0::2]) / 4, sum(bounds[1::2]) / 4)

def capture(name, width, height, size, dark):
    cdp('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=False)
    js(f"document.documentElement.classList.toggle('dark',{str(dark).lower()});document.documentElement.classList.toggle('light',{str(not dark).lower()});document.documentElement.style.fontSize='{size}px';document.querySelector('main').scrollTop=0")
    js("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))")
    time.sleep(1)
    (out / (name + '.png')).write_bytes(base64.b64decode(cdp('Page.captureScreenshot', format='png')['data']))
    result = json.loads(js("JSON.stringify({w:innerWidth,h:innerHeight,dpr:devicePixelRatio,font:getComputedStyle(document.documentElement).fontSize,theme:document.documentElement.className,tauri:!!window.__TAURI_INTERNALS__,grid:getComputedStyle(document.querySelector('.today-grid')).gridTemplateColumns,bodyOverflow:document.body.scrollWidth>innerWidth,overflows:[...document.querySelectorAll('.today-workspace *')].filter(e=>e instanceof HTMLElement&&e.scrollWidth>e.clientWidth+2&&getComputedStyle(e).overflowX==='visible').map(e=>({tag:e.tagName,text:e.innerText?.slice(0,35)})).slice(0,10)})"))
    result['file'] = name + '.png'
    results.append(result)
    print(result)

cdp('Emulation.setEmulatedMedia', features=[{'name':'prefers-reduced-motion','value':'reduce'}])
for config in [('light',1586,992,16,False), ('dark',1586,992,16,True), ('small',1586,992,15,False), ('large',1586,992,18,False), ('narrow-large',1066,800,18,False)]:
    capture(*config)

cdp('Emulation.setDeviceMetricsOverride', width=1586, height=992, deviceScaleFactor=1, mobile=False)
js("document.documentElement.classList.remove('dark');document.documentElement.classList.add('light');document.documentElement.style.fontSize='16px';document.querySelector('main').scrollTop=0")
time.sleep(.5)
click_named('开始','button')
time.sleep(1.2)
before = js("document.querySelector('[role=timer]').textContent")
click_named('学习轨道 Ctrl 2','tab')
time.sleep(1)
after = js("document.querySelector('[role=timer]').textContent")
assert after < before, (before, after)
click_named('暂停','button')
paused = js("document.querySelector('[role=timer]').textContent")
time.sleep(1.2)
assert js("document.querySelector('[role=timer]').textContent") == paused
capture('orbit',1586,992,16,False)
click_named('工作台 Ctrl 1','tab')
time.sleep(.3)
click_named('继续','button')
time.sleep(.5)
click_named('结束','button')
click_named('新建','button')
time.sleep(.5)
assert any(n.get('role',{}).get('value') == 'dialog' for n in cdp('Accessibility.getFullAXTree')['nodes'])
cdp('Input.dispatchKeyEvent', type='keyDown', key='Escape', code='Escape', windowsVirtualKeyCode=27)
cdp('Input.dispatchKeyEvent', type='keyUp', key='Escape', code='Escape', windowsVirtualKeyCode=27)
print('Native interactions passed:', before, after, paused, 'quick note opened and dismissed')
(out / 'matrix.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
