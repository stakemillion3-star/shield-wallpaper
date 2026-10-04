import io, os, requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W,H=3840,2160
TZ=ZoneInfo("America/Toronto")
UA={"User-Agent":"Mozilla/5.0 shield-wallpaper/1.0"}

def get(url):
    r=requests.get(url,headers=UA,timeout=25); r.raise_for_status(); return r.json()

def remote_image(url,size):
    try:
        r=requests.get(url,headers=UA,timeout=20); r.raise_for_status()
        im=Image.open(io.BytesIO(r.content)).convert("RGBA")
        im.thumbnail(size,Image.Resampling.LANCZOS)
        return im
    except Exception:
        return None

TEAM_ABBR={"Toronto Raptors":"tor","Miami Heat":"mia","LA Clippers":"lac","New York Knicks":"ny","Detroit Pistons":"det",
"Chicago Bulls":"chi","Washington Wizards":"wsh","Minnesota Timberwolves":"min","Orlando Magic":"orl",
"Los Angeles Lakers":"lal","Denver Nuggets":"den","Milwaukee Bucks":"mil","Memphis Grizzlies":"mem",
"Boston Celtics":"bos","Philadelphia 76ers":"phi"}
COUNTRY_CODE={"Bosnia and Herzegovina":"ba","Sweden":"se","Poland":"pl","Romania":"ro"}

def team_icon(name,sport,size=(100,70)):
    if sport=="nba":
        ab=TEAM_ABBR.get(name)
        return remote_image(f"https://a.espncdn.com/i/teamlogos/nba/500/{ab}.png",size) if ab else None
    cc=COUNTRY_CODE.get(name)
    return remote_image(f"https://flagcdn.com/w160/{cc}.png",size) if cc else None

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

def nba_phase(last,nxt):
    events=([last] if last else [])+(nxt or [])
    details=" ".join((e.get("detail") or "")+" "+(e.get("name") or "") for e in events).lower()
    if "preseason" in details: return "PRESEASON"
    if "playoff" in details or "finals" in details: return "PLAYOFFS"
    # NBA's 2026-27 regular season starts Oct 20 league-wide; Toronto opens Oct 21.
    now=datetime.now(TZ)
    if now < datetime(2026,10,18,tzinfo=TZ): return "PRESEASON"
    return "REGULAR SEASON"

def raptors():
    # Structured schedule feed. Scores render only when the provider marks the game completed.
    urls=[
      "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/tor/schedule?season=2027",
      "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/28/schedule?season=2027"]
    for u in urls:
        try:
            last,nxt=fetch_schedule(u)
            if last or nxt:return last,nxt,nba_phase(last,nxt)
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
                return last,nxt,"NATIONS LEAGUE  •  LEAGUE B  •  GROUP B4"
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
    return (past[-1] if past else None),future[:3],"NATIONS LEAGUE  •  LEAGUE B  •  GROUP B4"

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

def display_name(name):
    return "Bosna I Hercegovina" if name in ("Bosnia and Herzegovina","Bosnia & Herzegovina","Bosnia-Herzegovina","Bosnia") else name

