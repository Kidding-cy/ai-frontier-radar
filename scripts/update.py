#!/usr/bin/env python3
"""AI Frontier Radar RSS collector. No credentials required for feeds.
OpenAI summaries are optional; OPENAI_API_KEY stays server-side in Actions secrets.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'site' / 'data.json'
USER_AGENT = 'AIFrontierRadar/1.0 (public RSS aggregation with attribution)'
NOW = datetime.now(timezone.utc)
MAX_AGE_DAYS = 21
FEEDS = [
    ('OpenAI', 'https://openai.com/news/rss.xml', 9, 'application'),
    ('Google DeepMind', 'https://deepmind.google/blog/rss.xml', 9, 'application'),
    ('Google Research', 'https://research.google/blog/rss/', 7, 'foundation'),
    ('Hugging Face', 'https://huggingface.co/blog/feed.xml', 7, 'application'),
    ('MIT Technology Review', 'https://www.technologyreview.com/topic/artificial-intelligence/feed/', 8, 'application'),
    ('TechCrunch AI', 'https://techcrunch.com/category/artificial-intelligence/feed/', 6, 'application'),
    ('NVIDIA', 'https://blogs.nvidia.com/feed/', 6, 'infrastructure'),
    ('AWS ML Blog', 'https://aws.amazon.com/blogs/machine-learning/feed/', 5, 'application'),
    ('arXiv AI', 'https://rss.arxiv.org/rss/cs.AI', 7, 'foundation'),
]

# Deliberately coarse classifier: application innovation has the highest priority.
INFRA = re.compile(r'\b(?:data\s*cent(?:er|re)|gpu|h100|b200|blackwell|cooling|semiconductor|chip(?:s|let)?|hyperscal(?:e|er)|electricity|power\s*grid|energy\s*consumption|infrastructure|datacent(?:er|re)|servers?)\b', re.I)
FOUNDATION = re.compile(r'\b(?:training|pre-?training|post-?training|distillation|scaling law|benchmark|inference|architecture|alignment|tokeniz|parameter|foundation model|language model|transformer|model evaluation|reasoning model|reinforcement learning|multimodal|diffusion model)\b', re.I)
APPLICATION = re.compile(r'\b(?:agent(?:s|ic)?|product|application|launch|release|deploy|enterprise|robot(?:s|ics)?|medical|clinical|drug|discover|science|health|education|assist|workflow|factory|manufactur|automation|coding|software|customer|video generation|creat|security|detection|enterprise|business)\b', re.I)
TOPICS = [
    ('机器人', re.compile(r'robot|embodied|humanoid', re.I)),
    ('科学与医疗', re.compile(r'biology|medical|drug|antibiotic|medicine|cancer|science|protein|health|genomic|clinical', re.I)),
    ('工业与制造', re.compile(r'industrial|manufactur|factory|logistics|plant|maintenance', re.I)),
    ('开发与软件', re.compile(r'coding|software|developer|programming|codebase|computer use|terminal', re.I)),
    ('智能体与工作流', re.compile(r'agents?|workflow|automat|orchestrat', re.I)),
    ('多模态与创作', re.compile(r'video|image|audio|voice|multimodal|3d|creative|generat', re.I)),
    ('云与算力', re.compile(r'datacenter|data center|gpu|chip|power|cloud|infra|cooling', re.I)),
    ('模型能力', re.compile(r'benchmark|model|training|reasoning|inference|eval', re.I)),
]
GENERIC = {
    'application': ('这条新闻涉及 AI 应用或产品动向。尚未配置逐篇中文解读，需打开原文了解实际结果和适用条件。',
                    '可重点观察它是否已产生真实用户价值、降低使用成本，或使以前难以自动化的工作流程成为可能。'),
    'foundation': ('这条研究涉及基础模型或算法。暂未生成逐篇中文解读，建议阅读原文的实验方法与结论。',
                   '关注新增能力是否可被重复验证，并是否可能推动机器人、科研或企业软件等应用创新。'),
    'infrastructure': ('这条动态涉及支持 AI 发展的硬件、云、能源或基础设施，尚未生成逐篇中文解读。',
                       '观察算力供给、能源需求、建设成本或企业部署条件会发生什么变化。'),
}


def clean(raw: str, limit: int = 520) -> str:
    s = html.unescape(re.sub(r'<[^>]*>', ' ', str(raw or '')))
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:limit]


def parse_dt(entry) -> datetime | None:
    for key in ('published_parsed', 'updated_parsed'):
        v = entry.get(key)
        if v:
            try:
                from calendar import timegm
                return datetime.fromtimestamp(timegm(v), tz=timezone.utc)
            except Exception:
                pass
    for key in ('published', 'updated'):
        if entry.get(key):
            try:
                dt = parsedate_to_datetime(entry[key]); return dt.replace(tzinfo=timezone.utc) if not dt.tzinfo else dt.astimezone(timezone.utc)
            except Exception:
                pass
    return None


def safe_url(url: str) -> str | None:
    try:
        u = urlparse(url.strip())
        if u.scheme not in ('https', 'http') or not u.netloc: return None
        query = urlencode([(k,v) for k,v in parse_qsl(u.query) if not k.lower().startswith('utm_')])
        return urlunparse((u.scheme,u.netloc,u.path,'',query,''))
    except Exception:
        return None


def classify(title: str, short: str, pref: str, source: str) -> tuple[str, str]:
    t = title + ' ' + short[:230]
    # Prefer concrete applications even when model/benchmark is mentioned.
    if INFRA.search(title) and not APPLICATION.search(title):cat = 'infrastructure'
    elif APPLICATION.search(title): cat = 'application'
    elif FOUNDATION.search(title):cat = 'foundation'
    else:cat = pref
    if source == 'arXiv AI' and cat == 'application' and not re.search(r'robot|agent|medical|clinical|real-world|application', title, re.I):cat='foundation'
    topic = next((topic for topic, pat in TOPICS if pat.search(title)), None) or ('模型能力' if cat=='foundation' else '云与算力' if cat=='infrastructure' else '应用探索')
    return cat, topic


def score_record(date: datetime, category: str, source_boost: int, title: str) -> tuple[int,int]:
    age = max(0, (NOW-date).total_seconds()/86400)
    focus = {'application':15,'foundation':6,'infrastructure':-9}.get(category, 0)
    timely = max(0, 16-round(age*1.1))
    high = 5 if re.search(r'launch|release|introduc|discover|deploy|agent|robot|breakthrough',title,re.I) else 0
    score = min(96, max(24, 51+focus+source_boost+timely+high))
    potential = min(99, max(25, 64+focus+source_boost + (6 if APPLICATION.search(title) else 0)))
    return score,potential


def fetch_feeds() -> tuple[list[dict], list[str]]:
    items, errors = [], []
    for name, url, boost, pref in FEEDS:
        try:
            r=requests.get(url,timeout=17,headers={'User-Agent': USER_AGENT,'Accept':'application/rss+xml,application/atom+xml,application/xml,text/xml,*/*'})
            r.raise_for_status()
            parsed=feedparser.parse(r.content)
            if not parsed.entries: raise ValueError('empty RSS feed')
            count=0
            for e in parsed.entries[:30]:
                title=clean(e.get('title',''),220)
                link=safe_url(e.get('link',''))
                dt=parse_dt(e)
                if not title or not link or dt is None: continue
                age=(NOW-dt).total_seconds()/86400
                if age < -2 or age > MAX_AGE_DAYS: continue
                excerpt=clean(e.get('summary') or e.get('description') or '',430)
                cat, topic=classify(title,excerpt,pref,name)
                score,potential=score_record(dt,cat,boost,title)
                short, apps=GENERIC[cat]
                items.append(dict(id=hashlib.sha1(link.encode('utf8')).hexdigest()[:16],category=cat,topic=topic,date=dt.isoformat(),source=name,
                    title=title,original_title=title,summary=short,application=apps,
                    watch='进一步查看原始资料、独立评测及真实部署，区分发布宣传与实证结果。',stage='新动态·待解读',score=score,potential=potential,
                    url=link,auto_summary=True,_excerpt=excerpt))
                count+=1
            print(f'OK {name}: {count}',file=sys.stderr)
        except Exception as exc:
            errors.append(f'{name}: {str(exc)[:130]}')
            print('WARN',errors[-1],file=sys.stderr)
    # Optional high-signal academic content via Hugging Face curated daily papers API.
    try:
        r=requests.get('https://huggingface.co/api/daily_papers?limit=30',timeout=20,headers={'User-Agent':USER_AGENT});r.raise_for_status()
        papers=r.json()
        for p in papers[:25]:
            paper=p.get('paper') or {}
            title=clean(paper.get('title',''),220);paper_id=paper.get('id')
            if not title or not paper_id:continue
            dt_str=paper.get('publishedAt') or p.get('publishedAt')
            try:dt=datetime.fromisoformat(dt_str.replace('Z','+00:00'))
            except (ValueError,TypeError,AttributeError):continue
            if (NOW-dt).total_seconds()/86400>MAX_AGE_DAYS:continue
            link=safe_url('https://huggingface.co/papers/'+str(paper_id))
            if not link:continue
            snippet=clean(paper.get('summary',''),430)
            cat,topic=classify(title,snippet,'foundation','Hugging Face Papers')
            # Academic results stay foundation unless real-world application is explicit in the title.
            if cat=='application' and not re.search(r'robot|agent|medical|deploy|application',title,re.I):cat='foundation'
            score,potential=score_record(dt,cat,7,title)
            short,apps=GENERIC[cat]
            items.append(dict(id=hashlib.sha1(link.encode()).hexdigest()[:16],category=cat,topic=topic,date=dt.isoformat(),source='Hugging Face Papers',title=title,
                original_title=title,summary=short,application=apps,watch='论文本身未必已经过同行评审；关注代码、数据、外部复现及现实限制。',
                stage='论文预印本',score=min(94,score+min(8,int(p.get('upvotes',0))//10)),potential=potential,url=link,auto_summary=True,_excerpt=snippet))
        print('OK Hugging Face API',file=sys.stderr)
    except Exception as exc:
        errors.append('Hugging Face Papers API: '+str(exc)[:130]);print('WARN',errors[-1],file=sys.stderr)
    return items,errors


def load_seed() -> list[dict]:
    try:
        return json.loads(OUT.read_text('utf8')).get('items',[])
    except (OSError,ValueError):return []


def curate(items: list[dict], seed: list[dict]) -> list[dict]:
    # Keep manually verified demo stories for at most 21 days to make the first deployment useful.
    recent_seed=[]
    for s in seed:
        if s.get('id','').startswith('2026-'):
            try:
                d=datetime.fromisoformat(s['date']).replace(tzinfo=timezone.utc)
                if (NOW-d).total_seconds()/86400<=MAX_AGE_DAYS:recent_seed.append(s)
            except Exception:pass
    seen_urls=set();seen_titles=set();combined=[]
    for rec in recent_seed+sorted(items,key=lambda e:e['score'],reverse=True):
        url=safe_url(rec.get('url',''))
        canonical=' '.join(re.findall(r'[a-z0-9]+',rec.get('original_title','').lower()))
        if not url or url in seen_urls or (canonical and canonical in seen_titles):continue
        seen_urls.add(url);seen_titles.add(canonical);combined.append(rec)
    # Soft category quotas. Anything not explicitly relevant to the reader's focus is secondary.
    buckets={cat:sorted((r for r in combined if r.get('category')==cat),key=lambda x:(x.get('score',0),x.get('date','')),reverse=True)
             for cat in ('application','foundation','infrastructure')}
    selected=buckets['application'][:29]+buckets['foundation'][:10]+buckets['infrastructure'][:5]
    selected.sort(key=lambda x:(x.get('score',0),x.get('date','')),reverse=True)
    return selected[:38]


def enrich_with_openai(items: list[dict]) -> None:
    key=os.getenv('OPENAI_API_KEY','').strip()
    if not key:return
    targets=[x for x in items if x.get('auto_summary')][:24]
    if not targets:return
    prompt_data=[{'id':x['id'],'category':x['category'],'source':x['source'],'title':x['original_title'],'excerpt':x.get('_excerpt','')[:360]} for x in targets]
    prompt=(
        '你是一名严谨的AI前沿技术编辑，服务于不熟悉技术但关心创新应用的中文读者。'
        '根据以下每条元数据（标题、来源、最多360字符的RSS摘录）写中文导读，只输出JSON对象: '
        '{"items":[{"id":"...","title":"中文标题","summary":"1-2句事实概括","application":"1句可能的应用场景",'
        '"watch":"1句可信度/成熟度/尚待验证的事项","topic":"4-10字中文主题","stage":"例如 已发布/研究探索/行业观察"}]}。'
        '不能编造量化效果、产品已发布状态、日期、公司承诺或研究结论。'
        '不要把展望写成事实。只能利用输入提到的信息；不确定就明确说需要看原文核实。'
        '如标题没有足够证据，用谨慎中性措辞。每条summary 35-80个汉字，application 22-60个汉字。'
        '\nJSON输入:\n'+json.dumps(prompt_data,ensure_ascii=False)
    )
    body={'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),
          'messages':[{'role':'system','content':'你仅输出可解析的JSON对象，不使用Markdown。'},{'role':'user','content':prompt}],
          'response_format':{'type':'json_object'},'temperature':0.2,'max_completion_tokens':7500}
    try:
        resp=requests.post('https://api.openai.com/v1/chat/completions',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},
                json=body,timeout=100);resp.raise_for_status()
        obj=json.loads(resp.json()['choices'][0]['message']['content'])
        edits={e.get('id'):e for e in obj.get('items',[]) if isinstance(e,dict)}
        count=0
        for x in targets:
            e=edits.get(x['id'])
            if not e:continue
            for k in ('title','summary','application','watch','topic','stage'):
                v=e.get(k)
                if isinstance(v,str) and v.strip():x[k]=clean(v,260)
            x['auto_summary']=True
            count+=1
        print(f'AI Chinese enrichment: {count}/{len(targets)}',file=sys.stderr)
    except Exception as exc:
        print('WARN AI enrichment failed (using honest English-title fallback):',str(exc)[:180],file=sys.stderr)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--offline',action='store_true',help='check output using embedded seed only')
    args=parser.parse_args()
    seed=load_seed()
    fetched,errors=([],[]) if args.offline else fetch_feeds()
    items=curate(fetched,seed) if fetched else seed
    if fetched:enrich_with_openai(items)
    for x in items:x.pop('_excerpt',None)
    result={
        'generated_at':NOW.isoformat() if fetched else '2026-10-23T12:00:00+08:00',
        'demo':not bool(fetched),
        'notes':('自动收集的资讯快照；部分来源抓取可能失败；中文自动解读需单独配置 API。' if fetched
                 else '示例快照；未获取到实时来源，仍显示已核验的2026年10月示例。'),
        'source_errors':errors,
        'items':items,
    }
    if not args.offline:
        OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(f"items={len(items)}, demo={result['demo']}, errors={len(errors)}, file={OUT}")
    assert all(x['category'] in ('application','foundation','infrastructure') and x.get('url','').startswith('https://') for x in items)

if __name__=='__main__':main()
