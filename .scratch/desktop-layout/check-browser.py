import base64
import json
import time
from pathlib import Path

out = Path('E:/workspace/project/my/KnowRealm-AI/.scratch/desktop-layout/evidence')
cdp('Emulation.setFocusEmulationEnabled', enabled=True)
goto_url('http://localhost:1420/settings?section=appearance')
wait_for_load()
js("(async()=>{const m=await import('/src/i18n/index.ts');await m.applyLanguage('zh')})()")

def click_named(name, role):
    nodes = cdp('Accessibility.getFullAXTree')['nodes']
    node = next(n for n in nodes if n.get('name', {}).get('value') == name and n.get('role', {}).get('value') == role)
    cdp('DOM.scrollIntoViewIfNeeded', backendNodeId=node['backendDOMNodeId'])
    box = cdp('DOM.getBoxModel', backendNodeId=node['backendDOMNodeId'])['model']['content']
    click_at_xy(sum(box[0::2])/4, sum(box[1::2])/4)

def wait_js(expression):
    for _ in range(50):
        if js(expression):
            return
        time.sleep(.1)
    raise AssertionError(expression)

def shot(name):
    (out/(name+'.png')).write_bytes(base64.b64decode(cdp('Page.captureScreenshot', format='png', _response_timeout=30)['data']))

cdp('Emulation.setDeviceMetricsOverride', width=1440, height=900, deviceScaleFactor=1, mobile=False)
wait_js("!!document.getElementById('preference-layout-TOP')")
click_named('顶部导航布局', 'radio')
wait_js("document.getElementById('app-sidebar').hidden")
assert js("document.querySelector('button[aria-controls=app-sidebar]').closest('[hidden]') !== null")
shot('settings-top')
click_named('资产库', 'link')
wait_js("location.pathname === '/library'")
assert js("document.querySelector('nav[aria-label] a[href=\"/library\"]').getAttribute('aria-current')") == 'page'
results = []
for language in ['zh', 'en']:
    js(f"(async()=>{{const m=await import('/src/i18n/index.ts');await m.applyLanguage('{language}')}})()")
    wait_js(f"document.documentElement.lang === '{'zh-CN' if language=='zh' else 'en-US'}'")
    for mode, theme in [('light','LIGHT_DEFAULT'), ('dark','DARK_DEFAULT'), ('light','LIGHT_SAGE'), ('dark','DARK_INK')]:
        for width, size in [(1440,16), (1099,18), (800,18), (600,18)]:
            cdp('Emulation.setDeviceMetricsOverride', width=width, height=900, deviceScaleFactor=1, mobile=False)
            js(f"document.documentElement.classList.toggle('dark',{str(mode=='dark').lower()});document.documentElement.classList.toggle('light',{str(mode=='light').lower()});document.documentElement.dataset.theme='{theme}';document.documentElement.style.fontSize='{size}px';document.body.offsetHeight;document.getAnimations().forEach(a=>a.finish())")
            time.sleep(.2)
            value = json.loads(js("JSON.stringify((()=>{const nav=document.querySelector('nav[aria-label]');const box=nav.getBoundingClientRect();return {overflow:document.documentElement.scrollWidth>innerWidth,sidebarHidden:document.querySelector('#app-sidebar').hidden,navigationWidth:box.width,links:[...nav.querySelectorAll(':scope>a')].map(a=>({text:a.textContent.trim(),fits:a.getBoundingClientRect().right<=box.right+.5})),more:!!nav.querySelector('[aria-haspopup=menu]'),border:getComputedStyle(document.querySelector('header[data-tauri-drag-region]')).borderBottomWidth}})())"))
            assert not value['overflow'] and value['sidebarHidden'] and all(a['fits'] for a in value['links']), value
            value.update(language=language,theme=theme,width=width,font=size)
            results.append(value)
            if language=='zh' and width==1440:
                shot(theme)
    if language=='en':
        shot('english-narrow')
        click_named('More navigation', 'button')
        shot('overflow-menu')
        click_named('AI Chat', 'menuitem')
        wait_js("location.pathname === '/chat'")

(out/'matrix.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'matrixPassed':len(results),'overflowRoute':js('location.pathname')},ensure_ascii=True))
js("(async()=>{const m=await import('/src/i18n/index.ts');await m.applyLanguage('zh')})()")
wait_js("document.documentElement.lang === 'zh-CN'")
cdp('Emulation.setDeviceMetricsOverride', width=1440, height=900, deviceScaleFactor=1, mobile=False)
js("document.documentElement.style.fontSize='16px'")
click_named('近期课程', 'button')
click_named('布局验收课程', 'menuitem')
wait_js("location.pathname.includes('/spaces/')")
click_named('设置', 'link')
wait_js("location.pathname === '/settings'")
click_named('外观与布局', 'tab')
click_named('侧边栏布局', 'radio')
wait_js("!document.getElementById('app-sidebar').hidden")
click_named('顶部导航布局', 'radio')
wait_js("document.getElementById('app-sidebar').hidden")
cdp('Page.reload')
wait_for_load()
wait_js("!!document.getElementById('app-sidebar') && document.getElementById('app-sidebar').hidden")
print('Real API saving, course navigation, layout reversal and browser reload passed; IPC remains substituted.')
