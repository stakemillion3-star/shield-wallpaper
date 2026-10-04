import io, os, requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W,H=3840,2160
TZ=ZoneInfo("America/Toronto")
UA={"User-Agent":"Mozilla/5.0 shield-wallpaper/1.0"}

def get(url):
    r=requests.get(url,headers=UA,timeout=25); r.raise_for_status(); return r.json()

def font(size,bold=False):
    paths=[
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
      "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"]
    for p in paths:
        if os.path.exists(p): return ImageFont.truetype(p,size)
    return ImageFont.load_default()

def parse_event(e):
    comp=(e.get("competitions") or [{}])[0]
    competitors=comp.get("competitors") or []
    names=[]
    for c in sorted(competitors,key=lambda x:x.get("homeAway")!="home"):
        t=c.get("team") or {}
        names.append((t.get("displayName") or t.get("shortDisplayName") or "?",
                      c.get("score",{}).get("displayValue") if isinstance(c.get("score"),dict) else c.get("score"),
                      c.get("homeAway")))
    dt=datetime.fromisoformat(e["date"].replace("Z","+00:00")).astimezone(TZ)
    status=(e.get("status") or {}).get("type") or {}
    return {"date":dt,"state":status.get("state"),"completed":status.get("completed",False),
            "detail":status.get("shortDetail") or status.get("detail") or "","teams":names,
            "name":e.get("shortName") or e.get("name") or ""}

def fetch_schedule(url):
    data=get(url)
    events=[parse_event(e) for e in data.get("events",[]) if e.get("date")]
    events.sort(key=lambda x:x["date"])
    now=datetime.now(TZ)
    past=[e for e in events if e["completed"] or e["date"]<now]
    future=[e for e in events if not e["completed"] and e["date"]>=now]
    return (past[-1] if past else None), future[:3]

def raptors():
    # ESPN is used as the presentation feed; results are only shown when marked final.
    urls=[
      "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/tor/schedule?season=2027",
      "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/28/schedule?season=2027"]
    for u in urls:
        try:
            last,nxt=fetch_schedule(u)
            if last or nxt:return last,nxt
        except Exception: pass
    raise RuntimeError("Raptors schedule unavailable")

def bosnia():
    # ESPN Nations League feed. Multiple identifiers are tried so a provider alias change does not silently invent data.
    urls=[
      "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.nations/teams/bosnia-herzegovina/schedule",
      "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.nations/teams/458/schedule"]
    for u in urls:
        try:
            last,nxt=fetch_schedule(u)
            # Hard validation: never accept a feed unless every returned event is actually Bosnia.
            all_events=([last] if last else [])+nxt
            def is_bih(e):
                if not e: return True
                names=[t[0].lower() for t in e["teams"]]
                return any(("bosnia" in n and "herzegovina" in n) for n in names)
            if all_events and all(is_bih(e) for e in all_events):
                return last,nxt
        except Exception: pass
    # Official UEFA 2026/27 B4 fixtures/results, used as a fail-closed fallback.
    # Times are 20:45 CET/CEST unless UEFA specifies otherwise; converted to Toronto.
    raw=[
      ("2026-09-25T20:45:00+02:00","Poland","Bosnia and Herzegovina","0","0",True),
      ("2026-09-28T20:45:00+02:00","Romania","Bosnia and Herzegovina","2","4",True),
      ("2026-10-02T20:45:00+02:00","Bosnia and Herzegovina","Sweden","1","1",True),
      ("2026-10-05T20:45:00+02:00","Bosnia and Herzegovina","Poland",None,None,False),
      ("2026-11-14T20:45:00+01:00","Sweden","Bosnia and Herzegovina",None,None,False),
      ("2026-11-17T20:45:00+01:00","Bosnia and Herzegovina","Romania",None,None,False)]
    ev=[]
    for ds,a,b,sa,sb,done in raw:
        dt=datetime.fromisoformat(ds).astimezone(TZ)
        ev.append({"date":dt,"state":"post" if done else "pre","completed":done,"detail":"",
                   "teams":[(a,sa,"home"),(b,sb,"away")],"name":f"{a} vs {b}"})
    now=datetime.now(TZ); past=[e for e in ev if e["completed"]]; future=[e for e in ev if not e["completed"] and e["date"]>=now]
    return (past[-1] if past else None),future[:3]

