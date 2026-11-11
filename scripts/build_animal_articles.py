#!/usr/bin/env python3
"""Build static, attributed species articles for every Animal World guide entry."""
import html, json, re, time, unicodedata
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
GUIDE=ROOT/"animal-guides.html"
ART=ROOT/"articles"
ART.mkdir(exist_ok=True)
UA="AnimalWorldArticleBuilder/1.0 (educational animal library; contact Dhanushkaprasad2001@gmail.com)"

class GuideParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.items=[]; self.current=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=="article" and "animal-article" in a.get("class","").split():
            self.current={"name":a.get("data-title","").strip(),"group":a.get("data-group","Mammals"),"subgroup":a.get("data-subgroup","")}
        elif tag=="article" and self.current is not None:
            return
    def handle_endtag(self, tag):
        if tag=="article" and self.current:
            if self.current["name"]: self.items.append(self.current)
            self.current=None

def request_json(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    for attempt in range(6):
        try:
            with urlopen(req,timeout=30) as r: return json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            if e.code not in (429,500,502,503,504) or attempt==5: raise
            time.sleep(min(45,4*(2**attempt)))
        except URLError:
            if attempt==5: raise
            time.sleep(min(30,3*(2**attempt)))

def slug(value):
    value=unicodedata.normalize("NFKD",value).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+","-",value).strip("-")

def group_prefix(group):
    return {"Mammals":"mammals","Birds":"birds","Reptiles":"reptiles","Amphibians":"amphibians","Fish":"fish","Insects":"insects","Other Invertebrates":"other-invertebrates"}.get(group,"animals")

def wiki_data(name):
    try:
        summary=request_json("https://en.wikipedia.org/api/rest_v1/page/summary/"+quote(name,safe=""))
    except Exception:
        summary={}
    extract=""
    try:
        data=request_json("https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&exsectionformat=plain&redirects=1&titles="+quote(name)+"&format=json")
        pages=list(data.get("query",{}).get("pages",{}).values())
        if pages: extract=pages[0].get("extract","")
    except Exception:
        pass
    return {"title":summary.get("title",name),"description":summary.get("description",""),"extract":extract,"summary":summary.get("extract","")}

def split_extract(text):
    blocks=[]
    for line in re.split(r"\n\s*\n",text or ""):
        line=re.sub(r"\s+"," ",line).strip()
        if not line: continue
        if len(line)<90 and not re.search(r"[.!?]$",line):
            blocks.append(("heading",line))
        else:
            blocks.append(("p",line))
    return blocks

def build_page(item,manifest,existing):
    name=item["name"]; group=item["group"]; sub=item["subgroup"]
    prefix=group_prefix(group); key=slug(name)
    candidates=[ART/f"{prefix}-{key}-guide.html",ART/f"{prefix}-{key}-field-guide.html",ART/f"{key}-guide.html"]
    path=next((p for p in candidates if p.exists()),candidates[0])
    if path.exists(): return path.name,False
    data=wiki_data(name)
    title=data["title"] or name
    desc=(data["summary"] or data["description"] or f"Explore the classification, natural history and conservation of {name}.").split("\n")[0][:155]
    photo=manifest.get(name,{})
    photo_html=""
    if photo.get("file") and str(photo.get("status","")).startswith("downloaded"):
        credit=html.escape((photo.get("author") or "Photographer not identified")+" · "+(photo.get("license") or "Licence information"))
        photo_html=f'<figure class="species-photo"><img src="../{html.escape(photo["file"])}" alt="{html.escape(name)}" loading="lazy"><figcaption>{credit} · locally hosted on Animal World</figcaption></figure>'
    blocks=split_extract(data["extract"] or data["summary"])
    content=[]
    first=True
    for kind,value in blocks:
        if kind=="heading":
            content.append("<h2>"+html.escape(value)+"</h2>")
        else:
            content.append("<p>"+html.escape(value)+"</p>")
            first=False
    if not content:
        content=["<p>A species-specific reference could not be retrieved automatically for this entry. This page is reserved for a verified profile and will not display an unrelated animal photograph.</p>"]
    source_title=title
    page=f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)}: Species Guide | Animal World</title>
