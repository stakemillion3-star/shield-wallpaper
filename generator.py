import hashlib, io, json, os, requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W,H=3840,2160
TZ=ZoneInfo("America/Toronto")
UA={"User-Agent":"Mozilla/5.0 shield-wallpaper/1.0"}
DISPLAY_DATE=None
NBA_LOGOS={}
NBA_STANDINGS_CACHE=None

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
        url=NBA_LOGOS.get(name)
        if url:
            icon=remote_image(url,size)
        else:
            ab=TEAM_ABBR.get(name)
            icon=remote_image(f"https://a.espncdn.com/i/teamlogos/nba/500/{ab}.png",size) if ab else None
        if icon and name=="Toronto Raptors":
            pixels=icon.load()
            for py in range(icon.height):
                for px in range(icon.width):
                    r,g,b,a=pixels[px,py]
                    if a and max(r,g,b)<110:
                        pixels[px,py]=(int(r*0.45),int(g*0.45),int(b*0.45),a)
        return icon
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
    if now < datetime(2026,10,20,tzinfo=TZ): return "PRESEASON"
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
    today=DISPLAY_DATE or datetime.now(TZ).date()
    delta=(local.date()-today).days
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

def nba_regular_standings_data(season):
    data=get(f"https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season={season}")
    east={"ATL","BOS","BKN","CHA","CHI","CLE","DET","IND","MIA","MIL","NY","NYK","ORL","PHI","TOR","WSH"}
    rows=[]
    def walk(node,conf=None):
        label=(str(node.get("name",""))+" "+str(node.get("abbreviation",""))).lower()
        if "eastern conference" in label or label.strip().endswith(" east") or label=="east": conf="east"
        elif "western conference" in label or label.strip().endswith(" west") or label=="west": conf="west"
        elif any(x in label for x in ("atlantic division","central division","southeast division")): conf="east"
        elif any(x in label for x in ("northwest division","pacific division","southwest division")): conf="west"
        for entry in (node.get("standings") or {}).get("entries",[]):
            team=entry.get("team") or {}
            name=team.get("displayName") or team.get("name") or ""
            abbr=str(team.get("abbreviation","")).upper()
            team_conf=conf or ("east" if abbr in east else "west" if abbr else None)
            stats={}
            for stat in entry.get("stats",[]):
                for key in (stat.get("name"),stat.get("abbreviation")):
                    if key: stats[str(key).lower().replace("_","").replace(" ","")]=stat
            def val(*keys):
                for key in keys:
                    stat=stats.get(key.lower().replace("_","").replace(" ",""))
                    if stat: return str(stat.get("displayValue",stat.get("value","")))
                return ""
            wins=val("wins","win","w"); losses=val("losses","loss","l")
            pct=val("winPercent","winpercentage","pct"); gb=val("gamesBehind","gb")
            seed=val("playoffSeed","seed")
            logos=team.get("logos") or []
            logo=team.get("logo") or (logos[0].get("href") if logos else None)
            if logo and name: NBA_LOGOS[name]=logo
            if team_conf=="east" and name and wins!="" and losses!="":
                try: numeric_seed=int(seed) if seed else 99
                except ValueError: numeric_seed=99
                try: numeric_pct=float(pct)
                except (ValueError,TypeError): numeric_pct=float(wins)/(float(wins)+float(losses)) if float(wins)+float(losses) else 0
                rows.append({"name":name,"abbr":abbr,"wins":wins,"losses":losses,
                             "pct":pct or f"{numeric_pct:.3f}","gb":gb,"seed":numeric_seed})
        for child in node.get("children",[]) or []: walk(child,conf)
    for group in data.get("children",[]) or []: walk(group)
    if not rows: walk(data)
    if len(rows)<10 or not any(row["abbr"]=="TOR" for row in rows):
        raise ValueError("ESPN regular-season Eastern standings are incomplete")
    rows.sort(key=lambda row:(row["seed"],row["name"]))
    leader=rows[0]
    for i,row in enumerate(rows,1):
        row["rank"]=str(row["seed"] if row["seed"]<99 else i)
        if row["pct"].startswith("0."): row["pct"]=row["pct"][1:]
        if not row["gb"]:
            gb=((int(leader["wins"])-int(row["wins"]))+(int(row["losses"])-int(leader["losses"])))/2
            row["gb"]="—" if gb==0 else f"{gb:.1f}"
    return rows


