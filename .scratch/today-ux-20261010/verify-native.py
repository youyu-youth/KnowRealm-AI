from pathlib import Path
import base64
import json
import time

out = Path('.scratch/today-ux-20261010')
results = []


def click_named(name, role):
    node = next(n for n in cdp('Accessibility.getFullAXTree')['nodes']
                if n.get('name', {}).get('value') == name
                and n.get('role', {}).get('value') == role)
    cdp('DOM.scrollIntoViewIfNeeded', backendNodeId=node['backendDOMNodeId'])
    box = cdp('DOM.getBoxModel', backendNodeId=node['backendDOMNodeId'])['model']['content']
    click_at_xy(sum(box[0::2]) / 4, sum(box[1::2]) / 4)


def ctrl_digit(key):
    for event_type in ['keyDown', 'keyUp']:
        cdp('Input.dispatchKeyEvent', type=event_type, key=key,
            code='Digit' + key, windowsVirtualKeyCode=ord(key), modifiers=2)


def capture(name, width, height, size, dark):
    cdp('Emulation.setDeviceMetricsOverride', width=width, height=height,
        deviceScaleFactor=1, mobile=False)
    js(f"document.documentElement.classList.toggle('dark',{str(dark).lower()});"
       f"document.documentElement.classList.toggle('light',{str(not dark).lower()});"
       f"document.documentElement.style.fontSize='{size}px'")
    ctrl_digit('1')
    js("document.querySelectorAll('.today-workspace *').forEach(e=>{if(e.scrollTop)e.scrollTop=0})")
    time.sleep(.7)
    (out / (name + '.png')).write_bytes(base64.b64decode(
        cdp('Page.captureScreenshot', format='png')['data']))
    info = json.loads(js("JSON.stringify({viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,"
        "font:getComputedStyle(document.documentElement).fontSize,"
        "tauri:!!window.__TAURI_INTERNALS__,mock:!!window.__TODAY_VISUAL_MOCK__,"
        "bodyOverflow:document.body.scrollWidth>innerWidth,"
        "mainOverflow:document.querySelector('main').scrollHeight>document.querySelector('main').clientHeight+1,"
        "grid:getComputedStyle(document.querySelector('.today-grid')).gridTemplateColumns,"
        "visiblePanels:[...document.querySelectorAll('.today-grid > *')].filter(e=>getComputedStyle(e).display!=='none').map(e=>e.id),"
        "panelBackground:getComputedStyle(document.querySelector('.today-panel')).backgroundColor,"
        "linkColor:getComputedStyle(document.querySelector('.today-task-row a')).color,"
        "previewBody:document.querySelector('.today-preview-body')?.clientHeight,"
        "confirmBottom:document.querySelector('.today-preview-actions')?.getBoundingClientRect().bottom})"))
    assert info['tauri'] and not info['mock'], info
    assert not info['bodyOverflow'] and not info['mainOverflow'], info
    if dark:
        assert info['panelBackground'] == 'rgb(32, 36, 42)', info
        assert info['linkColor'] == 'rgb(213, 216, 222)', info
    info['file'] = name + '.png'
    results.append(info)
    print(info)


try:
    cdp('Page.bringToFront')
    for case in [('final-light', 1920, 1080, 16, False),
                 ('final-light-standard', 1440, 900, 16, False),
                 ('final-dark', 1440, 900, 16, True),
                 ('final-small', 1280, 800, 16, False),
                 ('final-narrow', 1099, 720, 18, False)]:
        capture(*case)
    click_named('待处理', 'button')
    time.sleep(.2)
    assert js("getComputedStyle(document.querySelector('.today-left')).display") == 'flex'
    assert js("getComputedStyle(document.querySelector('.today-center')).display") == 'none'
    node = next(n for n in cdp('Accessibility.getFullAXTree')['nodes']
                if n.get('role', {}).get('value') == 'button'
                and n.get('name', {}).get('value', '').startswith('预览总结'))
    click_named(node['name']['value'], 'button')
    time.sleep(.3)
    assert js("getComputedStyle(document.querySelector('.today-rail')).display") == 'flex'
    assert js("document.activeElement.id") == 'today-summary-preview'
    (out / 'final-narrow-review.png').write_bytes(base64.b64decode(
        cdp('Page.captureScreenshot', format='png')['data']))
    click_named('今日行动', 'button')
    assert js("getComputedStyle(document.querySelector('.today-center')).display") == 'block'
    print('Narrow selection, preview focus, and return passed')
    (out / 'matrix.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
finally:
    original = json.loads((out / 'original.json').read_text())
    cdp('Emulation.clearDeviceMetricsOverride')
    js('document.documentElement.className=' + json.dumps(original['theme']) +
       ';document.documentElement.style.fontSize=' + json.dumps(original['font']))
