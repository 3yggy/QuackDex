import os
import base64
import re
import struct
from io import BytesIO
from flask import Flask, render_template, request, send_file, abort, redirect
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, desc, func
from datetime import datetime
from Crypto.Cipher import AES
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests 
import json
import random
import urllib

f = Flask(__name__)

key = os.environ.get("ZIGGY_KEY")
f.config["SECRET_KEY"] = key if key else "testpass"

limiter = Limiter(
    f,
    key_func=get_remote_address
)

googleSecret = os.environ.get("GOOGLE_SECRET")

bans = os.environ.get("BANS_LIST")
bans = bans.split('|') if bans else []
@f.before_request
def limit_remote_addr():
    if request.headers.getlist("X-Forwarded-For"):
        ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        ip = request.remote_addr
    if str(ip) in bans:
        abort(403)
    else:
        print('connected: '+ip)

hatSection = "/hats"

@f.route("/")
def Home():
    return redirect('/hats')

@limiter.limit('500/minute')
@f.route('/api/hatnamed/<string:name>')
def HatNamed(name):
    return HatNamedNum(name,0)

@limiter.limit('500/minute')
@f.route('/api/hatnamed/<string:name>/<int:num>')
def HatNamedNum(name,num):
    print(name)
    query = HatPost.query.filter(HatPost.title.ilike('%'+name+'%'))
    if query and num >= 0 and query.count()>num:
        hat = query[num]
        response = f.make_response(ImgFromHat(hat.hat))
        response.headers.set('Content-Type', 'image/png')
        response.headers.set('Content-Disposition', 'attachment', filename=(hat.title)+".png")
        return response
    return 'nothing :('

@limiter.limit('15 per hour')
@f.route("/gethatfile/<int:id>")
def GetFile(id):  
    hat=HatById(id)
    if hat:
        if(hat.downloads == None):
            hat.downloads = 0
        hat.downloads += 1
        db.session.commit()
     
        return send_file(BytesIO(hat.hat),attachment_filename = format(hat.title)+".hat",as_attachment=True)
    else:
        return "404-Hat Missing"   

@limiter.limit('240 per hour')
@f.route("/edithat/<int:id>",methods=['GET','POST'])
def EditHat(id):   
    if request.method == 'POST':
        pas = request.form['passcode']        

        hat = HatById(id)
        if not hat:
            return "404-Hat Missing"    
        #else    
        goodPass = hat.author.passcode
        if pas == goodPass or pas == f.config["SECRET_KEY"]:
            if pas == "duck":
               return "This Hat is in the Hand of the Public and Can Not be Changed! To add Hats for the Public, Use The login: {User Name:duck, Passcode:duck}"
            if request.form['action']=='Remove':
                db.session.delete(hat)
                db.session.commit()
                return "Hat Removed"
            else:
                newname = request.form['newname']
                if newname:
                    hat.title = newname
                    db.session.commit()
                    return "Hat Title Changed to: "+newname
                else:
                    return "Please Chose A Valid Name"
        else:
            return "Wrong Password"

@limiter.limit('500/minute')
@f.route("/gethatimg/<int:id>")
def GetImg(id):   

    hat=HatPost.query.filter_by(id=id).first()
    if hat:
        png = ImgFromHat(hat.hat)
        response = f.make_response(png)
        response.headers.set('Content-Type', 'image/png')
        response.headers.set('Content-Disposition', 'attachment', filename=(hat.title)+".png")

        response.headers.set('meta',{
            'x':0,
            'y':-16
        })

        return response
    else:
        return None

@f.route("/gethatinfo/<int:id>")
def GetHatInfo(id):   
    hat=HatPost.query.filter_by(id=id).first()
    if hat:
       return render_template("viewhat.html",hat=hat,man=Babe.query.filter_by(id=hat.author_id).first().name)
    else:
        return "404-Hat Missing"   

