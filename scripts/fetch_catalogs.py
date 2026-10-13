"""Public retailer adapters for ViralRadar. No fabricated products, prices, or traffic.
Configure VIRALRADAR_STORES as comma-separated HTTPS merchant homepages.
Only the merchant's own public product endpoints are requested.
"""
import datetime,json,os,re,urllib.parse,urllib.request
from pathlib import Path

HEADERS={"User-Agent":"ViralRadar/1.2 (+https://github.com/Essens2022/viralradar)","Accept":"application/json"}
def get_json(url):
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=12) as response:
        if response.status!=200:return None
        return json.loads(response.read(1500000))
def tokens(value):
    return set(re.findall(r"[a-z0-9]+",value.casefold()))-{"the","and","for","with","new","pro","ultra","complete","series","model"}
def matching(query,title):
    q=tokens(query);t=tokens(title)
    return bool(q) and len(q&t)>=max(1,int(len(q)*0.75+0.999))
def valid_host(host):
    p=urllib.parse.urlparse(host.strip())
    if p.scheme!="https" or not p.hostname or p.username or p.password:return None
    if p.hostname in ("localhost",) or p.hostname.endswith((".local",".internal")):return None
    return "https://"+p.hostname
def shopify(store,term):
    # Shopify's public products.json is storefront-dependent; not guaranteed available.
    data=get_json(store+"/products.json?limit=250")
    if not isinstance(data,dict):return []
    found=[]
    for product in data.get("products",[]):
        name=product.get("title","")
        if not matching(term,name):continue
        handle=product.get("handle","")
        for v in product.get("variants",[])[:8]:
            try:price=float(v.get("price",0))
            except (TypeError,ValueError):continue
            if price<=0 or not handle:continue
            images=product.get("images") or []
            pic=images[0].get("src") if images else None
            found.append({"seller":urllib.parse.urlparse(store).hostname,"name":name,"url":store+"/products/"+urllib.parse.quote(handle),"price":price,"currency":None,"shipping":None,"image":pic if pic and pic.startswith("https://") else None,"source":"Shopify public catalog","match":"title_heuristic","verifiedAt":datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return found
def woocommerce(store,term):
    url=store+"/wp-json/wc/store/v1/products?"+urllib.parse.urlencode({"search":term,"per_page":30})
    data=get_json(url)
    if not isinstance(data,list):return []
    found=[]
    for p in data:
        name=p.get("name","")
        if not matching(term,name):continue
        prices=p.get("prices") or {}
        try:price=int(prices["price"])/(10**int(prices.get("currency_minor_unit",2)))
        except (KeyError,TypeError,ValueError,OverflowError):continue
        currency=prices.get("currency_code")
        images=p.get("images") or []
        pic=images[0].get("src") if images else None
        url=p.get("permalink","")
        if price<=0 or not url.startswith("https://"):continue
        found.append({"seller":urllib.parse.urlparse(store).hostname,"name":name,"url":url,"price":price,"currency":currency,"shipping":None,"image":pic if pic and pic.startswith("https://") else None,"source":"WooCommerce Store API","match":"title_heuristic","verifiedAt":datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return found
def main():
    data=json.loads(Path("trends.json").read_text(encoding="utf-8"))
    stores=list(dict.fromkeys(filter(None,(valid_host(x) for x in os.getenv("VIRALRADAR_STORES","").split(",")))))[:20]
    offers={}
    status={"Shopify public catalog":"not_configured" if not stores else "no_matches","WooCommerce Store API":"not_configured" if not stores else "no_matches"}
    for item in data.get("items",[])[:40]:
        term=item.get("name","")
        if not term:continue
        found=[]
        for store in stores:
            for label,adapter in (("WooCommerce Store API",woocommerce),("Shopify public catalog",shopify)):
                try:
                    results=adapter(store,term)
                    if results:status[label]="matches_found"
                    found.extend(results)
                except Exception as exc:
                    print(label,store,type(exc).__name__,str(exc)[:100])
        # Do not silently label a non-EUR price as EUR. UI currently supports EUR only.
        found=[x for x in found if x.get("currency")=="EUR"]
        if found:offers[item.get("geo","")+"|"+term]=sorted(found,key=lambda x:x["price"])
    payload={"updatedAt":datetime.datetime.now(datetime.timezone.utc).isoformat(),"source":"Public retailer product catalogs","offers":offers,"sourceStatus":status,"note":"Merchant prices only, EUR. Store domains must be configured; matches are title heuristics, not confirmed GTIN matches. Shipping not included."}
    Path("catalog_offers.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Catalog adapter matches",len(offers),"configured stores",len(stores))
if __name__=="__main__":main()
