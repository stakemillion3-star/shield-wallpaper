import hashlib, io, json, os, requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W,H=3840,2160
TZ=ZoneInfo("America/Toronto")
UA={"User-Agent":"Mozilla/5.0 shield-wallpaper/1.0"}

def get(url,timeout=25):
    r=requests.get(url,headers=UA,timeout=timeout); r.raise_for_status(); return r.json()

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
    # Download enough resolution for the upcoming flags to render much larger than result flags.
    return remote_image(f"https://flagcdn.com/w640/{cc}.png",size) if cc else None

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

def group_standings_from_results():
    # Rebuild B4 from all four teams' ESPN schedules as a fallback when the
    # league table is late to reflect a completed match.
    team_slugs={
        "bosnia-herzegovina":"Bosnia and Herzegovina",
        "sweden":"Sweden",
        "poland":"Poland",
        "romania":"Romania"
    }
    expected=set(team_slugs.values())
    def canonical(name):
        low=name.lower()
        if "bosnia" in low:
            return "Bosnia and Herzegovina"
        for team in expected:
            if team.lower()==low:
                return team
        return None
    def fetch_schedule_for(slug):
        url=f"https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.nations/teams/{slug}/schedule?season=2026"
        return slug,get(url,timeout=12)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(fetch_schedule_for,team_slugs))
    games={}
    teams_seen=set()
    for slug,data in responses:
        events=data.get("events",[])
        own_team=team_slugs[slug]
        if not any(any(canonical(t[0])==own_team for t in parse_event(e)["teams"]) for e in events if e.get("date")):
            raise ValueError(f"ESPN schedule contained no fixtures for {own_team}")
        teams_seen.add(own_team)
        for event in events:
            if not event.get("date"):
                continue
            parsed=parse_event(event)
            if not parsed["completed"] or len(parsed["teams"])<2:
                continue
            home,away=parsed["teams"][0],parsed["teams"][1]
            home_name,away_name=canonical(home[0]),canonical(away[0])
            if home_name not in expected or away_name not in expected:
                continue
            try:
                home_score,away_score=int(home[1]),int(away[1])
            except (TypeError,ValueError):
                continue
            key=(parsed["date"].isoformat(),home_name,away_name)
            games[key]=(home_name,away_name,home_score,away_score)
    if teams_seen!=expected or not games:
        raise ValueError("ESPN schedules did not provide a complete Group B4 results set")
    table={name:{"played":0,"wins":0,"draws":0,"losses":0,"gf":0,"ga":0,"points":0}
           for name in expected}
    for home,away,hs,as_ in games.values():
        table[home]["played"]+=1
        table[away]["played"]+=1
        table[home]["gf"]+=hs; table[home]["ga"]+=as_
        table[away]["gf"]+=as_; table[away]["ga"]+=hs
        if hs>as_:
            table[home]["wins"]+=1; table[away]["losses"]+=1; table[home]["points"]+=3
        elif hs<as_:
            table[away]["wins"]+=1; table[home]["losses"]+=1; table[away]["points"]+=3
        else:
            table[home]["draws"]+=1; table[away]["draws"]+=1
            table[home]["points"]+=1; table[away]["points"]+=1
    ordered=sorted(table.items(),key=lambda item:(
        item[1]["points"],item[1]["gf"]-item[1]["ga"],item[1]["gf"]),reverse=True)
    rows=[]
    for pos,(name,stats) in enumerate(ordered,1):
        gd=stats["gf"]-stats["ga"]
        rows.append((str(pos),name,str(stats["played"]),str(stats["wins"]),
                     str(stats["draws"]),str(stats["losses"]),
                     f"{gd:+d}",str(stats["points"])))
    return rows


