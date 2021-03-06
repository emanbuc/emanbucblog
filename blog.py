import os
import re
import random
import hashlib
import hmac
from string import letters

import webapp2
import jinja2
import json

from google.appengine.ext import db
from datetime import datetime

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

secret = 'pippo'

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val

class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        print 'user login '
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))

def render_post(response, post):
    response.out.write('<b>' + post.subject + '</b><br>')
    response.out.write(post.content)

class MainPage(BlogHandler):
  def get(self):
      self.write('Hello, Udacity!')


##### user stuff
def make_salt(length = 5):
    return ''.join(random.choice(letters) for x in xrange(length))

def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
    return db.Key.from_path('users', group)

class User(db.Model):
    name = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email = None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent = users_key(),
                    name = name,
                    pw_hash = pw_hash,
                    email = email)

    @classmethod
    def login(cls, name, pw):
        print 'username '+name
        print 'password '+pw
        u = cls.by_name(name)
        print 'username utente da validare:'+u.name
        if u and valid_pw(name, pw, u.pw_hash):
            return u

### LOGIN
class Signup(BlogHandler):
    def get(self):
        self.render("signup-form.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username = self.username,
                      email = self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            print 'invalid username'
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            print 'invalid password'
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            print 'invalid password verify'
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            print 'invalid email'
            have_error = True

        if have_error:
            self.render('welcome.html', **params)
        else:
            u = User.register(self.username, self.password, self.email)
            print 'user da registrare:'+ u.name
            u.put()
            self.login(u)
            self.render('welcome.html', **params)
        

class Login(BlogHandler):
    def get(self):
        self.render('login-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/blog')
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error = msg)

class Logout(BlogHandler):
    def get(self):
        self.logout()
        self.redirect('/blog')

##### blog stuff

def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

class Post(db.Model):
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p = self)

class BlogFront(BlogHandler):
    def get(self):
        posts = greetings = Post.all().order('-created')
        self.render('front.html', posts = posts)

class PostPage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            self.error(404)
            return

        self.render("permalink.html", post = post)

class NewPost(BlogHandler):
    def get(self):
        if self.user:
            self.render("newpost.html")
        else:
            self.redirect("/login")

    def post(self):
        if not self.user:
            self.redirect('/blog')

        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            p = Post(parent = blog_key(), subject = subject, content = content)
            p.put()
            self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = "subject and content, please!"
            self.render("newpost.html", subject=subject, content=content, error=error)


##### EVENTS

def calendarevent_key(name = 'default'):
    return db.Key.from_path('calendarevent', name)
    
class CalendarFront(BlogHandler):
    def get(self):
        calendarEvents  = CalendarEvent.all().order('-created')
        self.render('calendarfront.html', calendarEvents = calendarEvents)

class CalendarEventList(BlogHandler):
    def get(self):
        calendarEvents  = CalendarEvent.all().order('-created')
        ##results = calendarEvents.fetch(limit=50)
        result = []
    	for entry in calendarEvents:
        	result.append(dict([(p, unicode(getattr(entry, p))) for p in entry.properties()]))
        print result
        print json.dumps(result)
        self.response.out.write(json.dumps(result))
        

class CalendarEventPage(BlogHandler):
    def get(self, ce_id):
        key = db.Key.from_path('CalendarEvent', int(ce_id), parent=calendarevent_key())
        ce = db.get(key)

        if not ce:
            self.error(404)
            return

        self.render("calendareventpage.html", ce = ce)
        
class CalendarEvent(db.Model):
    title = db.StringProperty(required = True)
    description = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)
    startDate = db.DateTimeProperty(required = False)
    endDate = db.DateTimeProperty(required = False)

    def render(self):
        self._render_text = self.description.replace('\n', '<br>')
        return render_str("event.html", ce = self)

class NewEvent(BlogHandler):
    def get(self):
        if self.user:
            self.render("newevent.html")
        else:
            self.redirect("/login")

    def post(self):
        if not self.user:
            self.redirect('/calendar')

        title = self.request.get('title')
        description = self.request.get('description')
        startDate = self.request.get('startDate')
        endDate = self.request.get('endDate')

        if title and description:
            ce = CalendarEvent(parent = calendarevent_key(), description = description, title = title, startDate=datetime.strptime(startDate, "%Y-%m-%d"), endDate=datetime.strptime(endDate,"%Y-%m-%d"))
            ce.put()
            self.redirect('/calendar/%s' % str(ce.key().id()))
        else:
            error = "title and description, please!"
            self.render("newevent.html", description = description, title = title, error=error)

###### Unit 2 HW's
class Rot13(BlogHandler):
    def get(self):
        self.render('rot13-form.html')

    def post(self):
        rot13 = ''
        text = self.request.get('text')
        if text:
            rot13 = text.encode('rot13')

        self.render('rot13-form.html', text = rot13)


USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)


class Welcome(BlogHandler):
    def get(self):
    	username = self.user
        if valid_username(username):
            self.render('welcome.html',username)
        else:
            self.redirect('/unit2/signup')

app = webapp2.WSGIApplication([('/', MainPage),
                               ('/unit2/rot13', Rot13),
                               ('/blog/?', BlogFront),
                               ('/blog/([0-9]+)', PostPage),
                               ('/blog/newpost', NewPost),
                               ('/calendar/newevent', NewEvent),
                               ('/calendar/?', CalendarFront),
                               ('/calendar/eventlist', CalendarEventList),
                               ('/calendar/([0-9]+)', CalendarEventPage),
                               ('/signup', Signup),
                               ('/login', Login),
                               ('/logout', Logout)
                               ],
                              debug=True)
