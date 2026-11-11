#!/usr/bin/env python3
"""Download and locally host correctly licensed animal photographs for Animal World."""
import concurrent.futures, html, json, os, re, sys, time, unicodedata
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
GUIDE=ROOT/"animal-guides.html"
OUT=ROOT/"assets"/"animals"
OUT.mkdir(parents=True,exist_ok=True)
UA="AnimalWorldPhotoImporter/1.0 (educational animal encyclopedia; contact: Dhanushkaprasad2001@gmail.com)"
LICENSE=re.compile(r"(creative commons|cc0|public domain|cc by|cc-by|gfdl|free art license)",re.I)

class ImgParser(HTMLParser):
    def __init__(self): super().__init__(); self.names=[]
    def handle_starttag(self,tag,attrs):
        if tag=="img":
            d=dict(attrs)
            if d.get("data-wiki"): self.names.append(html.unescape(d["data-wiki"]).strip())

def get_json(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    for attempt in range(7):
        try:
            with urlopen(req,timeout=35) as r: return json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            if e.code not in (429,500,502,503,504) or attempt==6: raise
            delay=min(90,8*(2**attempt))
            print("API rate limit/server response",e.code,"retrying in",delay,"seconds",file=sys.stderr)
            time.sleep(delay)
        except URLError:
            if attempt==6: raise
            time.sleep(min(60,5*(2**attempt)))

def clean(value):
    return re.sub(r"<[^>]+>"," ",html.unescape(value or "")).strip()

def norm(value):
    value=unicodedata.normalize('NFKD', value or '').encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',value).strip()

def slug(name):
    s=name.lower()
    s=re.sub(r"[^a-z0-9]+","-",s).strip("-")
    return s or "animal"

def get_image(name):
    # Only accept filenames that clearly identify the requested animal.
    wanted=norm(name)
    words=[w for w in wanted.split() if len(w)>2]
    blocked=re.compile(r"\b(aircraft|airplane|aviation|fighter|bomber|tank|armou?r|vehicle|automobile|truck|motorcycle|ship|boat|sculpture|statue|painting|drawing|illustration|cartoon|toy|logo|model|costume|mascot|museum exhibit)\b",re.I)
    params={"action":"query","generator":"search","gsrnamespace":6,"gsrlimit":50,"gsrsearch":"filetype:bitmap "+name,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":800,"format":"json"}
    try:
        data=get_json("https://commons.wikimedia.org/w/api.php?"+urlencode(params))
        pages=list(data.get("query",{}).get("pages",{}).values())
        ranked=[]
        for page in pages:
            title=page.get("title","").replace("File:","",1)
            norm_title=norm(title)
            info=(page.get("imageinfo") or [{}])[0]
            meta=info.get("extmetadata") or {}
            license_name=clean(meta.get("LicenseShortName",{}).get("value") or meta.get("License",{}).get("value"))
            if not LICENSE.search(license_name) or blocked.search(norm_title): continue
            exact=wanted in norm_title
            all_words=bool(words) and all(w in norm_title.split() for w in words)
            if not exact and (len(words)==1 or not all_words): continue
            ranked.append((100 if exact else 80,title,info,meta,license_name))
        if ranked:
            ranked.sort(key=lambda x:(x[0],len(x[1])),reverse=True)
            score,title,info,meta,license_name=ranked[0]
            return {"url":info.get("thumburl") or info.get("url"),"title":title,
                    "author":clean(meta.get("Artist",{}).get("value") or meta.get("Credit",{}).get("value") or "Photographer not identified"),
                    "license":license_name,"license_url":clean(meta.get("LicenseUrl",{}).get("value")),
                    "source":"Wikimedia Commons"}
    except Exception as e:
        print("Commons lookup failed:",name,str(e)[:180],file=sys.stderr)
    try:
        summary=get_json("https://en.wikipedia.org/api/rest_v1/page/summary/"+__import__("urllib.parse").parse.quote(name,safe=""))
        image=(summary.get("originalimage") or summary.get("thumbnail") or {}).get("source")
        if image and "upload.wikimedia.org" in image:
            filename=__import__("urllib.parse").parse.unquote(image.split("/")[-1])
            title=filename.replace("_"," ")
            nt=norm(title)
            if blocked.search(nt) or (wanted not in nt and not all(w in nt.split() for w in words)): return None
            for host in ("https://commons.wikimedia.org/w/api.php","https://en.wikipedia.org/w/api.php"):
                q={"action":"query","titles":"File:"+title,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":800,"format":"json"}
                data=get_json(host+"?"+urlencode(q))
                pages=list(data.get("query",{}).get("pages",{}).values())
                info=(pages[0].get("imageinfo") or [{}])[0] if pages else {}
                meta=info.get("extmetadata") or {}
                lic=clean(meta.get("LicenseShortName",{}).get("value") or meta.get("License",{}).get("value"))
                if info.get("thumburl") and LICENSE.search(lic):
                    return {"url":info["thumburl"],"title":title,
                            "author":clean(meta.get("Artist",{}).get("value") or meta.get("Credit",{}).get("value") or "Photographer not identified"),
                            "license":lic,"license_url":clean(meta.get("LicenseUrl",{}).get("value")),"source":"Wikipedia / Wikimedia"}
    except Exception as e: print("Wikipedia fallback failed:",name,str(e)[:150],file=sys.stderr)
    return None

def download_one(name):
    target=OUT/(slug(name)+".webp")
    try:
        photo=get_image(name)
        if not photo or not photo.get("url"):
            if target.exists(): target.unlink()
            return name,{"status":"missing"}
        req=Request(photo["url"],headers={"User-Agent":UA})
        with urlopen(req,timeout=45) as r: raw=r.read()
        from PIL import Image
        import io
        im=Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((900,900))
        im.save(target,"WEBP",quality=82,method=5)
        return name,{"file":"assets/animals/"+target.name,"status":"downloaded",
                     "source_title":photo["title"],"author":photo["author"],
                     "license":photo["license"],"license_url":photo["license_url"],
                     "source":photo["source"]}
    except Exception as e:
        print("Download failed:",name,str(e)[:180],file=sys.stderr)
        return name,{"status":"error","error":str(e)[:180]}

parser=ImgParser()
parser.feed(GUIDE.read_text(encoding="utf-8"))
names=list(dict.fromkeys(parser.names))
print("Unique species:",len(names))
manifest={}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    futures=[pool.submit(download_one,n) for n in names]
    for idx,future in enumerate(concurrent.futures.as_completed(futures),1):
        name,result=future.result(); manifest[name]=result
        if idx%20==0: print("Processed",idx,"/",len(names))
(OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
ok=sum(v["status"].startswith("downloaded") for v in manifest.values())
missing=[n for n,v in manifest.items() if v["status"] not in ("downloaded","downloaded-existing")]
print("Downloaded/local:",ok,"Missing:",len(missing))
if missing: print("Missing species:",", ".join(missing))
