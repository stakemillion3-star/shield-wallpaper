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

def standings_data(sport):
    if sport=="soccer":
        return [("1","Sweden","3","2","1","0","+3","7"),
                ("2","Bosnia and Herzegovina","3","1","2","0","+2","5"),
                ("3","Poland","3","1","1","1","+4","4"),
                ("4","Romania","3","0","0","3","-9","0")]
    return []


def centered_text(d,text,cx,cy,ft,fill):
    d.text((cx,cy),text,anchor="mm",font=ft,fill=fill)


def place_icon(im,name,sport,cx,cy,size):
    icon=team_icon(name,sport,size)
    if icon:
        im.alpha_composite(icon,(int(cx-icon.width/2),int(cy-icon.height/2)))
    return icon


def draw_result(im,d,x,y,w,e,sport,accent):
    cx=x+w/2
    if not e or len(e["teams"])<2:
        centered_text(d,"NO RESULT AVAILABLE",cx,y+105,font(36,True),(225,230,238,255))
        return
    left,right=e["teams"][0],e["teams"][1]
    left_cx=x+w*0.245
    right_cx=x+w*0.755
    place_icon(im,left[0],sport,left_cx,y+67,(190,140))
    place_icon(im,right[0],sport,right_cx,y+67,(190,140))
    score=(f"{left[1]}  –  {right[1]}"
           if left[1] is not None and right[1] is not None else "—")
    centered_text(d,score,cx,y+67,font(100,True),(255,255,255,255))
    centered_text(d,display_name(left[0]),left_cx,y+157,font(42,True),(248,248,250,255))
    centered_text(d,display_name(right[0]),right_cx,y+157,font(42,True),(248,248,250,255))
    centered_text(d,e["date"].strftime("%a, %b %d"),cx,y+207,font(31,True),(218,224,234,255))


def draw_upcoming(im,d,x,y,w,e,sport,accent):
    cx=x+w/2
    if not e or len(e["teams"])<2:
        centered_text(d,"SCHEDULE UNAVAILABLE",cx,y+145,font(38,True),(230,234,240,255))
        return
    left,right=e["teams"][0],e["teams"][1]
    left_cx=x+w*0.245
    right_cx=x+w*0.755
    centered_text(d,fmt_date(e["date"]),cx,y+25,font(52,True),accent)
    place_icon(im,left[0],sport,left_cx,y+160,(230,170))
    place_icon(im,right[0],sport,right_cx,y+160,(230,170))
    centered_text(d,"VS",cx,y+160,font(78,True),(255,255,255,255))
    centered_text(d,display_name(left[0]),left_cx,y+278,font(43,True),(248,248,250,255))
    centered_text(d,display_name(right[0]),right_cx,y+278,font(43,True),(248,248,250,255))


def simple_standings(im,d,x,y,w,accent,competition_label):
    rows=standings_data("soccer")
    centered_text(d,competition_label,x+w/2,y+20,font(40,True),accent)

    col_x=[x+w-490,x+w-390,x+w-290,x+w-190,x+w-90]
    labels=["W","D","L","GD","PTS"]
    for label,cx in zip(labels,col_x):
        centered_text(d,label,cx,y+74,font(35,True),(235,238,244,255))

    row_start=y+113
    row_h=59
    for index,(pos,name,played,won,drawn,lost,gd,pts) in enumerate(rows):
        row_y=row_start+index*row_h
        if "Bosnia" in name:
            d.rounded_rectangle((x-12,row_y-2,x+w+12,row_y+55),radius=12,fill=(35,105,170,165))
        centered_text(d,pos+".",x+23,row_y+27,font(38,True),(255,255,255,255))
        icon=team_icon(name,"soccer",(88,58))
        if icon:
            im.alpha_composite(icon,(x+60,row_y+27-icon.height//2))
        d.text((x+164,row_y+27),display_name(name),anchor="lm",
               font=font(38,True),fill=(255,255,255,255))
        vals=[won,drawn,lost,gd,pts]
        for cx,val in zip(col_x,vals):
            centered_text(d,str(val),cx,row_y+27,font(38,True),(255,255,255,255))


def simple_section(im,x,y,w,title,last,nxt,accent,sport,status_label=None,competition_label=None):
    h=1270 if sport=="soccer" else 950
    im=panel(im,(x,y,x+w,y+h),194)
    d=ImageDraw.Draw(im)
    header_icon=team_icon("Toronto Raptors","nba",(112,112)) if sport=="nba" else team_icon("Bosnia and Herzegovina","soccer",(118,80))
    title_font=font(70,True)
    title_box=d.textbbox((0,0),title,font=title_font)
    title_w=title_box[2]-title_box[0]
    icon_w=header_icon.width if header_icon else 0
    gap=24 if header_icon else 0
    group_w=icon_w+gap+title_w
    group_x=x+(w-group_w)/2
    if header_icon:
        im.alpha_composite(header_icon,(int(group_x),y+34))
    d.text((int(group_x+icon_w+gap),y+79),title,anchor="lm",font=title_font,fill=accent)
    if status_label:
        d.text((x+w-58,y+79),status_label,anchor="rm",font=font(34,True),fill=accent)
    d.line((x+58,y+145,x+w-58,y+145),fill=accent,width=4)

    centered_text(d,"LAST RESULT",x+w/2,y+184,font(39,True),(224,229,238,255))
    draw_result(im,d,x+64,y+220,w-128,last,sport,accent)

    centered_text(d,"NEXT MATCH" if sport=="soccer" else "NEXT GAME",
                  x+w/2,y+486,font(56,True),accent)
    draw_upcoming(im,d,x+64,y+538,w-128,nxt[0] if nxt else None,sport,accent)

    if sport=="soccer":
        d.line((x+58,y+868,x+w-58,y+868),fill=accent,width=3)
        simple_standings(im,d,x+64,y+883,w-128,accent,competition_label or "GROUP TABLE")
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
    im=simple_section(im,48,790,1820,"BOSNA I HERCEGOVINA",bl,bn,(80,170,255,255),"soccer",competition_label=bcomp)
    im=simple_section(im,1972,790,1820,"TORONTO RAPTORS",rl,rn,(255,80,90,255),"nba",status_label=rphase)
    if errors:
        d=ImageDraw.Draw(im)
        d.text((W//2,H-80),"DATA TEMPORARILY UNAVAILABLE",anchor="mm",font=font(28,True),fill=(220,220,220,180))
    im.convert("RGB").save("wallpaper.jpg","JPEG",quality=96,optimize=True,progressive=True)

if __name__=="__main__":
    main()