def nba_standings_data():
    global NBA_STANDINGS_CACHE
    if NBA_STANDINGS_CACHE is not None:
        return NBA_STANDINGS_CACHE
    # ESPN does not expose an NBA preseason standings table, so derive records
    # from completed preseason games on ESPN's daily scoreboard.
    today=datetime.now(TZ).date()
    season=today.year+(1 if today.month>=7 else 0)
    if today>=datetime(season-1,10,20,tzinfo=TZ).date():
        rows=nba_regular_standings_data(season)
        toronto=next(row for row in rows if row["abbr"]=="TOR")
        toronto_index=rows.index(toronto)
        start=max(0,min(toronto_index-3,len(rows)-4))
        NBA_STANDINGS_CACHE=rows[start:start+4]
        print("ESPN regular-season Eastern table:",[(r["rank"],r["name"],r["wins"],r["losses"],r["pct"],r["gb"]) for r in NBA_STANDINGS_CACHE])
        return NBA_STANDINGS_CACHE
    start_date=datetime(season-1,9,15,tzinfo=TZ).date()
    end_date=min(today,datetime(season-1,10,19,tzinfo=TZ).date())
    dates=[(start_date+__import__("datetime").timedelta(days=i)).strftime("%Y%m%d")
           for i in range((end_date-start_date).days+1)]
    urls=[f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={day}&seasontype=1&limit=100"
          for day in dates]
    with ThreadPoolExecutor(max_workers=6) as pool:
        scoreboards=list(pool.map(get,urls))
    east={"ATL","BOS","BKN","CHA","CHI","CLE","DET","IND","MIA","MIL","NY","NYK","ORL","PHI","TOR","WSH"}
    records={}
    for data in scoreboards:
        for event in data.get("events",[]) or []:
            comp=(event.get("competitions") or [{}])[0]
            status=((event.get("status") or {}).get("type") or {})
            if not status.get("completed"):
                continue
            competitors=comp.get("competitors") or []
            if len(competitors)!=2:
                continue
            teams=[]
            for competitor in competitors:
                team=competitor.get("team") or {}
                name=team.get("displayName") or team.get("name") or ""
                abbr=str(team.get("abbreviation","")).upper()
                score=competitor.get("score")
                if isinstance(score,dict):
                    score=score.get("displayValue",score.get("value"))
                try:
                    score=int(str(score).replace(",",""))
                except (TypeError,ValueError):
                    continue
                teams.append((name,abbr,score,team))
            if len(teams)!=2:
                continue
            for name,abbr,score,team in teams:
                records.setdefault(abbr,{"name":name,"played":0,"wins":0,"losses":0})
                logos=team.get("logos") or []
                logo=team.get("logo") or (logos[0].get("href") if logos else None)
                if logo and name:
                    NBA_LOGOS[name]=logo
            home,away=teams
            records[home[1]]["played"]+=1
            records[away[1]]["played"]+=1
            if home[2]>away[2]:
                records[home[1]]["wins"]+=1
                records[away[1]]["losses"]+=1
            elif away[2]>home[2]:
                records[away[1]]["wins"]+=1
                records[home[1]]["losses"]+=1
    rows=[]
    for abbr in east:
        rec=records.get(abbr)
        if rec:
            pct=rec["wins"]/rec["played"] if rec["played"] else 0.0
            rows.append({"name":rec["name"],"abbr":abbr,"wins":rec["wins"],
                         "losses":rec["losses"],"pct":pct,"played":rec["played"]})
    toronto=next((row for row in rows if row["abbr"]=="TOR"),None)
    if not toronto:
        NBA_STANDINGS_CACHE=[]
        raise ValueError("ESPN has not posted completed 2026 preseason scores for Toronto")
    rows.sort(key=lambda row:(-row["pct"],-row["wins"],row["losses"],row["name"]))
    leader=rows[0]
    for i,row in enumerate(rows,1):
        row["rank"]=str(i)
        row["pct"]=f"{row['pct']:.3f}"[1:] if row["pct"]<1 else f"{row['pct']:.3f}"
        gb=((leader["wins"]-row["wins"])+(row["losses"]-leader["losses"]))/2
        row["gb"]="—" if gb==0 else f"{gb:.1f}"
    toronto_index=rows.index(toronto)
    start=max(0,min(toronto_index-3,len(rows)-4))
    leaders=rows[start:start+4]
    NBA_STANDINGS_CACHE=leaders
    print("ESPN preseason Eastern table:",[(r["rank"],r["name"],r["wins"],r["losses"],r["pct"],r["gb"]) for r in leaders])
    return leaders


