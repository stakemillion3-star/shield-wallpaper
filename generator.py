import hashlib, io, json, os, requests
from concurrent.futures import ThreadPoolExecutor
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
    if not cc and "bosnia" in name.lower():
        cc="ba"
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

NATIONS_EVENTS_CACHE=None

NATIONS_EVENTS_CACHE=None

def nations_events():
    # ESPN's competition scoreboard rejects broad date ranges here, so fetch
    # each scheduled Group B4 matchday and combine the returned events.
    global NATIONS_EVENTS_CACHE
    if NATIONS_EVENTS_CACHE is None:
        matchdays=("20260925","20260928","20261002","20261005","20261114","20261117")
        events={}
        for matchday in matchdays:
            data=get(
                "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.nations/scoreboard"
                f"?dates={matchday}",
                timeout=20
            )
            for raw_event in data.get("events",[]):
                if raw_event.get("date"):
                    parsed=parse_event(raw_event)
                    key=(parsed["date"].isoformat(),parsed["name"])
                    events[key]=parsed
        NATIONS_EVENTS_CACHE=sorted(events.values(),key=lambda event:event["date"])
        print(f"Loaded {len(NATIONS_EVENTS_CACHE)} Nations League scoreboard events across the B4 matchdays.")
    return NATIONS_EVENTS_CACHE

def bosnia():
    label="NATIONS LEAGUE  •  LEAGUE B  •  GROUP B4"
    try:
        events=nations_events()
        is_bosnia=lambda event:any(
            "bosnia" in team[0].lower() and "herzegovina" in team[0].lower()
            for team in event["teams"]
        )
        team_events=sorted((event for event in events if is_bosnia(event)),key=lambda e:e["date"])
        now=datetime.now(TZ)
        past=[event for event in team_events if event["completed"] and len(event["teams"])>=2]
        future=[event for event in team_events if not event["completed"] and (event["date"]>=now or event["date"].date()==now.date()) and len(event["teams"])>=2]
        if past or future:
            print(f"Using ESPN scoreboard for Bosnia: {len(past)} completed and {len(future)} upcoming fixtures.")
            return (past[-1] if past else None),future[:3],label
        print("ESPN scoreboard contained no usable Bosnia fixtures; using the bundled fallback schedule.")
    except Exception as exc:
        print(f"ESPN Bosnia scoreboard unavailable; using the bundled fallback schedule: {exc}")
    # Official UEFA 2026/27 B4 fixtures/results, used only if ESPN is unavailable.
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
    now=datetime.now(TZ)
    past=[event for event in ev if event["completed"] and event["date"]<=now]
    future=[event for event in ev if not event["completed"] and (event["date"]>=now or event["date"].date()==now.date())]
    return (past[-1] if past else None),future[:3],label

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

def fmt_date(dt):
    local=dt.astimezone(TZ)
    delta=(local.date()-datetime.now(TZ).date()).days
    if delta==0:
        return "TODAY • "+local.strftime("%-I:%M %p")
    if delta==1:
        return "TOMORROW • "+local.strftime("%-I:%M %p")
    if delta==-1:
        return "YESTERDAY • FINAL"
    return local.strftime("%a %b %d • %-I:%M %p")

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
    # Rebuild Group B4 from completed matches in the same ESPN feed used for
    # Bosnia's last result and next match.
    expected={"Bosnia and Herzegovina","Sweden","Poland","Romania"}
    def canonical(name):
        low=name.lower()
        if "bosnia" in low and "herzegovina" in low:
            return "Bosnia and Herzegovina"
        for team in expected:
            if team.lower()==low:
                return team
        return None
    events=nations_events()
    games={}
    seen=set()
    for event in events:
        if len(event["teams"])<2:
            continue
        home,away=event["teams"][0],event["teams"][1]
        names=[canonical(home[0]),canonical(away[0])]
        seen.update(name for name in names if name)
        # Only matches between the four Group B4 teams contribute to this table.
        if not event["completed"] or not all(names):
            continue
        try:
            home_score,away_score=int(home[1]),int(away[1])
        except (TypeError,ValueError):
            continue
        key=(event["date"].isoformat(),names[0],names[1])
        games[key]=(names[0],names[1],home_score,away_score)
    if not events or not games or not expected.issubset(seen):
        raise ValueError("ESPN scoreboard did not provide a complete Group B4 results set")
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
                     str(stats["draws"]),str(stats["losses"]),f"{gd:+d}",str(stats["points"])))
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


