import os, uuid, requests
from datetime import datetime
from urllib.parse import urlencode
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

google_router=APIRouter(); TOKENS={}
CID=os.getenv('GOOGLE_CLIENT_ID',''); SECRET=os.getenv('GOOGLE_CLIENT_SECRET',''); REDIRECT=os.getenv('GOOGLE_REDIRECT_URI','http://localhost:8000/api/google/callback')

def google_status(): return {'configured':bool(CID and SECRET),'redirect_uri':REDIRECT}
@google_router.get('/status')
def status(): return google_status()
@google_router.get('/login')
def login():
    if not CID or not SECRET: raise HTTPException(503,'Google Calendar is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to the deployment environment.')
    state=uuid.uuid4().hex; TOKENS[state]=None
    params={'client_id':CID,'redirect_uri':REDIRECT,'response_type':'code','scope':'https://www.googleapis.com/auth/calendar','access_type':'offline','prompt':'consent','state':state}
    return RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(params))
@google_router.get('/callback')
def callback(code:str,state:str):
    if state not in TOKENS: raise HTTPException(400,'Invalid Google OAuth state.')
    r=requests.post('https://oauth2.googleapis.com/token',data={'code':code,'client_id':CID,'client_secret':SECRET,'redirect_uri':REDIRECT,'grant_type':'authorization_code'},timeout=20)
    if not r.ok: raise HTTPException(400,'Google token exchange failed: '+r.text[:500])
    TOKENS[state]=r.json(); return RedirectResponse('/#calendar?google=connected')
@google_router.post('/events')
def events(payload:dict):
    # Demo-friendly bridge: token can be supplied by an OAuth callback state.
    token=payload.get('access_token')
    if not token:
        token=next((v for v in TOKENS.values() if v and v.get('access_token')),None)
    if not token: raise HTTPException(401,'Connect Google Calendar first. For a multi-user production deployment, persist OAuth tokens per authenticated user.')
    access=token.get('access_token',token) if isinstance(token,dict) else token
    created=[]
    for e in payload.get('events',[]):
        body={'summary':e['subject'],'description':e.get('description',''),'location':e.get('classroom',''),'start':{'dateTime':e['start'],'timeZone':e.get('timeZone','Asia/Kolkata')},'end':{'dateTime':e['end'],'timeZone':e.get('timeZone','Asia/Kolkata')}}
        r=requests.post('https://www.googleapis.com/calendar/v3/calendars/primary/events',headers={'Authorization':'Bearer '+access},json=body,timeout=20)
        if not r.ok: raise HTTPException(r.status_code,r.text[:1000])
        created.append(r.json().get('id'))
    return {'created':created}

def esc(s): return str(s or '').replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')
def build_ics(payload):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//TimetableFlow//EN','CALSCALE:GREGORIAN','METHOD:PUBLISH']
    for e in payload.get('events',[]):
        def z(s): return s.replace('-','').replace(':','')
        lines+=['BEGIN:VEVENT',f'UID:{e.get("uid",uuid.uuid4().hex+"@timetableflow")}',f'DTSTAMP:{datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")}',f'DTSTART;TZID={e.get("timeZone","Asia/Kolkata")}:{z(e["start"])}',f'DTEND;TZID={e.get("timeZone","Asia/Kolkata")}:{z(e["end"])}',f'SUMMARY:{esc(e.get("subject","Class"))}',f'DESCRIPTION:{esc(e.get("description",""))}',f'LOCATION:{esc(e.get("classroom",""))}','END:VEVENT']
    lines.append('END:VCALENDAR');return '\r\n'.join(lines)+'\r\n'
