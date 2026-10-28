import os, shutil, uuid
from datetime import datetime, date, time
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, Float, Text, ForeignKey, Time, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session

engine=create_engine("sqlite:///./hrms.db",connect_args={"check_same_thread":False})
SessionLocal=sessionmaker(bind=engine)
Base=declarative_base()
pwd=CryptContext(schemes=["bcrypt"],deprecated="auto")
oauth2=OAuth2PasswordBearer(tokenUrl="/auth/login")
SECRET=os.getenv("JWT_SECRET","change-this-secret")
UPLOAD="uploads"; os.makedirs(UPLOAD,exist_ok=True)

class User(Base):
    __tablename__="users"; id=Column(Integer,primary_key=True); username=Column(String,unique=True); password_hash=Column(String); role=Column(String); status=Column(String,default="ACTIVE")
class Employee(Base):
    __tablename__="employees"; id=Column(Integer,primary_key=True); user_id=Column(Integer,ForeignKey("users.id")); name=Column(String); email=Column(String); department=Column(String); position=Column(String)
class Attendance(Base):
    __tablename__="attendance"; id=Column(Integer,primary_key=True); employee_id=Column(Integer); attendance_date=Column(Date); check_in=Column(DateTime); check_out=Column(DateTime); status=Column(String); overtime_hours=Column(Float,default=0)
class Leave(Base):
    __tablename__="leaves"; id=Column(Integer,primary_key=True); employee_id=Column(Integer); leave_type=Column(String); start_date=Column(Date); end_date=Column(Date); reason=Column(String); status=Column(String,default="PENDING")
class Payroll(Base):
    __tablename__="payroll"; id=Column(Integer,primary_key=True); employee_id=Column(Integer); month=Column(String); basic=Column(Float); allowances=Column(Float); deductions=Column(Float); bonus=Column(Float); net_salary=Column(Float)
class Notification(Base):
    __tablename__="notifications"; id=Column(Integer,primary_key=True); user_id=Column(Integer); message=Column(String); created_at=Column(DateTime,default=datetime.utcnow); is_read=Column(Boolean,default=False)
class LeavePolicy(Base):
    __tablename__="leave_policies"; id=Column(Integer,primary_key=True); leave_type=Column(String); total_days_allowed=Column(Integer)
class LeaveBalance(Base):
    __tablename__="leave_balance"; id=Column(Integer,primary_key=True); employee_id=Column(Integer); leave_type=Column(String); remaining_days=Column(Integer)
class Shift(Base):
    __tablename__="shifts"; id=Column(Integer,primary_key=True); name=Column(String); start_time=Column(Time); end_time=Column(Time)
class EmployeeShift(Base):
    __tablename__="employee_shifts"; id=Column(Integer,primary_key=True); employee_id=Column(Integer); shift_id=Column(Integer)
class Document(Base):
    __tablename__="documents"; id=Column(Integer,primary_key=True); employee_id=Column(Integer); file_name=Column(String); file_url=Column(String); uploaded_at=Column(DateTime,default=datetime.utcnow)
class Performance(Base):
    __tablename__="performance"; id=Column(Integer,primary_key=True); employee_id=Column(Integer); review_period=Column(String); rating=Column(Float); feedback=Column(Text); created_at=Column(DateTime,default=datetime.utcnow)

Base.metadata.create_all(engine)

def db():
    d=SessionLocal()
    try: yield d
    finally: d.close()

def current(token=Depends(oauth2),d=Depends(db)):
    try:
        p=jwt.decode(token,SECRET,algorithms=["HS256"]); u=d.get(User,int(p["sub"]))
        if not u or u.status!="ACTIVE": raise HTTPException(401,"Invalid user")
        return u
    except Exception: raise HTTPException(401,"Invalid token")

def roles(*allowed):
    def dep(u=Depends(current)):
        if u.role not in allowed: raise HTTPException(403,"Insufficient permissions")
        return u
    return dep

def emp(d,u):
    x=d.query(Employee).filter_by(user_id=u.id).first()
    if not x: raise HTTPException(404,"Employee profile not found")
    return x

class ShiftIn(BaseModel): name:str; start_time:str; end_time:str
class AssignIn(BaseModel): employee_id:int; shift_id:int
class PerfIn(BaseModel): employee_id:int; review_period:str; rating:float=Field(ge=0,le=5); feedback:str=""

app=FastAPI(title="WorkSphere HRMS Phase 3")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

