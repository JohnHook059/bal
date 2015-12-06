from flask import Flask, render_template, request, g, session, flash, \
     redirect, url_for, abort
from flask.ext.openid import OpenID

from openid.extensions import pape

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

app = Flask(__name__)
app.config.update(
    DATABASE_URI = 'sqlite:///base.db',
    SECRET_KEY = 'development key',
    DEBUG = True
)

oid = OpenID(app, safe_roots=[], extension_responses=[pape.Response])

engine = create_engine(app.config['DATABASE_URI'])
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=True, bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
    Base.metadata.create_all(bind=engine)


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    email = Column(String(200))
    openid = Column(String(200))
    sex = Column(String(20))
    favorite = Column(String(2000))

    def __init__(self, name, email, openid, sex, favorite):
        self.name = name
        self.email = email
        self.openid = openid
        self.sex = sex
        self.favorite = favorite


@app.before_request
def before_request():
    g.user = None
    if 'openid' in session:
        g.user = User.query.filter_by(openid=session['openid']).first()


@app.after_request
def after_request(response):
    db_session.remove()
    return response


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
@oid.loginhandler
def login():
    if g.user is not None:
        return redirect(oid.get_next_url())
    if request.method == 'POST':
        openid = request.form.get('openid')
        if openid:
            pape_req = pape.Request([])
            return oid.try_login(openid, ask_for=['email', 'nickname'],
                                         ask_for_optional=['fullname'],
                                         extensions=[pape_req])
    return render_template('login.html', next=oid.get_next_url(),
                           error=oid.fetch_error())


@oid.after_login
def create_or_login(resp):
    session['openid'] = resp.identity_url
    if 'pape' in resp.extensions:
        pape_resp = resp.extensions['pape']
        session['auth_time'] = pape_resp.auth_time
    user = User.query.filter_by(openid=resp.identity_url).first()
    if user is not None:
        flash(u'Successfully signed in')
        g.user = user
        return redirect(oid.get_next_url())
    return redirect(url_for('create_profile', next=oid.get_next_url(),
                            name=resp.fullname or resp.nickname,
                            email=resp.email))


@app.route('/create-profile', methods=['GET', 'POST'])
def create_profile():
    if g.user is not None or 'openid' not in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        sex = request.form['sex']
        if not name:
            flash(u'Error: you have to provide a name')
        elif '@' not in email:
            flash(u'Error: you have to enter a valid email address')
        elif sex != 'Male' and sex != 'Female':
            flash(u'Error: you have to provide a sex')
        else:
            flash(u'Profile successfully created')
            db_session.add(User(name, email, session['openid'], sex, ''))
            db_session.commit()
            return redirect(oid.get_next_url())
    return render_template('create_profile.html', next_url=oid.get_next_url())


@app.route('/profile', methods=['GET', 'POST'])
def edit_profile():
    if g.user is None:
        abort(401)
    form = dict(name=g.user.name, email=g.user.email, sex=g.user.sex, favorite=g.user.favorite)
    if request.method == 'POST':
        if 'delete' in request.form:
            g.user.openid = 'DEL'
            # db_session.delete(g.user)
            db_session.commit()
            session['openid'] = None
            flash(u'Profile deleted')
            return redirect(url_for('index'))
        form['name'] = request.form['name']
        form['email'] = request.form['email']
        form['sex'] = request.form['sex']

        favorite = ''
        for i in sorted(request.form.keys()):
            if request.form[i] == 'on':
                while len(favorite) <= int(i) - 1:
                    favorite += '0'
                favorite += '1'
        form['favorite'] = favorite
        # print(request.form)

        if not form['name']:
            flash(u'Error: you have to provide a name')
        elif '@' not in form['email']:
            flash(u'Error: you have to enter a valid email address')
        elif form['sex'] != 'Male' and form['sex'] != 'Female':
            flash(u'Error: you have to provide a sex')
        else:
            flash(u'Profile successfully created')
            g.user.name = form['name']
            g.user.email = form['email']
            g.user.sex = form['sex']
            g.user.favorite = form['favorite']
            db_session.commit()
            return redirect(url_for('edit_profile'))

    users = []
    for user in db_session.query(User).order_by(User.id):
        if user.sex != g.user.sex and user.openid != 'DEL':
            users.append(user)
    return render_template('edit_profile.html', form=form, users=users, users_len=len(users))


@app.route('/logout')
def logout():
    session.pop('openid', None)
    flash(u'You have been signed out')
    return redirect(oid.get_next_url())


if __name__ == '__main__':
    init_db()
    app.run(port=5001)