def standings_data(sport):
    if sport!="soccer":
        return []
    fallback=[
        ("1","Sweden","3","2","1","0","+3","7"),
        ("2","Bosnia and Herzegovina","3","1","2","0","+2","5"),
        ("3","Poland","3","1","1","1","+4","4"),
        ("4","Romania","3","0","0","3","-9","0")
    ]
    live_rows=None
    try:
        # ESPN publishes soccer standings on the /apis/v2 route (not site/v2).
        data=get("https://site.api.espn.com/apis/v2/sports/soccer/uefa.nations/standings?season=2026")
        group=next((g for g in data.get("children",[])
                    if "b4" in (g.get("name","")+g.get("abbreviation","")).lower()),None)
        entries=(group or {}).get("standings",{}).get("entries",[])
        parsed_rows=[]
        aliases={
            "gamesplayed":("gamesplayed","played"),
            "wins":("wins","win"),
            "draws":("ties","draws","draw"),
            "losses":("losses","loss"),
            "gd":("pointdifferential","goaldifference","goaldiff","differential"),
            "points":("points","leaguepoints","totalpoints"),
            "goalsfor":("pointsfor","goalsfor","goalsscored")
        }
        for entry in entries:
            team=entry.get("team") or {}
            name=team.get("displayName") or team.get("name","")
            if "bosnia" in name.lower():
                name="Bosnia and Herzegovina"
            elif name.lower() in ("sweden","poland","romania"):
                name=name.title()
            stats={str(s.get("name","")).lower():s for s in entry.get("stats",[])}
            stats.update({str(s.get("abbreviation","")).lower():s for s in entry.get("stats",[]) if s.get("abbreviation")})
            def value_for(key):
                for alias in aliases[key]:
                    stat=stats.get(alias)
                    if stat:
                        return str(stat.get("displayValue",stat.get("value","")))
                return ""
            played,wins,draws,losses,gd,points=(value_for(k) for k in ("gamesplayed","wins","draws","losses","gd","points"))
            goals_for=value_for("goalsfor") or "0"
            if not all((name,played,wins,draws,losses,gd,points)):
                raise ValueError("ESPN standings row is missing a required table value")
            number=lambda value:int(str(value).replace("+","").replace(",",""))
            parsed_rows.append(((number(points),number(gd),number(goals_for)),
                                (name,played,wins,draws,losses,gd,points)))
        required={"Sweden","Bosnia and Herzegovina","Poland","Romania"}
        if len(parsed_rows)!=4 or {r[1][0] for r in parsed_rows}!=required:
            raise ValueError("ESPN did not return the four expected Group B4 teams")
        parsed_rows.sort(key=lambda row:row[0],reverse=True)
        live_rows=[(str(i),*row[1]) for i,row in enumerate(parsed_rows,1)]
    except Exception as exc:
        print(f"ESPN Group B4 table endpoint unavailable: {exc}")

    try:
        result_rows=group_standings_from_results()
        if live_rows:
            live_by_team={row[1]:row[2:] for row in live_rows}
            result_by_team={row[1]:row[2:] for row in result_rows}
            if live_by_team!=result_by_team:
                print("ESPN table is behind completed B4 scores; using standings rebuilt from final results.")
            else:
                print("ESPN Group B4 table matches the table rebuilt from final results.")
        else:
            print("ESPN Group B4 table rebuilt from completed team schedules.")
        return result_rows
    except Exception as exc:
        if live_rows:
            print(f"Group B4 result fallback unavailable; using ESPN table: {exc}")
            return live_rows
        print(f"Live Group B4 sources unavailable; using the bundled fallback table: {exc}")
        return fallback

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
        centered_text(d,"NO RESULT AVAILABLE",cx,y+80,font(32,True),(225,230,238,255))
        return
    left,right=e["teams"][0],e["teams"][1]
    left_cx=x+w*0.245
    right_cx=x+w*0.755
    place_icon(im,left[0],sport,left_cx,y+65,(150,105))
    place_icon(im,right[0],sport,right_cx,y+65,(150,105))
    score=(f"{left[1]}  –  {right[1]}"
           if left[1] is not None and right[1] is not None else "—")
    centered_text(d,score,cx,y+65,font(60,True),(255,255,255,255))
    centered_text(d,display_name(left[0]),left_cx,y+150,font(30,True),(248,248,250,255))
    centered_text(d,display_name(right[0]),right_cx,y+150,font(30,True),(248,248,250,255))


def draw_upcoming(im,d,x,y,w,e,sport,accent):
    cx=x+w/2
    if not e or len(e["teams"])<2:
        centered_text(d,"SCHEDULE UNAVAILABLE",cx,y+260,font(44,True),(230,234,240,255))
        return
    left,right=e["teams"][0],e["teams"][1]
    left_cx=x+w*0.245
    right_cx=x+w*0.755
    def upcoming_icon_size(name):
        if sport=="soccer":
            # Matchup flags and logos are slightly smaller to open up the panel.
            return (500,250) if "Bosnia" in name else (400,250)
        return (250,250)
    left_icon=place_icon(im,left[0],sport,left_cx,y+65,upcoming_icon_size(left[0]))
    right_icon=place_icon(im,right[0],sport,right_cx,y+65,upcoming_icon_size(right[0]))
    vs_cx=cx
    if left_icon and right_icon:
        left_edge=left_cx+left_icon.width/2
        right_edge=right_cx-right_icon.width/2
        vs_cx=(left_edge+right_edge)/2
    centered_text(d,"VS",vs_cx,y+65,font(96,True),(255,255,255,255))
    centered_text(d,display_name(left[0]),left_cx,y+245,font(48,True),(248,248,250,255))
    centered_text(d,display_name(right[0]),right_cx,y+245,font(48,True),(248,248,250,255))
    centered_text(d,fmt_date(e["date"]),cx,y+325,font(52,True),accent)


