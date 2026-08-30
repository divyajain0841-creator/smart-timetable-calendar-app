import re
from pathlib import Path
from collections import defaultdict
import cv2
import numpy as np
import pytesseract

DAYS=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
DEFAULT_MAIN=[("08:00","08:45"),("08:45","09:30"),("09:30","10:30"),("10:30","11:30"),("11:30","12:30"),("12:30","13:30"),("13:30","14:30")]
DEFAULT_SAT=[("08:00","09:00"),("09:00","10:00"),("10:00","11:00"),("11:00","12:00")]
TIME_RE=re.compile(r'(?i)(\d{1,2})\s*[:.]?\s*(\d{2})\s*[-–—]\s*(\d{1,2})\s*[:.]?\s*(\d{2})')
FIELDS=[("subject",["course name"]),("course_code",["course code"]),("course_type",["course type"]),("teacher",["teacher name","teacher"]),("classroom",["classroom","class room"])]

def clean(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def norm(s): return re.sub(r'[^a-z0-9]','',str(s).lower())
def structural(s): return norm(s) in {'break','mentoring','day','time','synchronous','session','coursename','coursecode','coursetype','teacher','teachername','classroom'}

def load_pages(path):
    if path.suffix.lower()=='.pdf':
        try:
            import fitz
            doc=fitz.open(path); pages=[]
            for page in doc:
                pix=page.get_pixmap(matrix=fitz.Matrix(2.5,2.5),alpha=False)
                arr=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,pix.n)
                pages.append(cv2.cvtColor(arr,cv2.COLOR_RGB2BGR))
            return pages
        except Exception as e: raise ValueError('Could not render PDF: '+str(e))
    img=cv2.imread(str(path))
    if img is None: raise ValueError('Could not read the uploaded image.')
    return [img]

def preprocess(img):
    scale=2.6
    big=cv2.resize(img,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    lab=cv2.cvtColor(big,cv2.COLOR_BGR2LAB); l,a,b=cv2.split(lab)
    l=cv2.createCLAHE(clipLimit=1.6,tileGridSize=(8,8)).apply(l)
    return cv2.cvtColor(cv2.merge((l,a,b)),cv2.COLOR_LAB2BGR),scale

def ocr(img,scale):
    # Run several segmentation modes and union their coordinate results. A
    # single PSM can miss faint day labels such as "Thursday" while another
    # catches them; keeping both is more reliable for structured tables.
    merged={}
    for psm in (6,11,12):
        d=pytesseract.image_to_data(cv2.cvtColor(img,cv2.COLOR_BGR2RGB),config=f'--oem 3 --psm {psm}',output_type=pytesseract.Output.DICT)
        for i,t in enumerate(d['text']):
            t=clean(t)
            try: conf=float(d['conf'][i])
            except: conf=-1
            if not t or conf<10: continue
            x,y,w,h=[float(d[k][i])/scale for k in ('left','top','width','height')]
            key=(round(x/3),round(y/3),norm(t))
            rec={'text':t,'conf':conf,'x':x,'y':y,'w':w,'h':h,'cx':x+w/2,'cy':y+h/2}
            if key not in merged or conf>merged[key]['conf']: merged[key]=rec
    return list(merged.values())

def grid_bounds(img):
    h,w=img.shape[:2]
    # The timetable has a metadata column followed by regular session columns.
    # Find the left metadata/session divider, then derive regular session widths.
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    bw=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,10)
    vk=cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(18,int(h*.018))))
    v=cv2.morphologyEx(bw,cv2.MORPH_OPEN,vk)
    score=(v>0).sum(axis=0)
    inds=np.where(score>max(5,score.max()*.14))[0]
    groups=[]
    for x in inds:
        if not groups or x-groups[-1][-1]>5: groups.append([x])
        else: groups[-1].append(x)
    xs=[int(np.mean(g)) for g in groups]
    xs=[x for x in xs if .12*w<x<.995*w]
    # Choose the first strong divider in the expected metadata range.
    left=min(xs,key=lambda x:abs(x-.19*w)) if xs else int(.19*w)
    # The outer right edge is reliably near the image edge for the supplied
    # academic layout. Derive equal session columns rather than trusting OCR
    # or spurious internal vertical lines.
    right=int(.975*w)
    if right-left<400:
        left=int(.19*w);right=int(.985*w)
    step=(right-left)/7
    return [left+i*step for i in range(8)]