<meta name="description" content="{html.escape(desc,quote=True)}"><meta name="robots" content="index,follow">
<link rel="canonical" href="https://dhanushkaprasad2001-max.github.io/animal-world/articles/{path.name}">
<link rel="stylesheet" href="../styles.css">
<style>.species-article{{max-width:900px;margin:0 auto;padding:46px 24px 72px}}.species-article h1{{font:600 clamp(32px,5vw,48px)/1.15 'Playfair Display',serif;color:#173f35}}.species-article h2{{font:600 25px 'Playfair Display',serif;color:#173f35;margin:32px 0 10px}}.species-article p{{font-size:16px;line-height:1.85;color:#425249}}.species-photo img{{width:100%;max-height:520px;object-fit:cover;border-radius:12px}}.species-photo figcaption{{font-size:11px;color:#68746e;padding-top:8px}}.species-breadcrumb{{font-size:12px;color:#a47737;font-weight:700;letter-spacing:1px}}</style></head><body>
<header class="site-header"><a class="brand" href="../index.html"><span class="brand-mark">✦</span><span>Animal<span class="brand-light">World</span><small>Discover. Learn. Protect.</small></span></a><button class="menu-toggle" aria-label="Open menu" aria-expanded="false">☰</button><nav class="nav"><a href="../index.html">Home</a><a href="../species-directory.html">Species Directory</a><a class="active" href="../articles.html">Articles</a><a href="../about.html">About</a><a href="../contact.html">Contact</a></nav></header>
<main class="species-article"><p class="species-breadcrumb">{html.escape(group.upper())} · {html.escape(sub.upper())}</p><h1>{html.escape(name)}: Species Guide</h1><p>{html.escape(desc)}</p>{photo_html}<section class="species-reference"><h2>Species profile and natural history</h2>{''.join(content)}</section><section><h2>Responsible wildlife observation</h2><p>Observe wild animals from a respectful distance. Never feed, handle or disturb wildlife, nests or dens. Follow local wildlife rules and support habitat protection and responsible animal care.</p></section><p class="content-credit">Reference text adapted from <a href="https://en.wikipedia.org/wiki/{quote(source_title.replace(' ','_'))}" rel="noopener">Wikipedia: {html.escape(source_title)}</a>. Wikipedia text is available under the <a href="https://creativecommons.org/licenses/by-sa/4.0/" rel="noopener">Creative Commons Attribution-ShareAlike 4.0 licence</a>. This page is an educational summary and may not reflect the latest regional conservation assessment.</p><p><a href="../animal-guides.html">← Back to all animal guides</a></p></main>
<footer class="site-footer"><a href="../index.html">Animal World</a> · <a href="../privacy.html">Privacy</a> · <a href="../disclaimer.html">Disclaimer</a></footer><script>const t=document.querySelector('.menu-toggle');t.addEventListener('click',()=>{const n=document.querySelector('.nav');n.classList.toggle('open');t.setAttribute('aria-expanded',n.classList.contains('open'));});</script></body></html>'''
    path.write_text(page,encoding="utf-8")
    return path.name,True

def rebuild_index(paths):
    groups=[("mammals","Mammals"),("birds","Birds"),("reptiles","Reptiles"),("amphibians","Amphibians"),("fish","Fish"),("insects","Insects"),("other-invertebrates","Other Invertebrates"),("animals","Other Guides")]
    sections=[]
    for prefix,label in groups:
        files=sorted([p for p in paths if p.name.startswith(prefix+"-") or (prefix=="animals" and not re.match(r"^(mammals|birds|reptiles|amphibians|fish|insects|other-invertebrates)-",p.name))],key=lambda p:p.name)
        if not files: continue
        cards=[]
        for p in files:
            name=p.stem
            name=re.sub(r"^(mammals|birds|reptiles|amphibians|fish|insects|other-invertebrates)-","",name)
            name=re.sub(r"-(field-guide|guide)$","",name).replace("-"," ").title()
            cards.append(f'<a class="library-card" href="articles/{p.name}"><span>{label.upper()}</span><h3>{html.escape(name)}</h3><b>Read guide →</b></a>')
        sections.append(f'<section class="library-section"><div class="library-heading"><h2>{label}</h2><p>Species profiles and educational animal guides</p></div><div class="library-grid">{"".join(cards)}</div></section>')
    page='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Animal Articles and Species Guides | Animal World</title><meta name="description" content="Browse Animal World species profiles and educational guides organised into animal groups."><link rel="canonical" href="https://dhanushkaprasad2001-max.github.io/animal-world/articles.html"><link rel="stylesheet" href="styles.css"><style>.library-hero{background:#173f35;color:#fff;padding:58px 6vw}.library-hero h1{font:600 clamp(34px,5vw,54px)/1.12 'Playfair Display',serif;margin:12px 0}.library-hero p{max-width:720px;color:#e2eee8;line-height:1.8}.library-section{max-width:1160px;margin:auto;padding:42px 26px 10px}.library-heading{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:20px}.library-heading h2{font:600 30px 'Playfair Display',serif;color:#173f35;margin:6px 0}.library-heading p{color:#68746e;font-size:13px}.library-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}.library-card{display:block;background:#fff;border:1px solid #e4e9e3;border-radius:8px;padding:18px;min-height:130px}.library-card span{font-size:9px;letter-spacing:1.5px;color:#a47737;font-weight:700}.library-card h3{font:600 19px 'Playfair Display',serif;color:#173f35;margin:9px 0 14px}.library-card b{font-size:10px;color:#a47737}@media(max-width:650px){.library-heading{display:block}}</style></head><body><header class="site-header"><a class="brand" href="index.html"><span class="brand-mark">✦</span><span>Animal<span class="brand-light">World</span><small>Discover. Learn. Protect.</small></span></a><button class="menu-toggle" aria-label="Open menu" aria-expanded="false">☰</button><nav class="nav"><a href="index.html">Home</a><a href="species-directory.html">Species Directory</a><a class="active" href="articles.html">Articles</a><a href="about.html">About</a><a href="contact.html">Contact</a></nav></header><main><section class="library-hero"><span>THE ANIMAL WORLD LIBRARY</span><h1>Animal species articles</h1><p>Browse individual species profiles, natural-history references and educational guides by animal group.</p><a class="button button-light" href="animal-guides.html">Browse the searchable animal directory →</a></section>'''+''.join(sections)+'''</main><footer class="site-footer"><a href="index.html">Animal World</a> · <a href="about.html">About</a> · <a href="contact.html">Contact</a> · <a href="privacy.html">Privacy</a> · <a href="disclaimer.html">Disclaimer</a></footer><script>const t=document.querySelector('.menu-toggle');t.addEventListener('click',()=>{const n=document.querySelector('.nav');n.classList.toggle('open');t.setAttribute('aria-expanded',n.classList.contains('open'));});</script></body></html>'''
    (ROOT/"articles.html").write_text(page,encoding="utf-8")

def main():
    parser=GuideParser();parser.feed(GUIDE.read_text(encoding="utf-8"))
    unique={x["name"]:x for x in parser.items}
    manifest_path=ROOT/"assets"/"animals"/"manifest.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    existing=list(ART.glob("*.html"))
    created=0
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(build_page,item,manifest,existing) for item in unique.values()]
        for f in as_completed(futures):
            name,made=f.result()
            if made: created+=1
    all_pages=list(ART.glob("*.html"))
    # Add direct full-article links to each matching directory entry.
    guide=GUIDE.read_text(encoding="utf-8")
    for item in unique.values():
        prefix=group_prefix(item["group"]); key=slug(item["name"])
        candidates=[f"{prefix}-{key}-guide.html",f"{prefix}-{key}-field-guide.html",f"{key}-guide.html"]
        file=next((x for x in candidates if (ART/x).exists()),None)
        if not file: continue
        marker=f'<h2>{html.escape(item["name"])}</h2>'
        replacement=marker+f'<p class="full-guide-link"><a href="articles/{file}">Read the full {html.escape(item["name"])} species guide →</a></p>'
        # Add only when this entry does not already have a guide link.
        pos=guide.find(marker)
        if pos>=0 and 'class="full-guide-link"' not in guide[pos:pos+len(replacement)+150]:
            guide=guide[:pos]+guide[pos:].replace(marker,replacement,1)
    GUIDE.write_text(guide,encoding="utf-8")
    rebuild_index(all_pages)
    print("Directory entries:",len(unique),"new articles created:",created,"total article pages:",len(all_pages))

if __name__=="__main__": main()
