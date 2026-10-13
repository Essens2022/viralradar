"""Find retailer product offers via Google Programmable Search API (optional credentials).
Only publish merchant prices from structured data on exact product pages.
"""
import datetime,json,os,re,urllib.parse,urllib.request,html
from html.parser import HTMLParser
from pathlib import Path

class JSONLD(HTMLParser):
 def __init__(self): super().__init__();self.active=False;self.scripts=[]
 def handle_starttag(self,tag,attrs):
  if tag=="script" and dict(attrs).get("type","").lower()=="application/ld+json":self.active=True
 def handle_data(self,data):
  if self.active:self.scripts.append(data)
 def handle_endtag(self,tag):
  if tag=="script":self.active=False

def fetch(url,timeout=12):
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 ViralRadarResearch/1.0"})
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.read(1200000).decode("utf-8","replace")

def nodes(obj):
 if isinstance(obj,list):
  for x in obj:yield from nodes(x)
 elif isinstance(obj,dict):
  yield obj
  if "@graph" in obj:yield from nodes(obj["@graph"])

def is_product(x):
 t=x.get("@type",[])
 return "Product" in ([t] if isinstance(t,str) else t)

def parse_offer(url,query):
 try:
  p=JSONLD();p.feed(fetch(url))
  for raw in p.scripts:
   try: doc=json.loads(raw)
   except (ValueError,TypeError):continue
   for obj in nodes(doc):
    if not is_product(obj):continue
    title=str(obj.get("name",""))
    # Conservative match: all substantial search tokens must occur in merchant product title.
    terms=[w.lower() for w in re.findall(r"\w+",query) if len(w)>=4]
    name=title.lower()
    if not terms or sum(w in name for w in terms)<max(1,int(len(terms)*0.8+0.999)):continue
    for offer in ([obj.get("offers")] if isinstance(obj.get("offers"),dict) else obj.get("offers",[]) or []):
     if not isinstance(offer,dict):continue
     price=offer.get("price")
     if price is None and isinstance(offer.get("priceSpecification"),dict):price=offer["priceSpecification"].get("price")
     try:price=float(str(price).replace(",","."))
     except (ValueError,TypeError):continue
     currency=offer.get("priceCurrency") or (offer.get("priceSpecification") or {}).get("priceCurrency")
     if price<=0 or currency!="EUR":continue
     image=obj.get("image","")
     if isinstance(image,list):image=image[0] if image else ""
     if isinstance(image,dict):image=image.get("url","")
     merchant=urllib.parse.urlparse(url).hostname or ""
     return {"seller":merchant,"name":title,"url":url,"price":price,"currency":"EUR","shipping":None,"delivery":None,"image":image if isinstance(image,str) and image.startswith("https://") else None,"availability":offer.get("availability"),"verifiedAt":datetime.datetime.now(datetime.timezone.utc).isoformat(),"match":"title_heuristic","source":"Merchant JSON-LD"}
 except Exception as exc:print("Merchant fetch",str(exc)[:100])
 return None

def main():
 key=os.getenv("GOOGLE_SEARCH_API_KEY");cx=os.getenv("GOOGLE_SEARCH_ENGINE_ID")
 now=datetime.datetime.now(datetime.timezone.utc).isoformat()
 if not key or not cx:
  print("Google Programmable Search not configured; skipping merchant discovery")
  return
 data=json.loads(Path("trends.json").read_text(encoding="utf-8")) if Path("trends.json").exists() else {"items":[]}
 offers={}
 for product in data.get("items",[])[:25]:
  name=product["name"];geo=product.get("geo","IT")
  params=urllib.parse.urlencode({"key":key,"cx":cx,"q":'"'+name+'" prezzo acquista',"num":10,"gl":geo.lower()})
  try:
   response=json.loads(fetch("https://www.googleapis.com/customsearch/v1?"+params))
   if "error" in response:print("Search API",response["error"].get("message"));break
  except Exception as exc:print("Search failed",str(exc)[:100]);continue
  found=[];seen=set()
  for result in response.get("items",[]):
   url=result.get("link","")
   host=urllib.parse.urlparse(url).hostname or ""
   if not url.startswith("https://") or host in seen:continue
   seen.add(host)
   item=parse_offer(url,name)
   if item:found.append(item)
  if found:offers[product["geo"]+"|"+name]=sorted(found,key=lambda x:x["price"])
 Path("offers.json").write_text(json.dumps({"updatedAt":now,"source":"Google Programmable Search + merchant structured data","offers":offers,"note":"Prices are extracted from publicly accessible product pages. Exact model, shipping, delivery, availability and retailer eligibility require verification."},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("Verified candidate offers for",len(offers),"products")
if __name__=="__main__":main()