def day_hits(words):
    def distance(a,b):
        if len(a)>12 or len(b)>12: return 99
        prev=list(range(len(b)+1))
        for i,ca in enumerate(a,1):
            cur=[i]
            for j,cb in enumerate(b,1): cur.append(min(cur[-1]+1,prev[j]+1,prev[j-1]+(ca!=cb)))
            prev=cur
        return prev[-1]
    out=defaultdict(list)
    for w in words:
        n=norm(w['text'])
        if not n: continue
        for d in DAYS:
            target=norm(d)
            if n==target or target in n or distance(n,target)<=1: out[d].append(w['cy'])
    return {d:float(np.median(v)) for d,v in out.items() if v}

def row_centers_for_day(words,top,bot,w):
    # Match the actual two-word labels where possible. This prevents a lone
    # OCR word "Course" from being mistaken for the Course Name row.
    left=[x for x in words if top-20<=x['cy']<=bot+20 and x['cx']<.205*w]
    out={}
    for key,firsts in [('subject',('course','name')),('course_code',('code',)),('course_type',('type',)),('teacher',('teacher',)),('classroom',('classroom',))]:
        if key=='subject':
            candidates=[]
            for a in left:
                if norm(a['text'])!='course': continue
                for b in left:
                    if norm(b['text'])=='name' and abs(a['cy']-b['cy'])<=9 and 35<=b['cx']-a['cx']<=100:
                        candidates.append((a['cy']+b['cy'])/2)
            if candidates: out[key]=float(np.median(candidates))
        else:
            ys=[x['cy'] for x in left if norm(x['text'])==norm(firsts[0])]
            if ys: out[key]=float(np.median(ys))
    # Infer missing row labels from the ordered known rows. The screenshot's
    # data rows are separated by ~24-32 px depending on resolution.
    order=['subject','course_code','course_type','teacher','classroom']
    known=sorted(out.items(),key=lambda kv:kv[1])
    if len(known)>=2:
        ds=[b[1]-a[1] for a,b in zip(known,known[1:]) if 12<b[1]-a[1]<45]
        step=float(np.median(ds)) if ds else 24.0
    else: step=24.0
    if known:
        # Anchor on the earliest known field and fill the ordered sequence.
        anchor_key,anchor_y=known[0]
        ai=order.index(anchor_key)
        for i,k in enumerate(order): out.setdefault(k,anchor_y+(i-ai)*step)
    else:
        base=(top+bot)/2-48
        for i,k in enumerate(order): out[k]=base+i*step
    return out
def clusters(words,gap=30):
    if not words:return []
    ws=sorted(words,key=lambda z:z['x']); out=[]; cur=[ws[0]]
    for w in ws[1:]:
        if w['x']-(cur[-1]['x']+cur[-1]['w'])>gap: out.append(cur);cur=[w]
        else: cur.append(w)
    out.append(cur);return out

def cell_text(cluster):
    vals=[]
    for w in sorted(cluster,key=lambda z:z['x']):
        t=clean(w['text']).replace('|','').strip('[]{}<>_=~`')
        if not t:continue
        if structural(t):continue
        if TIME_RE.search(t.replace(' ','')):continue
        vals.append(t)
    return clean(' '.join(vals))
