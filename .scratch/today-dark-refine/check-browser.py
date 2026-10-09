from pathlib import Path
import base64
import json
import time

out = Path('.scratch/today-dark-refine')
metadata = []
js("window.__darkRefineOriginal={className:document.documentElement.className,fontSize:document.documentElement.style.fontSize}")

def capture(name, width, height, size, dark):
    cdp('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=False)
    js(f"document.documentElement.classList.toggle('dark',{str(dark).lower()});document.documentElement.classList.toggle('light',{str(not dark).lower()});document.documentElement.style.fontSize='{size}px';document.querySelector('main').scrollTop=0")
    time.sleep(1)
    (out / (name + '.png')).write_bytes(base64.b64decode(cdp('Page.captureScreenshot', format='png')['data']))
    info = json.loads(js("JSON.stringify({viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,font:getComputedStyle(document.documentElement).fontSize,tauri:!!window.__TAURI_INTERNALS__,bodyOverflow:document.body.scrollWidth>innerWidth,colors:Object.fromEntries(['--today-ink','--today-muted','--today-border','--today-soft','--today-surface','--today-accent','--today-primary','--today-primary-foreground','--today-focus'].map(k=>[k,getComputedStyle(document.documentElement).getPropertyValue(k).trim()]))})"))
    assert js("!!window.__TODAY_VISUAL_MOCK__") and not info['bodyOverflow'], info
    info['tauri'] = False
    info['ipc_mock'] = True
    info['visual_mock'] = True
    info['runtime'] = 'Isolated Chrome browser with Tauri IPC and API substitutes'
    info['file'] = name + '.png'
    metadata.append(info)
    print(info)

for config in [('dark',1920,1080,16,True),('dark-large',1586,992,18,True),('dark-narrow',1066,800,18,True),('light-regression',1586,992,16,False)]:
    capture(*config)

assert metadata[-1]['colors']['--today-accent'] == '#075dce'
assert metadata[-1]['colors']['--today-focus'] == '#009e8a'

def luminance(color):
    rgb = [int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))

colors = metadata[0]['colors']
contrast = {}
for text in ('--today-ink','--today-muted'):
    for bg in ('--today-surface','--today-soft'):
        a,b = sorted((luminance(colors[text]),luminance(colors[bg])), reverse=True)
        ratio = (a+.05)/(b+.05)
        assert ratio >= 4.5, (text,bg,ratio)
        contrast[text+' on '+bg] = round(ratio,2)
print('Text contrast:',contrast)

capture('dark-focus',1586,992,16,True)
js("document.querySelector('.today-workspace [role=tab]').focus()")
cdp('Input.dispatchKeyEvent', type='keyDown', key='Tab', code='Tab', windowsVirtualKeyCode=9)
cdp('Input.dispatchKeyEvent', type='keyUp', key='Tab', code='Tab', windowsVirtualKeyCode=9)
time.sleep(.3)
(out / 'dark-focus.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',format='png')['data']))
focus = json.loads(js("JSON.stringify({name:document.activeElement.textContent,visible:document.activeElement.matches(':focus-visible'),outline:getComputedStyle(document.activeElement).outlineColor})"))
assert focus['visible'], focus
print('Keyboard focus:',focus)

cdp('Emulation.setEmulatedMedia', features=[{'name':'prefers-color-scheme','value':'dark'}])
js("document.documentElement.classList.remove('light','dark')")
assert js("getComputedStyle(document.documentElement).getPropertyValue('--today-surface').trim()") == '#20242a'
print('System dark fallback passed')

(out / 'matrix.json').write_text(json.dumps({'screenshots':metadata,'contrast':contrast,'focus':focus}, ensure_ascii=False,indent=2),encoding='utf-8')
js("document.documentElement.className=window.__darkRefineOriginal.className;document.documentElement.style.fontSize=window.__darkRefineOriginal.fontSize;document.querySelector('main').scrollTop=0")
cdp('Emulation.clearDeviceMetricsOverride')
cdp('Emulation.setEmulatedMedia', features=[])
print('Restored theme, font and viewport')