@app.on_event("startup")
def seed():
    d=SessionLocal()
    if not d.query(User).first():
        for un,pw,role in [("admin","Admin@123","ADMIN"),("hr","Hr@123","HR"),("employee","Employee@123","EMPLOYEE")]:
            u=User(username=un,password_hash=pwd.hash(pw),role=role); d.add(u); d.flush()
            e=Employee(user_id=u.id,name=un.title(),email=un+"@worksphere.local",department="HR" if role!="EMPLOYEE" else "Engineering",position=role.title()); d.add(e); d.flush()
            for lt,days in [("Casual",12),("Sick",10),("Earned",15)]: d.add(LeaveBalance(employee_id=e.id,leave_type=lt,remaining_days=days))
        for n,s,e in [("Morning",time(9),time(17)),("Evening",time(14),time(22)),("Night",time(22),time(6))]: d.add(Shift(name=n,start_time=s,end_time=e))
        for lt,days in [("Casual",12),("Sick",10),("Earned",15)]: d.add(LeavePolicy(leave_type=lt,total_days_allowed=days))
        d.commit()
    d.close()

@app.post("/auth/login")
def login(form:OAuth2PasswordRequestForm=Depends(),d=Depends(db)):
    u=d.query(User).filter_by(username=form.username).first()
    if not u or not pwd.verify(form.password,u.password_hash): raise HTTPException(401,"Invalid username or password")
    token=jwt.encode({"sub":str(u.id),"role":u.role},SECRET,algorithm="HS256")
    return {"access_token":token,"token_type":"bearer","role":u.role}

@app.get("/me")
def me(u=Depends(current),d=Depends(db)):
    e=emp(d,u); return {"username":u.username,"role":u.role,"status":u.status,"employee":{"id":e.id,"name":e.name,"email":e.email,"department":e.department,"position":e.position}}

@app.get("/shifts")
def shifts(u=Depends(current),d=Depends(db)):
    return [{"id":x.id,"name":x.name,"start_time":x.start_time.strftime("%H:%M"),"end_time":x.end_time.strftime("%H:%M")} for x in d.query(Shift).all()]

@app.post("/shifts")
def add_shift(x:ShiftIn,u=Depends(roles("ADMIN","HR")),d=Depends(db)):
    s=Shift(name=x.name,start_time=time.fromisoformat(x.start_time),end_time=time.fromisoformat(x.end_time)); d.add(s); d.commit(); return {"message":"Shift created","id":s.id}

@app.post("/shifts/assign")
def assign(x:AssignIn,u=Depends(roles("ADMIN","HR")),d=Depends(db)):
    d.add(EmployeeShift(employee_id=x.employee_id,shift_id=x.shift_id)); d.commit(); return {"message":"Shift assigned"}

@app.get("/shifts/my")
def my_shift(u=Depends(current),d=Depends(db)):
    e=emp(d,u); es=d.query(EmployeeShift).filter_by(employee_id=e.id).order_by(EmployeeShift.id.desc()).first()
    if not es:return {"shift":None}
    s=d.get(Shift,es.shift_id); return {"shift":s.name,"start_time":s.start_time.strftime("%H:%M"),"end_time":s.end_time.strftime("%H:%M")}

@app.post("/attendance/check-in")
def checkin(u=Depends(current),d=Depends(db)):
    e=emp(d,u); today=date.today()
    if d.query(Attendance).filter_by(employee_id=e.id,attendance_date=today).first(): raise HTTPException(400,"Already checked in today")
    now=datetime.now(); status="On Time"
    es=d.query(EmployeeShift).filter_by(employee_id=e.id).order_by(EmployeeShift.id.desc()).first()
    if es and now.time()>d.get(Shift,es.shift_id).start_time: status="Late"
    d.add(Attendance(employee_id=e.id,attendance_date=today,check_in=now,status=status)); d.commit()
    if status=="Late": d.add(Notification(user_id=u.id,message="Late attendance detected")); d.commit()
    return {"message":"Check-in recorded","status":status}

@app.post("/attendance/check-out")
def checkout(u=Depends(current),d=Depends(db)):
    e=emp(d,u); a=d.query(Attendance).filter_by(employee_id=e.id,attendance_date=date.today()).first()
    if not a: raise HTTPException(400,"Check in first")
    a.check_out=datetime.now(); d.commit(); return {"message":"Check-out recorded"}