def time_ranges(words):
    vals=[]
    for w in words:
        t=w['text'].replace(' ','').replace('—','-').replace('–','-')
        m=TIME_RE.search(t)
        if m:
            vals.append((w['cx'],(int(m.group(1)),int(m.group(2)),int(m.group(3)),int(m.group(4)))))
    return vals

def nearest_slot(cx,bounds):
    centers=[(bounds[i]+bounds[i+1])/2 for i in range(len(bounds)-1)]
    return int(np.argmin([abs(cx-c) for c in centers]))

def parse_page(img):
    proc,scale=preprocess(img); words=ocr(proc,scale)
    if len(words)<10: raise ValueError('OCR returned too little text. Use the original high-resolution timetable image.')
    h,w=img.shape[:2]; bounds=grid_bounds(img); days=day_hits(words)
    if len(days)<3:
        # Structural fallback for the six-row layout.
        for d,c in zip(DAYS[:6],[.16,.305,.45,.595,.74,.925]): days[d]=c*h
    ordered=sorted(days.items(),key=lambda kv:kv[1]); blocks={}
    for i,(d,cy) in enumerate(ordered):
        top=0 if i==0 else (ordered[i-1][1]+cy)/2
        bot=h if i==len(ordered)-1 else (cy+ordered[i+1][1])/2
        blocks[d]=(top,bot)
    main_times=list(DEFAULT_MAIN);sat_times=list(DEFAULT_SAT)
    # The source layout uses seven main sessions and four Saturday sessions.
    # Parse header times conservatively; if OCR mangles them, defaults remain.
    for w0 in words:
        t=w0['text'].replace(' ','').replace('—','-').replace('–','-')
        m=TIME_RE.search(t)
        if not m:continue
        p=(int(m.group(1)),int(m.group(2)),int(m.group(3)),int(m.group(4)))
        slot=nearest_slot(w0['cx'],bounds)
        if 0<=slot<7 and w0['cy']<.14*h:
            main_times[slot]=(f'{p[0]:02d}:{p[1]:02d}',f'{p[2]:02d}:{p[3]:02d}')
    events=[]
    for day,(top,bot) in blocks.items():
        rows=row_centers_for_day(words,top,bot,w)
        n=4 if day=='Saturday' else 7; times=sat_times if day=='Saturday' else main_times
        # Extract each row across the entire session region and form horizontal clusters.
        field_clusters={}
        for key,y in rows.items():
            ws=[x for x in words if bounds[0]-5<=x['cx']<=bounds[n]+5 and top-20<=x['cy']<=bot+20 and abs(x['cy']-y)<=16 and x['cx']>bounds[0]-8]
            field_clusters[key]=[(cell_text(c),min(x['x'] for x in c),max(x['x']+x['w'] for x in c)) for c in clusters(ws,32)]
        slotvals=[{k:'' for k in ['subject','course_code','course_type','teacher','classroom']} for _ in range(n)]
        for key,cs in field_clusters.items():
            for text,x0,x1 in cs:
                if not text or structural(text):continue
                touched=[]
                for si in range(n):
                    l,r=bounds[si],bounds[si+1]
                    overlap=max(0,min(x1,r)-max(x0,l))/(max(1,min(x1,r)-max(x0,l))+1e-6)
                    if overlap>0.20 or (x0>=l and x0<r) or (x1>l and x1<=r): touched.append(si)
                if not touched:
                    touched=[nearest_slot((x0+x1)/2,bounds)]
                for si in touched:
                    # Avoid putting a long merged-cell string into every slot if it merely
                    # touches a boundary; genuine spans have substantial overlap.
                    if key=='subject' or len(touched)==1: slotvals[si][key]=text
                    elif not slotvals[si][key]: slotvals[si][key]=text
        for si,v in enumerate(slotvals):
            subject=clean(v['subject'])
            if not subject or structural(subject) or subject.lower() in {'break','mentoring','cusbma'}:continue
            events.append({'day':day,'start':times[si][0],'end':times[si][1],'subject':subject,'course_code':clean(v['course_code']),'course_type':clean(v['course_type']),'teacher':clean(v['teacher']),'classroom':clean(v['classroom']),'source':'ocr-grid'})
    events=merge(events)
    return events,len(words),len(bounds)-1,list(days.keys())
