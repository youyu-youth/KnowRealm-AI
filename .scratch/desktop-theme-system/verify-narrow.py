from pathlib import Path
import base64
import json
import time

out = Path('.scratch/desktop-theme-system/native/narrow')
out.mkdir(exist_ok=True)
results = []

def click_named(name):
    n = next(n for n in cdp('Accessibility.getFullAXTree')['nodes']
             if n.get('name', {}).get('value') == name and n.get('role', {}).get('value') == 'radio')
    cdp('DOM.scrollIntoViewIfNeeded', backendNodeId=n['backendDOMNodeId'])
    b = cdp('DOM.getBoxModel', backendNodeId=n['backendDOMNodeId'])['model']['content']
    click_at_xy(sum(b[0::2])/4, sum(b[1::2])/4)
    for _ in range(50):
        time.sleep(.05)
        if js("!document.querySelector('[role=radio][aria-disabled=true]')"): return
    raise AssertionError('save remained pending')

def capture(name):
    time.sleep(.15)
    r = js("({theme:document.documentElement.dataset.theme,font:getComputedStyle(document.documentElement).fontSize,viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,overflow:document.body.scrollWidth>innerWidth,native:!!window.__TAURI_INTERNALS__})")
    assert r['native'] and not r['overflow'], r
    r['file'] = name+'.png'
    results.append(r)
    (out/(name+'.png')).write_bytes(base64.b64decode(cdp('Page.captureScreenshot',format='png')['data']))

for font in ['小','中','大']:
    for mode, choice in [('浅色','默认明亮'),('浅色','柔和青灰'),('深色','默认暗黑'),('深色','克制墨蓝')]:
        cdp('Page.navigate',url='http://localhost:1420/settings?section=appearance')
        time.sleep(.45)
        click_named(font)
        click_named(mode)
        click_named(choice)
        capture(font+'-'+choice+'-settings')
        js("document.querySelector('a[href=\"/\"]').click()")
        time.sleep(.3)
        capture(font+'-'+choice+'-today')
        print(font,choice,'settings/today passed')

cdp('Emulation.setEmulatedMedia',features=[{'name':'prefers-reduced-motion','value':'reduce'}])
cdp('Page.navigate',url='http://localhost:1420/settings?section=appearance')
time.sleep(.5)
click_named('中')
click_named('浅色')
click_named('柔和青灰')
js("document.querySelector('[role=radio][aria-labelledby=appearance-LIGHT_SAGE-label]').focus()")
cdp('Input.dispatchKeyEvent',type='keyDown',key='ArrowLeft',code='ArrowLeft',windowsVirtualKeyCode=37)
cdp('Input.dispatchKeyEvent',type='keyUp',key='ArrowLeft',code='ArrowLeft',windowsVirtualKeyCode=37)
time.sleep(.4)
assert js("document.querySelector('[role=radio][aria-labelledby=appearance-LIGHT_DEFAULT-label]').getAttribute('aria-checked')") == 'true'
assert js("document.activeElement.getAttribute('aria-labelledby')") == 'appearance-LIGHT_DEFAULT-label'
assert js("matchMedia('(prefers-reduced-motion: reduce)').matches")
capture('keyboard-reduced-motion')
cdp('Emulation.setEmulatedMedia',features=[])
(out/'matrix.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('keyboard and reduced-motion passed')
