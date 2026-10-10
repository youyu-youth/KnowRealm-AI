import json
import time
from pathlib import Path

out = Path('.scratch/today-ux-20261010')
original_theme = js('document.documentElement.className')
snapshots = {}
try:
    cdp('Page.bringToFront')
    for theme in ['light', 'dark']:
        js('document.documentElement.className=' + json.dumps(theme))
        time.sleep(.6)
        cdp('Page.captureScreenshot', format='png')
        snapshots[theme] = js("(()=>{const selectors={workbench:'.today-header [role=tab][aria-selected=true]',pending:'.today-pending-tabs [role=tab][aria-selected=true]',trend:'.today-stats [role=tab][aria-selected=true]',start:'.today-focus-controls [data-slot=button]',confirm:'.today-preview-actions a:not(.today-preview-source-shortcut)',heading:'.today-heading',timer:'[role=timer]',link:'.today-pending a',panel:'.today-panel'};return Object.fromEntries(Object.entries(selectors).map(([key,s])=>{const e=document.querySelector(s),c=getComputedStyle(e),r=e.getBoundingClientRect();return [key,{background:c.backgroundColor,color:c.color,geometry:[r.x,r.y,r.width,r.height]}]}))})()")
    if verify_after:
        before = json.loads((out / 'button-colors-before.json').read_text(encoding='utf-8'))
        assert snapshots['dark'] == before['dark'], 'Dark theme changed'
        for name in ['workbench','pending','trend','start','confirm']:
            assert snapshots['light'][name]['background'] == 'rgb(26, 28, 32)', (name, snapshots['light'][name])
            assert snapshots['light'][name]['color'] == before['light'][name]['color'], name
            assert snapshots['light'][name]['geometry'] == before['light'][name]['geometry'], name
        for name in ['heading','timer','link','panel']:
            assert snapshots['light'][name] == before['light'][name], name
        print('PASS five light controls use DESIGN #1A1C20; geometry, text, links, timer, panels, and dark styles preserved')
    else:
        assert snapshots['dark']['panel']['background'] == 'rgb(32, 36, 42)', snapshots['dark']
    (out / ('button-colors-after.json' if verify_after else 'button-colors-before.json')).write_text(json.dumps(snapshots, indent=2), encoding='utf-8')
finally:
    js('document.documentElement.className=' + json.dumps(original_theme))