def fallback_by_text(words,blocks,bounds,main_times,sat_times,w):
    out=[]
    for day,(top,bot) in blocks.items():
        times=sat_times if day=='Saturday' else main_times; n=4 if day=='Saturday' else 7
        # Course names are generally the first text row beneath the day's separator.
        for slot in range(n):
            l,r=bounds[slot],bounds[slot+1]
            candidates=[x for x in words if top+25<=x['cy']<=top+(bot-top)*.34 and l-20<=x['cx']<=r+20 and x['cx']>.18*w and x['conf']>20]
            text=clean(' '.join(x['text'] for x in sorted(candidates,key=lambda z:z['x'])))
            if text and not structural(text) and len(text)>2:
                out.append({'day':day,'start':times[slot][0],'end':times[slot][1],'subject':text,'course_code':'','course_type':'','teacher':'','classroom':'','source':'ocr-fallback'})
    return out

def merge(items):
    items=sorted(items,key=lambda x:(DAYS.index(x['day']) if x['day'] in DAYS else 99,x['start']))
    out=[]
    for x in items:
        if out and out[-1]['day']==x['day'] and out[-1]['subject'].lower()==x['subject'].lower() and out[-1]['course_code'].lower()==x['course_code'].lower() and out[-1]['end']==x['start']:
            out[-1]['end']=x['end']
            for k in ('course_type','teacher','classroom'):
                if not out[-1].get(k) and x.get(k): out[-1][k]=x[k]
        else: out.append(dict(x))
    return dedupe(out)

def dedupe(items):
    seen=set();out=[]
    for x in items:
        k=(x['day'],x['start'],x['end'],norm(x['subject']),norm(x.get('course_code','')))
        if k not in seen:seen.add(k);out.append(x)
    return out

def parse_timetable(path):
    pages=load_pages(path); all_events=[]; meta=[]
    for img in pages:
        ev,ow,sc,days=parse_page(img);all_events.extend(ev);meta.append((ow,sc,days))
    all_events=dedupe(all_events)
    return {'success':bool(all_events),'confidence':round(min(.98,max(.25,.35+min(.55,len(all_events)/20))),2),'grid':{'session_count':max((x[1] for x in meta),default=0),'days_detected':sorted(set(sum((x[2] for x in meta),[])),key=lambda d:DAYS.index(d))},'classes':all_events,'ocr_blocks':sum(x[0] for x in meta),'warnings':[] if all_events else ['No classes were confidently mapped. Review the image or add missing classes manually.']}

def parse_academic_calendar(path: Path):
    pages=load_pages(path); text=[]
    for img in pages:
        p,scale=preprocess(img)
        text.append(pytesseract.image_to_string(cv2.cvtColor(p,cv2.COLOR_BGR2RGB),config='--oem 3 --psm 6'))
    joined='\n'.join(text); found=[]; seen=set()
    months={m.lower():i for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
    for m in re.finditer(r'\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b',joined):
        try:
            d,mo,y=map(int,m.groups()); key=f'{y:04d}-{mo:02d}-{d:02d}'
            if key not in seen: found.append({'date':key,'name':'Academic calendar holiday'});seen.add(key)
        except: pass
    for m in re.finditer(r'\b(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(20\d{2})\b',joined,re.I):
        try:
            d=int(m.group(1)); mon=next(v for k,v in months.items() if k.startswith(m.group(2).lower())); y=int(m.group(3));key=f'{y:04d}-{mon:02d}-{d:02d}'
            if key not in seen: found.append({'date':key,'name':'Academic calendar holiday'});seen.add(key)
        except: pass
    return {'holidays':found,'text_preview':clean(joined)[:3000]}