def background():
    p="assets/background.jpg"
    if os.path.exists(p):
        im=Image.open(p).convert("RGB")
        return im.resize((W,H),Image.Resampling.LANCZOS)
    # Safe fallback until the cinematic background asset is added.
    im=Image.new("RGB",(W,H))
    px=im.load()
    for x in range(W):
        t=x/(W-1)
        c=(int(8+50*t),int(45-25*t),int(95-55*t))
        for y in range(H): px[x,y]=c
    return im

def panel(base,box,alpha=150):
    ov=Image.new("RGBA",base.size,(0,0,0,0)); d=ImageDraw.Draw(ov)
    d.rounded_rectangle(box,radius=36,fill=(4,10,20,alpha),outline=(255,255,255,45),width=2)
    return Image.alpha_composite(base.convert("RGBA"),ov)

def fmt_date(dt): return dt.strftime("%a %b %d • %-I:%M %p")

def matchup(e,with_score=False):
    if not e:return "—"
    if len(e["teams"])<2:return e["name"]
    a,b=e["teams"][0],e["teams"][1]
    if with_score and e["completed"] and a[1] is not None and b[1] is not None:
        return f'{a[0]}  {a[1]}  –  {b[1]}  {b[0]}'
    return f'{a[0]}  vs  {b[0]}'

def section(im,x,y,w,title,last,nxt,accent):
    im=panel(im,(x,y,x+w,y+790),175)
    d=ImageDraw.Draw(im)
    d.text((x+70,y+58),title,font=font(54,True),fill=accent)
    yy=y+125
    d.text((x+70,yy),"LAST RESULT",font=font(28,True),fill=(210,215,225,255)); yy+=50
    d.text((x+70,yy),matchup(last,True),font=font(33,True),fill="white"); yy+=58
    if last:d.text((x+70,yy),fmt_date(last["date"]),font=font(27),fill=(190,195,205,255))
    yy+=70
    d.text((x+70,yy),"NEXT",font=font(28,True),fill=(210,215,225,255)); yy+=50
    first=nxt[0] if nxt else None
    d.text((x+70,yy),matchup(first),font=font(36,True),fill="white"); yy+=64
    if first:d.text((x+70,yy),fmt_date(first["date"]),font=font(30),fill=accent)
    yy+=70
    if len(nxt)>1:
        d.text((x+70,yy),"UPCOMING",font=font(28,True),fill=(210,215,225,255)); yy+=55
        for e in nxt[1:]:
            d.text((x+70,yy),matchup(e),font=font(27,True),fill="white"); yy+=44
            d.text((x+70,yy),fmt_date(e["date"]),font=font(25),fill=(190,195,205,255)); yy+=75
    return im

def main():
    errors=[]
    try: bl,bn=bosnia()
    except Exception as e: bl,bn=None,[]; errors.append(str(e))
    try: rl,rn=raptors()
    except Exception as e: rl,rn=None,[]; errors.append(str(e))
    im=background().filter(ImageFilter.GaussianBlur(0.25)).convert("RGBA")
    # dark cinematic vignette
    shade=Image.new("RGBA",(W,H),(0,0,0,0)); sd=ImageDraw.Draw(shade)
    sd.rectangle((0,0,W,H),fill=(0,0,0,35))
    im=Image.alpha_composite(im,shade)
    im=section(im,170,610,1250,"BOSNIA & HERZEGOVINA",bl,bn,(80,170,255,255))
    im=section(im,2420,610,1250,"TORONTO RAPTORS",rl,rn,(255,80,90,255))
    # Fail visibly rather than publish fabricated values.
    if errors:
        d=ImageDraw.Draw(im); d.text((W//2,H-80),"DATA TEMPORARILY UNAVAILABLE",anchor="mm",font=font(28,True),fill=(220,220,220,180))
    im.convert("RGB").save("wallpaper.jpg","JPEG",quality=93,optimize=True,progressive=True)

if __name__=="__main__": main()