def date_window_events(last,upcoming,sport):
    today=datetime.now(TZ).date()
    now=datetime.now(TZ)
    candidates=([last] if last else [])+(upcoming or [])
    selected=[]
    seen=set()
    for event in candidates:
        if len(event.get("teams",[]))<2:
            continue
        local_date=event["date"].astimezone(TZ).date()
        offset=(local_date-today).days
        if offset not in (-1,0,1):
            continue
        if offset==-1 and not event["completed"]:
            continue
        if offset==1 and event["completed"]:
            continue
        key=(sport,event["date"].isoformat(),tuple(team[0] for team in event["teams"]))
        if key in seen:
            continue
        seen.add(key)
        item=dict(event)
        item["sport"]=sport
        item["day_offset"]=offset
        if offset==-1 or event["completed"]:
            item["kind"]="LAST RESULT"
        elif event.get("state")=="in":
            item["kind"]="LIVE"
        else:
            item["kind"]="NEXT MATCH" if sport=="soccer" else "NEXT GAME"
        selected.append(item)
    return selected

def event_time_label(event):
    offset=event["day_offset"]
    if offset==-1:
        return "YESTERDAY • FINAL"
    if event["completed"]:
        return "TODAY • FINAL"
    if event.get("state")=="in":
        return "LIVE • TODAY"
    return fmt_date(event["date"])

def fitted_font(draw,text,max_width,initial=44,minimum=32):
    size=initial
    while size>minimum and draw.textbbox((0,0),text,font=font(size,True))[2]>max_width:
        size-=2
    return font(size,True)

def draw_event_row(im,draw,event,x,y,w,row_h):
    soccer=event["sport"]=="soccer"
    accent=(80,170,255,255) if soccer else (255,80,90,255)
    left,right=event["teams"][0],event["teams"][1]
    league="NATIONS LEAGUE" if soccer else "NBA"
    heading=league if soccer else league+"  •  "+event["kind"]
    centered_text(draw,heading,x+w/2,y+58,font(54,True),accent)

    left_cx=x+w*0.245
    right_cx=x+w*0.755
    center_x=x+w/2
    # Large, balanced team flags/logos in the same VS layout as the earlier copy.
    icon_size=(540,300) if soccer else (310,310)
    icon_y=y+300
    left_icon=place_icon(im,left[0],event["sport"],left_cx,icon_y,icon_size)
    right_icon=place_icon(im,right[0],event["sport"],right_cx,icon_y,icon_size)
    vs_x=center_x
    if left_icon and right_icon:
        vs_x=((left_cx+left_icon.width/2)+(right_cx-right_icon.width/2))/2
    centered_text(draw,"VS",vs_x,icon_y,font(105,True),(255,255,255,255))

    left_name=display_name(left[0]).upper()
    right_name=display_name(right[0]).upper()
    centered_text(draw,left_name,left_cx,y+535,font(51,True),(248,248,250,255))
    centered_text(draw,right_name,right_cx,y+535,font(51,True),(248,248,250,255))
    # ESPN sometimes sends placeholder 0 scores before kickoff; only show scores
    # for live or completed games. Scheduled events always use VS.
    if event["completed"]:
        score=f"{left[1] or '0'}  –  {right[1] or '0'}"
        centered_text(draw,score,center_x,y+655,font(72,True),(255,255,255,255))
        time_y=y+738
    elif event.get("state")=="in":
        score=f"{left[1] or '0'}  –  {right[1] or '0'}"
        centered_text(draw,score,center_x,y+655,font(72,True),(255,255,255,255))
        time_y=y+738
    else:
        time_y=y+655
    centered_text(draw,event_time_label(event),center_x,time_y,font(56,True),accent)

def draw_standings_panel(im,x,y,w,h,competition_label):
    im=panel(im,(x,y,x+w,y+h),194)
    draw=ImageDraw.Draw(im)
    accent=(80,170,255,255)
    centered_text(draw,competition_label,x+w/2,y+58,font(44,True),accent)
    rows=standings_data("soccer")
    table_w=min(w-150,2320)
    tx=x+(w-table_w)//2
    col_x=[tx+table_w-575,tx+table_w-455,tx+table_w-335,tx+table_w-205,tx+table_w-65]
    for heading,cx in zip(["W","D","L","GD","PTS"],col_x):
        centered_text(draw,heading,cx,y+125,font(37,True),(235,238,244,255))
    row_start=y+183
    row_h=77
    for index,(position,name,played,wins,draws,losses,gd,points) in enumerate(rows):
        row_y=row_start+index*row_h
        if "Bosnia" in name:
            draw.rounded_rectangle((tx+8,row_y-2,tx+table_w-8,row_y+row_h-6),radius=14,
                                   fill=(35,105,170,165))
        centered_text(draw,position+".",tx+44,row_y+row_h/2,font(40,True),(255,255,255,255))
        icon=team_icon(name,"soccer",(94,60))
        if icon:
            im.alpha_composite(icon,(tx+96,row_y+int(row_h/2-icon.height/2)))
        team_name=display_name(name)
        draw.text((tx+220,row_y+row_h/2),team_name,anchor="lm",
                  font=fitted_font(draw,team_name,table_w-900,40,34),fill=(255,255,255,255))
        for cx,value in zip(col_x,[wins,draws,losses,gd,points]):
            centered_text(draw,str(value),cx,row_y+row_h/2,font(40,True),(255,255,255,255))
    return im