@limiter.limit("25/minute")
@f.route(hatSection,methods=["POST","GET"])
def Hat():
    search = request.args.get('search')
    page = request.args.get('page')
    
    sort = request.args.get('sort')
    desc = request.args.get('order')

    usr = request.form['author'] if 'author' in request.form else ''
    code =  request.form['pass'] if 'pass' in request.form else ''

    if not search:
        search = ""
    if not(page and str.isdigit(page)):
        page = "1"
    msg =""
    if not sort:
        sort = 't'

    if request.method=="POST":
        msg = DoHatAdding(request.files.getlist('hat[]'),request.form['author'], request.form['pass'],request.environ.get('HTTP_X_REAL_IP', request.remote_addr),request.form['g-recaptcha-response'])

    page = int(page)

    man = Babe.query.filter(func.lower(Babe.name) == func.lower(search)).first()

    q = HatPost.query if search == "" else( HatPost.query.filter(HatPost.title.ilike('%'+search+'%')) if not man else man.hats)
    
    if sort !='r':
        if sort=='a':
            oyster = HatPost.title
        elif sort =='l':
            oyster = HatPost.downloads
        else:
            oyster = HatPost.id
    else:
        oyster = func.random()

    good_desc = (not desc) != (not (sort == 't' or sort == 'l'))

    if good_desc:
        q = q.order_by(oyster.desc())
    else:
        q = q.order_by(oyster)
   
    pag = q.paginate(page=page,per_page=42)

    l = (Adress(page-1,search,sort,desc)) if pag.has_prev else ""
    r = (Adress(page+1,search,sort,desc)) if pag.has_next else ""
    first =(Adress(1,search,sort,desc)) if pag.has_prev else ""
    last =(Adress(pag.pages,search,sort,desc)) if pag.has_next else ""
    to = Adress(page,search,sort,desc)
    clear = Adress(page,"","","")

    return render_template("hatAccept.html",m=msg,hats = pag.items,tol = l,tor=r,p = page,to=to,Babe=Babe,clear = clear,first=first,last=last,sort = sort,desc=desc,search=search,usrNcode = [usr,code],topMsg=os.environ.get('TOP_MSG'))

def HatById(id):
    return HatPost.query.filter_by(id=id).first()

key = bytes([
    243,
    22,
    152,
    32,
    1,
    244,
    122,
    111,
    97,
    42,
    13,
    2,
    19,
    15,
    45,
    230
])

png_header = bytes([137, 80, 78, 71, 13, 10, 26, 10])

png_header = bytes([137, 80, 78, 71, 13, 10, 26, 10])
def ImgFromHat(hat):
    l = 20#int.from_bytes(hat[:4],byteorder='little')+4 

    iv, goodstuff = hat[4:l], hat[l:]

    cip = AES.new(key,AES.MODE_CBC,iv)
    plain = cip.decrypt(goodstuff)
    plain = plain[plain.index(png_header):]
    return plain

def Adress(num,search,sort,order):
    return (hatSection+"?search="+search+"&page="+str(num)+"&sort="+sort+("&order=on" if order else ""))

f.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
db = SQLAlchemy(f)