def standings_data(sport):
    if sport=="nba":
        try: return nba_standings_data()
        except Exception as exc:
            print(f"ESPN NBA preseason standings unavailable: {exc}")
            return []
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
    today=DISPLAY_DATE or datetime.now(TZ).date()
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

def regular_nba_event_stack(events, now=None):
    # All transitions follow the user's Toronto calendar, including the
    # noon cutoff for moving yesterday's result out of the compact card.
    now=now or datetime.now(TZ)
    before_noon=now.astimezone(TZ).hour<12
    active_today=[e for e in events if e["day_offset"]==0 and not e["completed"]]
    final_today=[e for e in events if e["day_offset"]==0 and e["completed"]]
    final_yesterday=[e for e in events if e["day_offset"]==-1 and e["completed"]]
    next_tomorrow=[e for e in events if e["day_offset"]==1 and not e["completed"]]

    if active_today:
        if final_yesterday:
            if before_noon:
                return [active_today[0],final_yesterday[-1]],False
            return [active_today[0]],True
        if next_tomorrow:
            return [active_today[0],next_tomorrow[0]],False
        return [active_today[0]],True

    if final_today:
        if next_tomorrow:
            # The next game takes the main card after today's result is final.
            return [next_tomorrow[0],final_today[-1]],False
        return [final_today[-1]],True

    if next_tomorrow:
        if final_yesterday and before_noon:
            return [next_tomorrow[0],final_yesterday[-1]],False
        return [next_tomorrow[0]],True

    if final_yesterday:
        return [final_yesterday[-1]],not before_noon
    return [],False


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
    phase=event.get("phase","NBA")
    league="NATIONS LEAGUE" if soccer else ("PRESEASON" if phase=="PRESEASON" else "NBA")
    heading=league if soccer or league=="PRESEASON" else league+"  •  "+event["kind"]
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
    centered_text(draw,left_name,left_cx,y+505,font(51,True),(248,248,250,255))
    centered_text(draw,right_name,right_cx,y+505,font(51,True),(248,248,250,255))
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
    centered_text(draw,event_time_label(event),center_x,time_y,font(64,True),accent)

