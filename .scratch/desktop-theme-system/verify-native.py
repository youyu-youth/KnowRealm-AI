from pathlib import Path
import base64
import json
import time

out = Path('.scratch/desktop-theme-system/native')
results = []


def click_named(name, role):
    node = next(n for n in cdp('Accessibility.getFullAXTree')['nodes']
                if n.get('name', {}).get('value') == name
                and n.get('role', {}).get('value') == role)
    cdp('DOM.scrollIntoViewIfNeeded', backendNodeId=node['backendDOMNodeId'])
    box = cdp('DOM.getBoxModel', backendNodeId=node['backendDOMNodeId'])['model']['content']
    click_at_xy(sum(box[0::2]) / 4, sum(box[1::2]) / 4)


def settled():
    for _ in range(100):
        if js("!document.querySelector('[role=radio][aria-disabled=true]')"):
            time.sleep(.1)
            return
        time.sleep(.05)
    raise AssertionError('Preference save did not settle')


def screenshot(name):
    time.sleep(.2)
    (out / (name + '.png')).write_bytes(base64.b64decode(
        cdp('Page.captureScreenshot', format='png')['data']))
    info = json.loads(js("JSON.stringify({theme:document.documentElement.dataset.theme,"
        "mode:document.documentElement.className,viewport:[innerWidth,innerHeight],"
        "dpr:devicePixelRatio,font:getComputedStyle(document.documentElement).fontSize,"
        "tauri:!!window.__TAURI_INTERNALS__,bodyOverflow:document.body.scrollWidth>innerWidth,"
        "canvas:getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim(),"
        "paper:getComputedStyle(document.documentElement).getPropertyValue('--paper').trim(),"
        "chartCount:document.querySelectorAll('[_echarts_instance_]').length})"))
    assert info['tauri'] and not info['bodyOverflow'], info
    info['file'] = name + '.png'
    results.append(info)


assert js("window.__TAURI_INTERNALS__.invoke('get_data_directory')").endswith('desktop-theme-system\\native\\data')
click_named('浅色', 'radio')
settled()
click_named('柔和青灰', 'radio')
settled()
assert js("document.documentElement.dataset.theme") == 'LIGHT_SAGE'
click_named('克制墨蓝', 'radio')
settled()
assert js("document.documentElement.dataset.theme") == 'LIGHT_SAGE'

for theme, mode, choice in [('LIGHT_DEFAULT', '浅色', '默认明亮'),
                             ('LIGHT_SAGE', '浅色', '柔和青灰'),
                             ('DARK_DEFAULT', '深色', '默认暗黑'),
                             ('DARK_INK', '深色', '克制墨蓝')]:
    click_named(mode, 'radio')
    settled()
    js("window.__themeClick=null;window.__themeChange=null;"
       "document.addEventListener('click',()=>window.__themeClick=performance.now(),{once:true,capture:true});"
       "window.__themeObserver=new MutationObserver(()=>{window.__themeChange=performance.now();window.__themeObserver.disconnect()});"
       "window.__themeObserver.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']})")
    click_named(choice, 'radio')
    settled()
    assert js("document.documentElement.dataset.theme") == theme
    latency = js("window.__themeChange===null?null:window.__themeChange-window.__themeClick")
    if latency is not None:
        assert latency < 120, latency
    screenshot(theme + '-settings')
    results[-1]['clickToRootMs'] = latency
    for page in ['今日', '知识空间', '资产库', 'AI 对话']:
        click_named(page, 'link')
        time.sleep(.4)
        screenshot(theme + '-' + {'今日': 'today', '知识空间': 'spaces', '资产库': 'library', 'AI 对话': 'chat'}[page])
    click_named('设置', 'link')
    time.sleep(.25)
    click_named('外观与语言', 'tab')
    time.sleep(.2)

# Real rendered chart instances update in place via the production appearance function.
click_named('今日', 'link')
time.sleep(.3)
nodes = cdp('Accessibility.getFullAXTree')['nodes']
tabs = [n.get('name', {}).get('value', '') for n in nodes if n.get('role', {}).get('value') == 'tab']
chart_tab = next((name for name in tabs if '统计' in name), None)
if chart_tab:
    click_named(chart_tab, 'tab')
    time.sleep(.4)
    js("window.__themeChart=document.querySelector('[_echarts_instance_]')")
    assert js("!!window.__themeChart"), 'Statistics chart missing'
    before = js("window.__themeChart.querySelector('svg').innerHTML")
    js("import('/src/features/settings/appearance.ts').then(m=>m.applyTheme('LIGHT',{theme:'LIGHT',light_theme_id:'LIGHT_SAGE',dark_theme_id:'DARK_INK'}))")
    time.sleep(.25)
    assert js("window.__themeChart===document.querySelector('[_echarts_instance_]')"), 'Chart was remounted'
    assert before != js("window.__themeChart.querySelector('svg').innerHTML"), 'Chart retained old colors'
    screenshot('chart-sage')
    js("import('/src/features/settings/appearance.ts').then(m=>m.applyTheme('DARK',{theme:'DARK',light_theme_id:'LIGHT_SAGE',dark_theme_id:'DARK_INK'}))")
    time.sleep(.25)
    screenshot('chart-ink')

# Keep an actual draft dialog, focus and scroll while the root palette changes.
click_named('新建速记', 'button')
time.sleep(.3)
print([(n.get('role',{}).get('value'),n.get('name',{}).get('value'))
       for n in cdp('Accessibility.getFullAXTree')['nodes']
       if n.get('role',{}).get('value') in ['dialog','textbox']])
(out / 'matrix.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print('Captured', len(results), 'native states; latencies', [r.get('clickToRootMs') for r in results if 'clickToRootMs' in r])