DGurl = os.environ.get('HOOK_DG')
ZGurl = os.environ.get('HOOK_ZG')
TUrl =  os.environ.get('HOOK_TS')
def DoHatAdding(hats,user,pas,ip,gr):

    length = len(hats)
    user=user.strip()
    pas=pas.strip()

    if length>20:
        return "Please Dont Add More Than 20 Hats at a Time or Buy Me a Premium Server >:("

    if length<1 or not hats[0].filename:
        return "Need Hat!"
    elif user =="":
        return "Need User Name"
    elif pas=="":
        return "Need Passcode!"
    else:

        r = requests.post(f'https://www.google.com/recaptcha/api/siteverify?secret='+googleSecret+'&response={gr}')

        google_response = json.loads(r.text)

        print('JSON: ', google_response)

        if not google_response['success']:
            return '717561636b; BAD CAPTCHA'

        result = ""
        bb = Babe.query.filter_by(name = user).first()
        shouldSubmit = True
        if bb is None:

            baby = Babe()
            baby.name = user
            baby.passcode = pas

            db.session.add(baby)
            db.session.commit()
            result = "Added New Profile: "+user+" and "
        elif bb.passcode != pas:
                return "Incorrect password for user: "+user
                shouldSubmit = False
        
        if shouldSubmit:

            man = Babe.query.filter_by(name = user,passcode=pas).first()
            
            hatNames=""
            i =0

            goodHat = None
            for h in hats:
                if h.filename.lower().endswith('.hat'):
                    hatName = h.filename
                    hatName = re.sub(r"(\w)([A-Z])", r"\1 \2", hatName[:-4])
        
                    hat = HatPost()
                
                    hat.title = hatName
                    hat.author_id =man.id
                    hat.hat = h.read()

                    db.session.add(hat)
                    db.session.commit()
                    hatNames+=hatName+", "

                    if not goodHat and hat:
                        goodHat = hat
                        print(f' good hat is #{goodHat.id}')

                    many = length>1
                    result +=("Added the Hats: "if many else" Added the Hat: ")+hatNames[:-2]
            
            if goodHat:
                print(f'----------------------------------------------------------------trying to add {goodHat.title}')
                bbName = goodHat.title
                bbId = goodHat.id
                manId = goodHat.author_id
                manName = Babe.query.filter_by(id=manId).first().name
                print(bbName+str(bbId)+manName+str(manId))
                post_fields ={
                "content": "New Hat Post!",
                "embeds":  [
                {     
                    "title": f"*By: {manName}*",
                    "description":f"Hat#{bbId-1} \n [Wear Hat](http://quackdex.herokuapp.com/gethatfile/{bbId}) \n [QuackDex.gq](http://quackdex.herokuapp.com/hats)",
                    "url": f"http://quackdex.herokuapp.com/hats?search={urllib.parse.quote(manName)}",
                    "color": random.randint(0,16777215),
                    "thumbnail": {
                        "url": f"https://quackdex.herokuapp.com/gethatimg/{bbId}"
                    },
                    "author": {
                        "name": f"Title: {hatName}",
                        "url": f"https://quackdex.herokuapp.com/hats?search={urllib.parse.quote(hatName)}",
                        "icon_url": "https://cdn.discordapp.com/emojis/274262644838629378.png?v=1"
                    }
                }]
                }
                jsond = json.dumps(post_fields)
                print (len(jsond))

                if __name__ == "__main__" or hatName.lower().startswith('cfif'):
                    db.session.delete(goodHat)
                    db.session.commit()
                    resT = requests.post(TUrl+'?wait=true', data=jsond, headers={"Content-Type": "application/json"}) 
                    print(jsond)
                    print('test: '+str(resT.text+' reason:'+str(resT.reason)))
                else:
                    resDG = requests.post(DGurl+'?wait=true', data=jsond, headers={"Content-Type": "application/json"})     
                    resZG = requests.post(ZGurl+'?wait=true', data=jsond, headers={"Content-Type": "application/json"})                   
                    print('DG: '+str(resDG.status_code)+', '+resDG.text+" :\n "+resDG.reason)
            else:
                print('bad hat')
        
    return result

class Babe(db.Model):
    __tablename__ = "men"
    id = db.Column(db.Integer, primary_key = True)
    name = db.Column(db.String(100), unique=True,nullable = False)
    passcode = db.Column(db.String(100),nullable = False)
    
    hats = db.relationship('HatPost',backref='author',lazy='dynamic')

class HatPost(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    title = db.Column(db.String(200),nullable = False)
    date_posted = db.Column(db.DateTime,nullable = False,default = datetime.now)
    hat = db.Column(db.LargeBinary(length=2048),nullable=False)        
    author_id = db.Column(db.Integer, db.ForeignKey('men.id'),nullable=False)

    downloads = db.Column(db.Integer,default = 0)

def ha(name):
    return HatPost.query.filter(HatPost.title == name).first()

def bab(name):
    return Babe.query.filter(Babe.name == name).first()

if __name__ == '__main__':
    f.run(debug = True)
