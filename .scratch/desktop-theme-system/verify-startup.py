from pathlib import Path
import base64
import json
import time

out = Path('.scratch/desktop-theme-system/native/startup')
out.mkdir(exist_ok=True)
directory = js("window.__TAURI_INTERNALS__.invoke('get_data_directory')")
assert directory.endswith('desktop-theme-system\\native\\data')
cache_key = 'knowrealm-appearance-v1:' + directory
observer = cdp('Page.addScriptToEvaluateOnNewDocument', source="""
window.__startupFrames = [];
function inspectAppearanceFrame() {
  const main = document.querySelector('main');
  if (main && main.getBoundingClientRect().height > 0 && window.__startupFrames.length < 40) {
    window.__startupFrames.push({time:performance.now(), theme:document.documentElement.dataset.theme,
      canvas:getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim()});
  }
  if(window.__startupFrames.length < 40) requestAnimationFrame(inspectAppearanceFrame);
}
requestAnimationFrame(inspectAppearanceFrame);
""")['identifier']
results = []
cases = [('light-no-cache','LIGHT','missing'), ('dark-valid','DARK','valid'),
         ('light-corrupt','LIGHT','corrupt'), ('dark-wrong-directory','DARK','wrong'),
         ('system-valid','SYSTEM','valid'), ('system-stale-theme','SYSTEM','stale')]
try:
    for name, mode, cache in cases:
        prefs = {'theme':mode,'light_theme_id':'LIGHT_SAGE','dark_theme_id':'DARK_INK'}
        js("(async()=>{const cfg=await window.__TAURI_INTERNALS__.invoke('get_sidecar_config');"
           "const r=await fetch(cfg.baseUrl+'/api/settings/preferences',{method:'PUT',headers:{'Content-Type':'application/json','X-KnowRealm-Token':cfg.token},body:"
           + json.dumps(json.dumps(prefs)) + "});if(!r.ok)throw Error('preference setup failed')})()")
        js('localStorage.removeItem(' + json.dumps(cache_key) + ')')
        if cache != 'missing':
            value = {'version':1,'directory':directory,'appearance':prefs}
            if cache == 'wrong': value['directory'] = 'another-directory'
            if cache == 'stale': value['appearance'] = {**prefs, 'light_theme_id':'REMOVED_THEME'}
            raw = 'broken-json' if cache == 'corrupt' else json.dumps(value)
            js('localStorage.setItem(' + json.dumps(cache_key) + ',' + json.dumps(raw) + ')')
        drain_events()
        cdp('Page.startScreencast', format='png', maxWidth=1280, maxHeight=800, everyNthFrame=1)
        cdp('Page.reload', ignoreCache=True)
        images = 0
        for _ in range(35):
            time.sleep(.08)
            for event in drain_events():
                if event.get('method') == 'Page.screencastFrame':
                    frame = event['params']
                    if images < 8:
                        (out / f'{name}-{images}.png').write_bytes(base64.b64decode(frame['data']))
                    images += 1
                    cdp('Page.screencastFrameAck', sessionId=frame['sessionId'])
            frames = js('window.__startupFrames || []')
            if isinstance(frames, list) and len(frames) >= 8: break
        cdp('Page.stopScreencast')
        frames = js('window.__startupFrames || []')
        expected = 'DARK_INK' if mode=='DARK' or (mode=='SYSTEM' and js("matchMedia('(prefers-color-scheme: dark)').matches")) else 'LIGHT_SAGE'
        assert frames and all(frame['theme'] == expected for frame in frames), (name, expected, frames)
        restored = json.loads(js('localStorage.getItem(' + json.dumps(cache_key) + ')'))
        assert restored['directory'] == directory and restored['appearance'] == prefs, restored
        results.append({'case':name,'expected':expected,'visibleWorkspaceFrames':frames,'screencastFrameCount':images})
        print(name, 'workspace frames:', len(frames), 'captured images:', images)
finally:
    cdp('Page.stopScreencast')
    cdp('Page.removeScriptToEvaluateOnNewDocument', identifier=observer)
    (out/'matrix.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