def draw_standings_panel(im,x,y,w,h,competition_label,sport="soccer"):
    im=panel(im,(x,y,x+w,y+h),194); draw=ImageDraw.Draw(im)
    if sport=="nba":
        rows=standings_data("nba")
        col_x=[x+w-510,x+w-390,x+w-260,x+w-120]
        for heading,cx in zip(["W","L","PCT","GB"],col_x):
            centered_text(draw,heading,cx,y+58,font(31,True),(235,238,244,255))
        slot_h=max(58,(h-100)//max(1,len(rows)))
        row_h=58
        row_start=y+86
        for i,row in enumerate(rows):
            ry=row_start+i*slot_h+(slot_h-row_h)//2
            if row["abbr"]=="TOR" or "raptors" in row["name"].lower():
                draw.rounded_rectangle((x+22,ry-2,x+w-22,ry+row_h-4),radius=12,
                                       fill=(76,8,18,232),outline=(255,92,104,150),width=2)
            centered_text(draw,row["rank"]+".",x+64,ry+row_h/2,font(32,True),(255,255,255,255))
            icon=team_icon(row["name"],"nba",(38,38))
            if icon: im.alpha_composite(icon,(x+104,ry+int(row_h/2-icon.height/2)))
            draw.text((x+164,ry+row_h/2),row["name"],anchor="lm",
                      font=fitted_font(draw,row["name"],w-900,32,25),fill=(255,255,255,255))
            for cx,value in zip(col_x,[row["wins"],row["losses"],row["pct"],row["gb"]]):
                centered_text(draw,str(value),cx,ry+row_h/2,font(31,True),(255,255,255,255))
        return im
    rows=standings_data("soccer")
    table_w=min(w-150,2320); tx=x+(w-table_w)//2
    col_x=[tx+table_w-575,tx+table_w-455,tx+table_w-335,tx+table_w-205,tx+table_w-65]
    for heading,cx in zip(["W","D","L","GD","PTS"],col_x):
        centered_text(draw,heading,cx,y+58,font(37,True),(235,238,244,255))
    for i,(position,name,played,wins,draws,losses,gd,points) in enumerate(rows):
        ry=y+97+i*77
        if "Bosnia" in name:
            draw.rounded_rectangle((tx+8,ry-2,tx+table_w-8,ry+71),radius=14,fill=(35,105,170,165))
        centered_text(draw,position+".",tx+44,ry+38,font(40,True),(255,255,255,255))
        icon=team_icon(name,"soccer",(94,60))
        if icon: im.alpha_composite(icon,(tx+96,ry+38-icon.height//2))
        draw.text((tx+220,ry+38),display_name(name),anchor="lm",
                  font=fitted_font(draw,display_name(name),table_w-900,40,34),fill=(255,255,255,255))
        for cx,value in zip(col_x,[wins,draws,losses,gd,points]):
            centered_text(draw,str(value),cx,ry+38,font(40,True),(255,255,255,255))
    return im


def draw_centered_panel(im,events,show_standings,competition_label):
    if not events:
        return im
    # The primary matchup stays full-size. An adjacent result or next game
    # uses a compact row, with standings below both during the regular season.
    card_w=2500
    card_h=740
    secondary_h=300 if len(events)>1 else 0
    standings_h=450 if show_standings else 0
    gap=22
    layer_gaps=(int(secondary_h>0)+int(standings_h>0))*gap
    group_h=card_h+secondary_h+standings_h+layer_gaps
    x=(W-card_w)//2
    safe_top,safe_bottom=260,1840
    y=max(safe_top,(safe_top+safe_bottom-group_h)//2+65)
    im=panel(im,(x,y,x+card_w,y+card_h),194)
    draw=ImageDraw.Draw(im)
    draw_event_row(im,draw,events[0],x+70,y+8,card_w-140,card_h-16)

    next_y=y+card_h
    if secondary_h:
        next_y+=gap
        im=panel(im,(x,next_y,x+card_w,next_y+secondary_h),194)
        draw=ImageDraw.Draw(im)
        event=events[1]
        accent=(80,170,255,255) if event["sport"]=="soccer" else (255,80,90,255)
        heading="LAST RESULT" if event["kind"]=="LAST RESULT" else (
            "NEXT MATCH" if event["sport"]=="soccer" else "NEXT GAME")
        centered_text(draw,heading,W/2,next_y+38,font(34,True),accent)
        left,right=event["teams"][:2]
        left_cx=x+card_w*0.245
        right_cx=x+card_w*0.755
        icon_size=(180,115) if event["sport"]=="soccer" else (115,115)
        place_icon(im,left[0],event["sport"],left_cx,next_y+132,icon_size)
        place_icon(im,right[0],event["sport"],right_cx,next_y+132,icon_size)
        if event["completed"] or event.get("state")=="in":
            score=f"{left[1] or '0'} – {right[1] or '0'}"
            centered_text(draw,score,W/2,next_y+132,font(56,True),(255,255,255,255))
        else:
            centered_text(draw,"VS",W/2,next_y+132,font(52,True),(255,255,255,255))
        centered_text(draw,display_name(left[0]).upper(),left_cx,next_y+220,font(30,True),(248,248,250,255))
        centered_text(draw,display_name(right[0]).upper(),right_cx,next_y+220,font(30,True),(248,248,250,255))
        centered_text(draw,event_time_label(event),W/2,next_y+270,font(32,True),accent)
        next_y+=secondary_h

    if show_standings:
        stand_y=next_y+gap
        im=draw_standings_panel(im,x,stand_y,card_w,standings_h,competition_label,
                                sport=events[0]["sport"])
    return im


def main():
    global DISPLAY_DATE
    errors=[]
    try:
        with open("preview.json",encoding="utf-8") as source: preview=json.load(source)
        expires_raw=preview.get("expires_at")
        expires=datetime.fromisoformat(expires_raw) if expires_raw else None
        if expires and expires.tzinfo is None: expires=expires.replace(tzinfo=TZ)
        if not expires or datetime.now(TZ)<expires:
            DISPLAY_DATE=date.fromisoformat(preview["as_of"])
            print(f"Preview date active: {DISPLAY_DATE}")
    except (OSError,ValueError,KeyError,TypeError): pass

    competition_label="NATIONS LEAGUE • LEAGUE B • GROUP B4"
    try:
        bl,bn,bcomp=bosnia()
        competition_label=bcomp or competition_label
        soccer_events=date_window_events(bl,bn,"soccer")
    except Exception as e:
        soccer_events=[]; errors.append("Bosnia: "+str(e))

    rphase="PRESEASON"
    try:
        rl,rn,rphase=raptors()
        raw_nba_events=date_window_events(rl,rn,"nba")
        for event in raw_nba_events: event["phase"]=rphase
        if rphase=="PRESEASON":
            nba_events=sorted(raw_nba_events,key=lambda event:event["date"])[:1]
            nba_show_standings=False
        else:
            nba_events,nba_show_standings=regular_nba_event_stack(raw_nba_events)
    except Exception as e:
        nba_events=[]; errors.append("Raptors: "+str(e))

    # In regular season, preserve the NBA matchup/result pair as one stack.
    # If a same-day Bosnia fixture exists, retain the shared multi-sport day
    # selection used by the rest of the wallpaper.
    regular_nba=(rphase=="REGULAR SEASON")
    if regular_nba and not any(e["day_offset"]==0 for e in soccer_events):
        events=nba_events
    else:
        events=soccer_events+nba_events
        if events:
            preferred_day=next((offset for offset in (0,1,-1)
                                if any(e["day_offset"]==offset for e in events)),events[0]["day_offset"])
            events=[event for event in events if event["day_offset"]==preferred_day]
            events.sort(key=lambda event:(event["date"],0 if event["sport"]=="soccer" else 1))

    standings_sport=None
    if any(event["sport"]=="soccer" and event["day_offset"]==0 for event in events):
        standings_sport="soccer"
        competition_label=bcomp or "NATIONS LEAGUE • GROUP B4"
    elif regular_nba and nba_show_standings and any(event["sport"]=="nba" for event in events):
        standings_sport="nba"
        competition_label=""
    show_standings=standings_sport is not None
    if standings_sport=="nba" and not standings_data("nba"):
        show_standings=False

    im=background().convert("RGBA")
    shade=Image.new("RGBA",(W,H),(0,0,0,0))
    ImageDraw.Draw(shade).rectangle((0,0,W,H),fill=(0,0,0,26))
    im=Image.alpha_composite(im,shade)
    if events:
        im=draw_centered_panel(im,events,show_standings,competition_label)
    elif errors:
        print("No games in the three-day display window. "+" | ".join(errors))
    im.convert("RGB").save("wallpaper.jpg","JPEG",quality=96,optimize=True,progressive=True)

    version=datetime.now(TZ).strftime("%Y%m%d")
    digest=hashlib.sha256(open("wallpaper.jpg","rb").read()).hexdigest()[:12]
    feed=[{"location":"Shield Sports","title":"Bosnia & Raptors Daily Wallpaper",
           "url_img":f"https://stakemillion3-star.github.io/shield-wallpaper/wallpaper.jpg?v={version}-{digest}"}]
    with open("p.json","w",encoding="utf-8") as output:
        json.dump(feed,output,ensure_ascii=False,indent=2); output.write("\n")



if __name__=="__main__":
    main()
