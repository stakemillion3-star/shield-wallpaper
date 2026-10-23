"""Fetch display data first; only compose a 4K image when visible content changes."""
import hashlib
import importlib
import json
import os
from pathlib import Path


class Paused(BaseException):
    """Not an ordinary feed failure: immediately unwind the renderer's fallbacks."""


def display_state(generator, events, show_standings, sport, label, revision):
    cards=[]
    for event in events:
        item={key:event.get(key) for key in ('sport','phase','completed','state')}
        item['teams']=[(team[0],team[2]) for team in event['teams']]
        item['heading']=generator.nba_heading(event) if event['sport']=='nba' else 'NATIONS LEAGUE'
        item['time_label']=generator.event_time_label(event)
        if event['completed'] or event.get('state')=='in':
            item['scores']=[team[1] for team in event['teams']]
        if event.get('state')=='in':
            item['live_label']=(generator.nba_live_score(event)[1] if event['sport']=='nba'
                                else generator.soccer_live_label(event))
        cards.append(item)
    rows=generator.standings_data(sport) if show_standings else None
    return dict(revision=revision,cards=cards,standings=rows,
                standings_label=label if show_standings else None)


def diagnostic(workspace, event, **details):
    """Keep bounded local history even after Android's shared log buffer rolls over."""
    from datetime import datetime, timezone
    try:
        path=Path(workspace)/'refresh-history.jsonl'
        line=json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),event=event,**details),default=str)+'\n'
        if path.exists() and path.stat().st_size>65536:
            tail=path.read_bytes()[-32768:]
            path.write_bytes(tail.split(b'\n',1)[-1])
        with path.open('a') as output: output.write(line)
    except OSError:
        pass


def render(workspace, gate=None, revision='legacy'):
    try:
        return _render(workspace,gate,revision)
    except Exception as error:
        diagnostic(workspace,'failed',error=repr(error))
        raise


def _render(workspace, gate=None, revision='legacy'):
    def allowed():
        if gate is not None and not gate.isAllowed():
            raise Paused('Projectivy is not visible or the device is asleep')
    allowed()
    root=Path(workspace)
    root.mkdir(parents=True,exist_ok=True)
    diagnostic(root,'started',revision=revision)
    os.chdir(root)
    os.environ['SHIELD_FONT_DIR']=str(root/'fonts')
    import generator
    generator=importlib.reload(generator)

    original_get=generator.get
    def checked_get(url,timeout=8):
        allowed()
        try:
            result=original_get(url,timeout=min(timeout,8))
        except Exception as error:
            diagnostic(root,'feed_failed',url=url,error=repr(error))
            raise
        allowed()
        return result
    generator.get=checked_get

    # Download each logo once, then reuse its small thumbnail for changed scores.
    original_image=generator.remote_image
    def cached_image(url,size):
        allowed()
        key=hashlib.sha256((url+repr(size)).encode()).hexdigest()
        cache=root/'icons'/f'{key}.png'
        from PIL import Image
        if cache.is_file():
            try:
                with Image.open(cache) as image:
                    return image.convert('RGBA')
            except OSError:
                cache.unlink(missing_ok=True)
        image=original_image(url,size)
        allowed()
        if image is not None:
            cache.parent.mkdir(exist_ok=True)
            image.save(cache)
        return image
    generator.remote_image=cached_image

    # Reuse a single standings response for comparison and drawing in this check.
    original_standings=generator.standings_data
    standings={}
    def cached_standings(sport):
        allowed()
        if sport not in standings:
            standings[sport]=original_standings(sport)
        return standings[sport]
    generator.standings_data=cached_standings

    # Cooperatively stop between expensive drawing stages if the user leaves Home.
    for name in ('background','draw_centered_panel','draw_event_row',
                 'draw_compact_event_panel','draw_standings_panel','place_icon'):
        original=getattr(generator,name)
        def checked(*args,_original=original,**kwargs):
            allowed()
            return _original(*args,**kwargs)
        setattr(generator,name,checked)

    saved_path=root/'display_state.json'
    try:
        saved=json.loads(saved_path.read_text())
    except (OSError,ValueError):
        saved={}
    previous=root/Path(saved.get('image','missing')).name
    pending={}
    def before_render(events,show_standings,sport,label):
        allowed()
        state=display_state(generator,events,show_standings,sport,label,revision)
        digest=hashlib.sha256(json.dumps(state,sort_keys=True,default=str).encode()).hexdigest()
        pending['signature']=digest
        diagnostic(root,'display_checked',labels=[card['time_label'] for card in state['cards']],changed=saved.get('signature')!=digest)
        if saved.get('signature')==digest and previous.is_file():
            print('Display unchanged; skipped 4K rendering.')
            return False
        return True
    try:
        generator.main(before_render=before_render)
        allowed()
    except Paused:
        diagnostic(root,'paused')
        print('Paused: Projectivy not visible; no image published.')
        return ''
    if pending.get('signature')==saved.get('signature') and previous.is_file():
        diagnostic(root,'complete',image=previous.name,changed=False)
        return str(previous)
    image=root/'wallpaper.jpg'
    from PIL import Image
    with Image.open(image) as check:
        check.verify()
    digest=hashlib.sha256(image.read_bytes()).hexdigest()[:16]
    target=root/f'wallpaper-{digest}.jpg'
    if not target.exists():
        image.replace(target)
    else:
        image.unlink()
    allowed()
    temp=saved_path.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(signature=pending['signature'],image=target.name)))
    temp.replace(saved_path)
    diagnostic(root,'complete',image=target.name,changed=True)
    return str(target)
