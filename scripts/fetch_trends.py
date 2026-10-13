"""ViralRadar discovery: live Google Trends + Google News, optional YouTube API.
Only publish observed evidence. No invented product scores or social metrics.
"""
import datetime
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REGIONS={"Italia":"IT","Regatul Unit":"GB","Germania":"DE","Franța":"FR","Spania":"ES","Polonia":"PL","SUA":"US","Canada":"CA","România":"RO"}
PRODUCT_WORDS=re.compile(r"(?i)\b(projector|proiettore|proiector|air fryer|friggitrice|aspirapolvere|vacuum|robot|lampada|lamp|lampă|massager|massaggiatore|massage gun|smartwatch|auricolari|earbuds|headphones|cuffie|power bank|caricatore|charger|speaker|altoparlante|blender|frullatore|borraccia|bottle|sticlă|keyboard|tastiera|mouse|camera|fotocamera|webcam|drone|tablet|console|stampante|printer|monitor|diffusore|diffuser|umidificatore|humidifier|organizer|organizzatore|organisateur|portable fan|ventilatore|ventilator|led strip|striscia led|smart ring|anello smart|fitness tracker|thermos|termometro|thermometer|mini pc|dashcam|car vacuum|solar light|luce solare|lumină solară)\b")
EXCLUDE=re.compile(r"(?i)\b(election|elezioni|president|presidente|partita|football|calcio|earthquake|terremoto|meteo|weather|lottery|lotto|war|guerra|celebrity|actor|attrice|movie|film|serie tv|concert|festival|politic|politica)\b")
HEADERS={"User-Agent":"ViralRadar/1.1 (public RSS aggregation; contact via repository)"}

def fetch(url):
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=20) as resp:
        return resp.read()

def rss(url):
    return ET.fromstring(fetch(url)).findall(".//item")

def news_mentions(term,geo):
    q=urllib.parse.quote('"'+term+'" (product OR gadget OR buy OR review OR prezzo OR acquisto)')
    url="https://news.google.com/rss/search?q="+q+"&hl=en&gl="+geo+"&ceid="+geo+":en"
    try:
        entries=rss(url)[:5]
        return [{"title":(e.findtext("title") or "").strip(),"url":(e.findtext("link") or "").strip(),"published":e.findtext("pubDate") or ""} for e in entries]
    except Exception as exc:
        print("News",geo,term,type(exc).__name__)
        return []

def youtube_mentions(term):
    key=os.getenv("YOUTUBE_API_KEY","")
    if not key: return [],"not_configured"
    query=urllib.parse.urlencode({"part":"snippet","q":term+" product review","type":"video","maxResults":5,"order":"date","key":key})
    try:
        data=json.loads(fetch("https://www.googleapis.com/youtube/v3/search?"+query))
        return [{"title":x.get("snippet",{}).get("title",""),"url":"https://www.youtube.com/watch?v="+x["id"]["videoId"],"published":x.get("snippet",{}).get("publishedAt",""),"thumbnail":x.get("snippet",{}).get("thumbnails",{}).get("medium",{}).get("url","")} for x in data.get("items",[]) if x.get("id",{}).get("videoId")],"connected"
    except Exception as exc:
        print("YouTube",term,type(exc).__name__,str(exc)[:100])
        return [],"unavailable"

def main():
    now=datetime.datetime.now(datetime.timezone.utc)
    items=[]
    source_status={"Google Trends":"live","Google News":"live","YouTube":"optional_api_key","TikTok":"not_connected","Instagram":"not_connected","Facebook":"not_connected","Reddit":"not_connected"}
    for region,geo in REGIONS.items():
        try:
            entries=rss("https://trends.google.com/trending/rss?geo="+geo)
        except Exception as exc:
            print("Trends",region,type(exc).__name__,str(exc)[:160])
            continue
        for entry in entries:
            title=(entry.findtext("title") or "").strip()
            if not title or not PRODUCT_WORDS.search(title) or EXCLUDE.search(title):
                continue
            traffic=next((e.text for e in entry if e.tag.endswith("approx_traffic")),None)
            news=news_mentions(title,geo)
            videos,yt_status=youtube_mentions(title)
            if yt_status=="connected":source_status["YouTube"]="connected"
            item={"name":title,"region":region,"geo":geo,"traffic":traffic,
                  "published":entry.findtext("pubDate") or "",
                  "source":"Google Trends RSS","url":entry.findtext("link") or "",
                  "news":news,"videos":videos,
                  "evidence":[{"source":"Google Trends","type":"trending_search","url":entry.findtext("link") or ""}]+
                  [{"source":"Google News","type":"news_mention","url":n["url"]} for n in news]+
                  [{"source":"YouTube","type":"video_mention","url":v["url"]} for v in videos],
                  "productStatus":"candidate_unverified"}
            items.append(item)
    # Fallback: discover product-focused news when broad trending topics have no products.
    # These are evidence-backed discovery candidates, NOT verified viral sales.
    if not items:
        queries={
            "Italia":('IT','it','IT:it','nuovo gadget tecnologia prodotto recensione'),
            "Regatul Unit":('GB','en','GB:en','new gadget product launch review'),
            "Germania":('DE','de','DE:de','neues gadget produkt test'),
            "Franța":('FR','fr','FR:fr','nouveau gadget produit test'),
            "Spania":('ES','es','ES:es','nuevo gadget producto reseña'),
            "SUA":('US','en','US:en','trending gadget product review')
        }
        for region,(geo,lang,ceid,query) in queries.items():
            url="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":query+" when:7d","hl":lang,"gl":geo,"ceid":ceid})
            try:
                entries=rss(url)[:15]
            except Exception as exc:
                print("Fallback discovery",region,type(exc).__name__,str(exc)[:120])
                continue
            for entry in entries:
                raw=(entry.findtext("title") or "").strip()
                headline=raw.rsplit(" - ",1)[0].strip()
                if len(headline)<12 or EXCLUDE.search(headline):
                    continue
                link=(entry.findtext("link") or "").strip()
                if not link:continue
                items.append({"name":headline,"region":region,"geo":geo,
                    "traffic":None,"published":entry.findtext("pubDate") or "",
                    "source":"Google News RSS","url":link,
                    "news":[{"title":raw,"url":link,"published":entry.findtext("pubDate") or ""}],
                    "videos":[],"evidence":[{"source":"Google News","type":"product_news_candidate","url":link}],
                    "productStatus":"candidate_unverified"})
        # Remove repeated headlines without making up ranking or demand.
        unique=set();dedup=[]
        for item in items:
            key=(item["geo"],item["name"].lower())
            if key not in unique:unique.add(key);dedup.append(item)
        items=dedup
    # Keep older valid feed on network failures, rather than publishing invented products.
    if not items:
        print("No product candidates found; retaining previous feed")
        if not Path("trends.json").exists():
            Path("trends.json").write_text(json.dumps({"updatedAt":now.isoformat(),"items":[],"sourceStatus":source_status,"note":"No verified product candidates yet"},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return
    items.sort(key=lambda x:(len(x["videos"])>0,len(x["news"])>0),reverse=True)
    payload={"updatedAt":now.isoformat(),"items":items,"sourceStatus":source_status,
             "note":"Heuristic product candidates from public trending searches; news/video mentions are not sales or virality scores. Not all platforms are connected."}
    Path("trends.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Published",len(items),"observed product candidates")

if __name__=="__main__": main()