@app.get("/attendance")
def attendance(u=Depends(current),d=Depends(db)):
    q=d.query(Attendance)
    if u.role=="EMPLOYEE": q=q.filter_by(employee_id=emp(d,u).id)
    return [{"id":a.id,"employee_id":a.employee_id,"date":str(a.attendance_date),"status":a.status,"check_in":str(a.check_in) if a.check_in else None,"check_out":str(a.check_out) if a.check_out else None} for a in q.order_by(Attendance.attendance_date.desc()).all()]

@app.get("/leave-calendar")
def leave_calendar(u=Depends(current),d=Depends(db)):
    out=[]
    for x in d.query(Leave).filter_by(status="APPROVED").all():
        e=d.get(Employee,x.employee_id); out.append({"employee":e.name,"department":e.department,"start":str(x.start_date),"end":str(x.end_date),"type":x.leave_type})
    return out

@app.get("/leave-balances")
def balances(u=Depends(current),d=Depends(db)):
    e=emp(d,u); return [{"leave_type":x.leave_type,"remaining_days":x.remaining_days} for x in d.query(LeaveBalance).filter_by(employee_id=e.id).all()]

@app.get("/performance")
def performance(u=Depends(current),d=Depends(db)):
    q=d.query(Performance)
    if u.role=="EMPLOYEE": q=q.filter_by(employee_id=emp(d,u).id)
    return [{"id":p.id,"employee_id":p.employee_id,"review_period":p.review_period,"rating":p.rating,"feedback":p.feedback,"created_at":str(p.created_at)} for p in q.all()]

@app.post("/performance")
def add_performance(x:PerfIn,u=Depends(roles("ADMIN","HR")),d=Depends(db)):
    p=Performance(**x.model_dump()); d.add(p); d.commit(); return {"message":"Performance review added","id":p.id}

@app.post("/documents/upload")
def upload(file:UploadFile=File(...),u=Depends(current),d=Depends(db)):
    e=emp(d,u); ext=os.path.splitext(file.filename or "")[1].lower()
    if ext not in [".pdf",".png",".jpg",".jpeg",".doc",".docx"]: raise HTTPException(400,"Unsupported file type")
    name=uuid.uuid4().hex+ext
    with open(os.path.join(UPLOAD,name),"wb") as f: shutil.copyfileobj(file.file,f)
    x=Document(employee_id=e.id,file_name=file.filename,file_url=name); d.add(x); d.commit()
    return {"id":x.id,"file_name":x.file_name}

@app.get("/documents")
def documents(u=Depends(current),d=Depends(db)):
    q=d.query(Document)
    if u.role=="EMPLOYEE": q=q.filter_by(employee_id=emp(d,u).id)
    return [{"id":x.id,"file_name":x.file_name,"uploaded_at":str(x.uploaded_at)} for x in q.all()]

@app.get("/documents/{doc_id}/download")
def download(doc_id:int,u=Depends(current),d=Depends(db)):
    x=d.get(Document,doc_id)
    if not x: raise HTTPException(404,"Not found")
    if u.role=="EMPLOYEE" and x.employee_id!=emp(d,u).id: raise HTTPException(403,"Forbidden")
    return FileResponse(os.path.join(UPLOAD,x.file_url),filename=x.file_name)

@app.get("/analytics")
def analytics(u=Depends(roles("ADMIN","HR")),d=Depends(db)):
    total=d.query(Employee).count(); late=d.query(Attendance).filter_by(status="Late").count()
    approved=d.query(Leave).filter_by(status="APPROVED").count(); pending=d.query(Leave).filter_by(status="PENDING").count()
    ps=d.query(Performance).all(); avg=round(sum(x.rating for x in ps)/len(ps),2) if ps else 0
    return {"employees":total,"late_attendance":late,"approved_leaves":approved,"pending_leaves":pending,"average_performance":avg}

@app.get("/notifications")
def notifications(u=Depends(current),d=Depends(db)):
    return [{"id":x.id,"message":x.message,"created_at":str(x.created_at),"is_read":x.is_read} for x in d.query(Notification).filter_by(user_id=u.id).all()]

@app.get("/employees/search")
def search(q:str="",department:str="",role:str="",status:str="",u=Depends(roles("ADMIN","HR")),d=Depends(db)):
    out=[]
    for e in d.query(Employee).all():
        z=d.get(User,e.user_id)
        if q and q.lower() not in e.name.lower(): continue
        if department and department.lower()!=e.department.lower(): continue
        if role and role.upper()!=z.role: continue
        if status and status.upper()!=z.status: continue
        out.append({"id":e.id,"name":e.name,"email":e.email,"department":e.department,"role":z.role,"status":z.status})
    return out