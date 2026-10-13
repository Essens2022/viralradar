import json, re, urllib.request, xml.etree.ElementTree as ET, datetime, time
from pathlib import Path
REGIONS={"Italia":"IT","Regatul Unit":"GB","Germania":"DE","Franța":"FR","Spania":"ES","Polonia":"PL","SUA":"US","Canada":"CA","România":"RO"}
OUT=[]
for region,geo in REGIONS.items():
 try:
  req=urllib.request.Request("https://trends.google.com/trending/rss?geo="+geo,headers={"User-Agent":"Mozilla/5.0 (compatible; ViralRadar/1.0)"})
  raw=urllib.request.urlopen(req,timeout=18).read()
  root=ET.fromstring(raw)
  for item in root.findall(".//item"):
   title=(item.findtext("title") or "").strip()
   link=(item.findtext("link") or "").strip()
   pub=item.findtext("pubDate") or ""
   traffic=next((e.text for e in item if e.tag.endswith("approx_traffic")),None)
   news=[{"title":(e.findtext("title") or ""),"url":(e.findtext("url") or "")} for e in item if e.tag.endswith("news_item")]
   if title:
    OUT.append({"name":title,"region":region,"geo":geo,"traffic":traffic,"published":pub,"source":"Google Trends RSS","url":link,"news":news[:2]})
 except Exception as exc:
  print(region,type(exc).__name__,str(exc)[:180])
payload={"updatedAt":datetime.datetime.now(datetime.timezone.utc).isoformat(),"source":"Google Trends RSS","note":"Search topics, not validated products or sales figures","items":OUT}
if not OUT: raise SystemExit("No live data returned; retaining prior file")
Path("trends.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("Saved",len(OUT),"live search topics")
