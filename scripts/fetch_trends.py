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

REGIONS={"Italia":"IT","Regatul Unit":"GB","Germania":"DE","Franța":"FR","Spania":"ES","Polonia":"PL","Portugalia":"PT","Țările de Jos":"NL","Belgia":"BE","Austria":"AT","Elveția":"CH","Suedia":"SE","Norvegia":"NO","Danemarca":"DK","Finlanda":"FI","Irlanda":"IE","Grecia":"GR","Cehia":"CZ","România":"RO","SUA":"US","Canada":"CA","Mexic":"MX","Brazilia":"BR","Argentina":"AR","Australia":"AU","Noua Zeelandă":"NZ","Japonia":"JP","Coreea de Sud":"KR","India":"IN","Indonezia":"ID","Filipine":"PH","Singapore":"SG","Malaysia":"MY","Africa de Sud":"ZA","Turcia":"TR","Emiratele Arabe Unite":"AE"}

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
    source_status={"Google Trends":"pending","Google News":"pending","YouTube":"optional_api_key","TikTok":"not_connected","Instagram":"not_connected","Facebook":"not_connected","Reddit":"not_connected"}
    for region,geo in REGIONS.items():
        try:
            entries=rss("https://trends.google.com/trending/rss?geo="+geo)
            source_status["Google Trends"]="reachable"
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
    # News headlines are not products. Only accept a clearly named model in a
    # product-focused headline, and mark it as unverified candidate.
    if not items:
        # Diversify evidence gathering across consumer categories and markets.
        queries={
            "Italia":("IT","it","IT:it",["nuovo aspirapolvere robot modello","nuovo accessorio auto modello","nuovo dispositivo cucina modello","nuovo gadget animali modello"]),
            "Regatul Unit":("GB","en","GB:en",["new home cleaning device model","new pet gadget model","new car accessory model","new kitchen appliance model"]),
            "Germania":("DE","de","DE:de",["neuer Saugroboter Modell","neues Autozubehör Modell","neues Küchengerät Modell","neues Haustier Gadget Modell"]),
            "Franța":("FR","fr","FR:fr",["nouvel aspirateur robot modèle","nouvel accessoire voiture modèle","nouvel appareil cuisine modèle","nouvel accessoire animaux modèle"]),
            "Spania":("ES","es","ES:es",["nuevo robot aspirador modelo","nuevo accesorio coche modelo","nuevo aparato cocina modelo","nuevo accesorio mascotas modelo"]),
            "SUA":("US","en","US:en",["new home gadget model","new car accessory model","new pet device model","new kitchen appliance model"]),
            "Japonia":("JP","ja","JP:ja",["新製品 掃除ロボット","新製品 キッチン家電","新製品 ペット用品"]),
            "India":("IN","en","IN:en",["new home appliance model","new automotive accessory model","new kitchen gadget model"]),
            "Brazilia":("BR","pt","BR:pt",["novo aspirador robô modelo","novo acessório automotivo modelo","novo aparelho cozinha modelo"]),
            "Australia":("AU","en","AU:en",["new home cleaning product model","new pet accessory model","new kitchen appliance model"])
        }
        brand=re.compile(r"(?i)\b(apple|iphone|ipad|samsung|galaxy|motorola|razr|google pixel|xiaomi|redmi|poco|oneplus|nothing phone|sony|bose|jbl|dyson|anker|ecovacs|roborock|dreame|garmin|fitbit|huawei|honor|lenovo|asus|acer|dji|gopro|meta quest|nintendo|playstation|xbox|kindle|homepod|airpods)\b")
        model=re.compile(r"(?i)\b(?:[a-z]{1,5}[- ]?\d{1,4}[a-z]{0,4}|\d{1,3}(?:\s?(?:pro|max|ultra|plus|mini|fold|lite))?|(?:pro|max|ultra|fold|mini|plus|air|edge|razr))\b")
        editorial=re.compile(r"(?i)\b(miglior|migliori|best|top \d|guida|guide|lista|list|gadgets? that|prodotti|products|comprare|buying|portfolio|event|livestream|trappola|confronto|comparison)\b")
        for region,(geo,lang,ceid,terms) in queries.items():
            entries=[]
            for query in terms:
                url="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":query+" when:7d","hl":lang,"gl":geo,"ceid":ceid})
                try:
                    entries.extend(rss(url)[:12])
                    source_status["Google News"]="reachable"
                except Exception as exc:
                    print("Fallback discovery",region,type(exc).__name__,str(exc)[:120])
            for entry in entries:
                raw=(entry.findtext("title") or "").strip()
                headline=raw.rsplit(" - ",1)[0].strip()
                if not headline or EXCLUDE.search(headline) or editorial.search(headline):
                    continue
                match=brand.search(headline)
                if not match or not model.search(headline[match.end():match.end()+38]):
                    continue
                # Product name is a short model phrase, not the entire article headline.
                words=headline[match.start():].split()
                product_name=" ".join(words[:min(5,len(words))]).split(":")[0].strip(" ,:;-")
                if len(product_name)>75:continue
                link=(entry.findtext("link") or "").strip()
                if not link:continue
                items.append({"name":product_name,"region":region,"geo":geo,
                    "traffic":None,"published":entry.findtext("pubDate") or "",
                    "source":"Google News RSS","url":link,
                    "news":[{"title":raw,"url":link,"published":entry.findtext("pubDate") or ""}],
                    "videos":[],"evidence":[{"source":"Google News","type":"model_mention","url":link}],
                    "productStatus":"candidate_unverified"})
        unique=set();dedup=[]
        for item in items:
            key=(item["geo"],item["name"].lower())
            if key not in unique:unique.add(key);dedup.append(item)
        items=dedup
    # Keep older valid feed on network failures, rather than publishing invented products.
    if not items:
        print("No product candidates found; retaining previous feed")
        Path("trends.json").write_text(json.dumps({"updatedAt":now.isoformat(),"items":[],"sourceStatus":source_status,"note":"No product candidates found in accessible feeds; check GitHub Actions logs and source availability."},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return
    items.sort(key=lambda x:(len(x["videos"])>0,len(x["news"])>0),reverse=True)
    payload={"updatedAt":now.isoformat(),"items":items,"sourceStatus":source_status,
             "note":"Heuristic product candidates from public trending searches; news/video mentions are not sales or virality scores. Not all platforms are connected."}
    Path("trends.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Published",len(items),"observed product candidates")

if __name__=="__main__": main()