def draw_centered_panel(im,events,show_standings,competition_label):
    if not events:
        return im
    events.sort(key=lambda event:(event["date"],0 if event["sport"]=="soccer" else 1))
    # One centered primary matchup card; its proportions are scaled down enough
    # to retain the calm composition and open background of the final copy.
    card_w=2500
    card_h=740
    standings_h=520 if show_standings else 0
    gap=22 if show_standings else 0
    x=(W-card_w)//2
    group_h=card_h+gap+standings_h
    safe_top,safe_bottom=260,1840
    y=max(safe_top,(safe_top+safe_bottom-group_h)//2)
    im=panel(im,(x,y,x+card_w,y+card_h),194)
    draw=ImageDraw.Draw(im)
    draw_event_row(im,draw,events[0],x+70,y+8,card_w-140,card_h-16)

    # Keep a second game visible only when it is also in the requested
    # yesterday/today/tomorrow window, beneath the primary card.
    if len(events)>1:
        second_y=y+card_h+gap
        second_h=min(310, max(260, group_h-card_h-gap))
        im=panel(im,(x,second_y,x+card_w,second_y+second_h),194)
        draw=ImageDraw.Draw(im)
        event=events[1]
        accent=(80,170,255,255) if event["sport"]=="soccer" else (255,80,90,255)
        centered_text(draw,( "NATIONS LEAGUE" if event["sport"]=="soccer" else "NBA" )+"  •  "+event["kind"],
                      W/2,second_y+45,font(36,True),accent)
        left,right=event["teams"][:2]
        place_icon(im,left[0],event["sport"],W*0.27,second_y+143,(220,125) if event["sport"]=="soccer" else (135,135))
        place_icon(im,right[0],event["sport"],W*0.73,second_y+143,(220,125) if event["sport"]=="soccer" else (135,135))
        centered_text(draw,"VS" if not event["completed"] and event.get("state")!="in" else f"{left[1]} – {right[1]}",
                      W/2,second_y+140,font(48,True),(255,255,255,255))
        centered_text(draw,event_time_label(event),W/2,second_y+254,font(35,True),accent)

    if show_standings:
        stand_y=y+card_h+gap
        im=draw_standings_panel(im,x,stand_y,card_w,standings_h,competition_label)
    return im

def main():
    errors=[]
    competition_label="NATIONS LEAGUE  •  LEAGUE B  •  GROUP B4"
    try:
        last,next_games,bcomp=bosnia()
        competition_label=bcomp or competition_label
        soccer_events=date_window_events(last,next_games,"soccer")
    except Exception as exc:
        soccer_events=[]
        errors.append("Bosnia: "+str(exc))
    try:
        last,next_games,rphase=raptors()
        nba_events=date_window_events(last,next_games,"nba")
    except Exception as exc:
        nba_events=[]
        errors.append("Raptors: "+str(exc))
    events=soccer_events+nba_events
    # Prefer today's events; when there are none, show tomorrow's before
    # falling back to yesterday's final result.
    if events:
        preferred_day=next(
            (offset for offset in (0,1,-1)
             if any(event["day_offset"]==offset for event in events)),
            events[0]["day_offset"]
        )
        events=[event for event in events if event["day_offset"]==preferred_day]
    show_standings=any(
        event["sport"]=="soccer" and event["day_offset"]==0
        for event in events
    )
    im=background().convert("RGBA")
    shade=Image.new("RGBA",(W,H),(0,0,0,26))
    ImageDraw.Draw(shade).rectangle((0,0,W,H),fill=(0,0,0,26))
    im=Image.alpha_composite(im,shade)
    if events:
        im=draw_centered_panel(im,events,show_standings,competition_label)
    elif errors:
        print("No games in the three-day display window. "+" | ".join(errors))
    im.convert("RGB").save("wallpaper.jpg","JPEG",quality=96,optimize=True,progressive=True)

    version=datetime.now(TZ).strftime("%Y%m%d")
    digest=hashlib.sha256(open("wallpaper.jpg","rb").read()).hexdigest()[:12]
    feed=[{
        "location":"Shield Sports",
        "title":"Bosnia & Raptors Daily Wallpaper",
        "url_img":f"https://stakemillion3-star.github.io/shield-wallpaper/wallpaper.jpg?v={version}-{digest}"
    }]
    with open("p.json","w",encoding="utf-8") as output:
        json.dump(feed,output,ensure_ascii=False,indent=2)
        output.write("\n")

if __name__=="__main__":
    main()