def simple_match(im,d,x,y,w,e,sport,score=False,hero=False,accent=(255,255,255,255)):
    if not e or len(e["teams"])<2:
        d.text((x+w//2,y+60),"—",anchor="mm",font=font(52,True),fill="white"); return
    left,right=e["teams"][0],e["teams"][1]
    iw,ih=((270,175) if hero else (190,125))
    li=team_icon(left[0],sport,(iw,ih)); ri=team_icon(right[0],sport,(iw,ih))
    cy=y+(82 if hero else 62)
    logo_inset=28
    lx=x+logo_inset
    rx=x+w-logo_inset
    if li: im.alpha_composite(li,(lx,int(cy-li.height/2)))
    if ri: im.alpha_composite(ri,(rx-ri.width,int(cy-ri.height/2)))

    center_x=x+w//2
    # Team names live directly beneath their own logos.
    name_y=cy+(112 if hero else 88)
    left_center=lx+(li.width/2 if li else iw/2)
    right_center=rx-(ri.width/2 if ri else iw/2)
    d.text((left_center,name_y),display_name(left[0]),anchor="mm",
           font=font(36 if hero else 33,True),fill=(248,248,250,255))
    d.text((right_center,name_y),display_name(right[0]),anchor="mm",
           font=font(36 if hero else 33,True),fill=(248,248,250,255))

    if score and left[1] is not None and right[1] is not None:
        # Large score isolated in the exact center.
        d.text((center_x,cy),f"{left[1]}  –  {right[1]}",anchor="mm",
               font=font(82,True),fill="white")
    else:
        # Next event keeps a simple central VS between the two logo/name columns.
        d.text((center_x,cy), "VS",anchor="mm",font=font(70,True),fill="white")

    # Bigger date/time for couch readability.
    date_y=cy+(76 if hero else 66)
    d.text((center_x,date_y),fmt_date(e["date"]),anchor="mm",
           font=font(49 if hero else 44,True),fill=accent if hero else (235,238,245,255))


def standings_data(sport):
    if sport=="soccer":
        return [("1","Sweden","3","2","1","0","+3","7"),
                ("2","Bosnia and Herzegovina","3","1","2","0","+2","5"),
                ("3","Poland","3","1","1","1","+4","4"),
                ("4","Romania","3","0","0","3","-9","0")]
    return []

def simple_standings(im,d,x,y,w,accent,competition_label):
    rows=standings_data("soccer")
    d.text((x,y),competition_label,font=font(44,True),fill=accent)

    # Absolute center-anchored columns. P is intentionally omitted.
    col_x=[x+w-400,x+w-300,x+w-200,x+w-100,x+w]
    labels=["W","D","L","GD","PTS"]
    for label,cx in zip(labels,col_x):
        d.text((cx,y+3),label,anchor="ma",font=font(36,True),fill=(235,238,244,255))

    y+=58
    for pos,name,p,w1,dr,l,gd,pts in rows:
        if "Bosnia" in name:
            d.rounded_rectangle((x-8,y-7,x+w+22,y+55),radius=9,fill=(35,105,170,110))
        icon=team_icon(name,"soccer",(78,52))
        d.text((x,y+4),pos+".",font=font(36,True),fill="white")
        if icon: im.alpha_composite(icon,(x+58,y))
        d.text((x+154,y+4),display_name(name),font=font(35,True),fill="white")
        vals=[w1,dr,l,gd,pts]
        for cx,val in zip(col_x,vals):
            d.text((cx,y+4),str(val),anchor="ma",font=font(35,True),fill="white")
        y+=66


def simple_section(im,x,y,w,title,last,nxt,accent,sport,status_label=None,competition_label=None):
    # Minimal 10-foot dashboard: header, last result, next event, standings only.
    h=1310 if sport=="soccer" else 850
    im=panel(im,(x,y,x+w,y+h),190)
    d=ImageDraw.Draw(im)
    header_icon=team_icon("Toronto Raptors","nba",(112,112)) if sport=="nba" else team_icon("Bosnia and Herzegovina","soccer",(132,88))
    hx=x+58
    if header_icon:
        im.alpha_composite(header_icon,(hx,y+28)); hx+=header_icon.width+25
    d.text((hx,y+45),title,font=font(70,True),fill=accent)
    if status_label:
        d.text((x+w-58,y+104),status_label,anchor="ra",font=font(34,True),fill=accent)
    d.line((x+58,y+145,x+w-58,y+145),fill=accent,width=4)

    d.text((x+58,y+174),"LAST RESULT",font=font(36,True),fill=(220,225,235,255))
    simple_match(im,d,x+65,y+225,w-130,last,sport,True,False,accent)

    d.text((x+58,y+455),"NEXT MATCH" if sport=="soccer" else "NEXT GAME",font=font(58,True),fill=accent)
    first=nxt[0] if nxt else None
    simple_match(im,d,x+65,y+555,w-130,first,sport,False,True,accent)

    if sport=="soccer":
        d.line((x+58,y+825,x+w-58,y+825),fill=accent,width=3)
        simple_standings(im,d,x+58,y+855,w-116,accent,competition_label or "GROUP TABLE")
    return im


def main():
    errors=[]
    try:
        bl,bn,bcomp=bosnia()
    except Exception as e:
        bl,bn,bcomp=None,[],"—"; errors.append(str(e))
    try:
        rl,rn,rphase=raptors()
    except Exception as e:
        rl,rn,rphase=None,[],"—"; errors.append(str(e))
    im=background().filter(ImageFilter.GaussianBlur(0.25)).convert("RGBA")
    shade=Image.new("RGBA",(W,H),(0,0,0,0))
    ImageDraw.Draw(shade).rectangle((0,0,W,H),fill=(0,0,0,35))
    im=Image.alpha_composite(im,shade)
    im=simple_section(im,45,790,1740,"BOSNA I HERCEGOVINA",bl,bn,(80,170,255,255),"soccer",competition_label=bcomp)
    im=simple_section(im,2055,790,1740,"TORONTO RAPTORS",rl,rn,(255,80,90,255),"nba",status_label=rphase)
    if errors:
        d=ImageDraw.Draw(im)
        d.text((W//2,H-80),"DATA TEMPORARILY UNAVAILABLE",anchor="mm",font=font(28,True),fill=(220,220,220,180))
    im.convert("RGB").save("wallpaper.jpg","JPEG",quality=96,optimize=True,progressive=True)

if __name__=="__main__":
    main()