def simple_standings(im,x,y,w,h,accent,competition_label):
    im=panel(im,(x,y,x+w,y+h),194)
    d=ImageDraw.Draw(im)
    rows=standings_data("soccer")
    centered_text(d,competition_label,x+w/2,y+38,font(42,True),accent)

    col_x=[x+w-500,x+w-400,x+w-300,x+w-200,x+w-100]
    labels=["W","D","L","GD","PTS"]
    for label,cx in zip(labels,col_x):
        centered_text(d,label,cx,y+90,font(36,True),(235,238,244,255))

    row_start=y+120
    row_h=72
    for index,(pos,name,played,won,drawn,lost,gd,pts) in enumerate(rows):
        row_y=row_start+index*row_h
        if "Bosnia" in name:
            d.rounded_rectangle((x+14,row_y-1,x+w-14,row_y+68),radius=12,fill=(35,105,170,165))
        centered_text(d,pos+".",x+40,row_y+36,font(40,True),(255,255,255,255))
        icon=team_icon(name,"soccer",(90,58))
        if icon:
            im.alpha_composite(icon,(x+82,row_y+36-icon.height//2))
        d.text((x+205,row_y+36),display_name(name),anchor="lm",
               font=font(42,True),fill=(255,255,255,255))
        vals=[won,drawn,lost,gd,pts]
        for cx,val in zip(col_x,vals):
            centered_text(d,str(val),cx,row_y+36,font(40,True),(255,255,255,255))
    return im


def simple_section(im,x,y,w,title,last,nxt,accent,sport,status_label=None,competition_label=None):
    h=840
    im=panel(im,(x,y,x+w,y+h),194)
    d=ImageDraw.Draw(im)
    if status_label:
        d.text((x+w-58,y+60),status_label,anchor="rm",font=font(34,True),fill=accent)

    centered_text(d,"NEXT MATCH" if sport=="soccer" else "NEXT GAME",
                  x+w/2,y+55,font(64,True),accent)
    draw_upcoming(im,d,x+64,y+170,w-128,nxt[0] if nxt else None,sport,accent)
    d.line((x+58,y+535,x+w-58,y+535),fill=accent,width=3)

    centered_text(d,"LAST RESULT",x+w/2,y+580,font(40,True),(224,229,238,255))
    draw_result(im,d,x+64,y+600,w-128,last,sport,accent)
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
    im=background().convert("RGBA")
    shade=Image.new("RGBA",(W,H),(0,0,0,0))
    ImageDraw.Draw(shade).rectangle((0,0,W,H),fill=(0,0,0,35))
    im=Image.alpha_composite(im,shade)
    im=simple_section(im,20,450,1890,"BOSNA I HERCEGOVINA",bl,bn,(80,170,255,255),"soccer",competition_label=bcomp)
    im=simple_section(im,1930,450,1890,"TORONTO RAPTORS",rl,rn,(255,80,90,255),"nba",status_label=rphase)
    im=simple_standings(im,45,1310,1840,430,(80,170,255,255),bcomp or "GROUP TABLE")
    if errors:
        d=ImageDraw.Draw(im)
        d.text((W//2,H-80),"DATA TEMPORARILY UNAVAILABLE",anchor="mm",font=font(28,True),fill=(220,220,220,180))
    im.convert("RGB").save("wallpaper.jpg","JPEG",quality=96,optimize=True,progressive=True)

    # Overflight wallpaper provider feed. Daily query values tell Projectivy
    # a new image URI after each scheduled render, avoiding stale image caches.
    version=datetime.now(TZ).strftime("%Y%m%d")
    digest=hashlib.sha256(open("wallpaper.jpg","rb").read()).hexdigest()[:12]
    feed=[{
        "location":"Shield Sports",
        "title":"Bosnia & Raptors Daily Wallpaper",
        "url_img":f"https://stakemillion3-star.github.io/shield-wallpaper/wallpaper.jpg?v={version}-{digest}"
    }]
    with open("p.json","w",encoding="utf-8") as f:
        json.dump(feed,f,ensure_ascii=False,indent=2)
        f.write("\n")

if __name__=="__main__":
    main()
