#!/usr/bin/env python
#-*- coding: utf-8 -*-
from urlparse import urlparse
import config
import hashlib,uuid
from framework.db import with_connection
from models import User,Blog,Tag,BlogTag
from models import *
from framework.web import get, post, ctx, view, interceptor, seeother, notfound
from framework.apis import api, Page, APIError, APIValueError, APIPermissionError, APIResourceNotFoundError
import os.path
import os, re, time, base64, hashlib, logging
from config import configs
import sae.storage
import markdown2
from framework import db
_COOKIE_NAME = 'jblog'
_COOKIE_KEY = configs.session.secret
CHUNKSIZE = 8192
UPLOAD_PATH='upload'
SAE_BUCKET = 'code4awesome'
@view('content.html')
@get('/')
def all_blogs():
    blogs = Blog.find_all()
    for blog in blogs:
        blog.content = markdown2.markdown(blog.content)
    main = blogs[0]
    sub = blogs[1:]
    #if not config.SAE:
        #for blog in sub:
            #os.path.join('..',blog.image)
    user = ctx.request.user
    return dict(main=main,sub=sub,user=user)

@view('signin.html')
@get('/signin')
def signin():
    user = ctx.request.user
    return dict(user=user)


def make_signed_cookie(id, password, max_age):
    # build cookie string by: id-expires-md5
    expires = str(int(time.time() + (max_age or 86400)))
    L = [id, expires, hashlib.md5('%s-%s-%s-%s' % (id, password, expires, _COOKIE_KEY)).hexdigest()]
    return '-'.join(L)
#@api
@post('/api/authenticate')
def authenticate():
    i = ctx.request.input(remember='')
    email = i.email.strip().lower()
    password = i.password
    remember = i.remember
    user = User.find_first('where email=?', email)
    if user is None:
        raise APIError('auth:failed', 'email', 'Invalid email.')
    elif user.password != password:
        raise APIError('auth:failed', 'password', 'Invalid password.')
    # make session cookie:
    max_age = 604800 if remember=='true' else None
    cookie = make_signed_cookie(user.id, user.password, max_age)
    ctx.response.set_cookie(_COOKIE_NAME, cookie, max_age=max_age)
    user.password = '******'
    raise seeother('/')
    return user


def parse_signed_cookie(cookie_str):
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        id, expires, md5 = L
        if int(expires) < time.time():
            return None
        user = User.get(id)
        if user is None:
            return None
        if md5 != hashlib.md5('%s-%s-%s-%s' % (id, user.password, expires, _COOKIE_KEY)).hexdigest():
            return None
        return user
    except:
        return None

@interceptor('/')
def user_interceptor(next):
    logging.info('try to bind user from session cookie...')
    user = None
    cookie = ctx.request.cookies.get(_COOKIE_NAME)
    if cookie:
        logging.info('parse session cookie...')
        user = parse_signed_cookie(cookie)
        if user:
            logging.info('bind user <%s> to session...' % user.email)
    ctx.request.user = user
    return next()


@get('/signout')
def signout():
    ctx.response.delete_cookie(_COOKIE_NAME)
    raise seeother('/')


def check_admin():
    user = ctx.request.user
    if user and user.admin:
        return
    raise APIPermissionError('No permission.')

def upload(image):
    filename = os.path.join(UPLOAD_PATH,hashlib.md5(image.filename.encode('utf-8')).hexdigest()+uuid.uuid4().hex)
    if 'SERVER_SOFTWARE' in os.environ:
       conn = sae.storage.Connection() 
       bucket = conn.get_bucket(SAE_BUCKET)
       bucket.put_object(filename,image.file)
       filename = bucket.generate_url(filename)
       logging.info(filename)
    else:
        with open(filename,'w') as f:
            chunk = image.file.read(CHUNKSIZE)
            while chunk:
                f.write(chunk)
                chunk = image.file.read(CHUNKSIZE)
    return filename

def delete_upload(filename):
    if 'SERVER_SOFTWARE' in os.environ:
       conn = sae.storage.Connection() 
       bucket = conn.get_bucket(SAE_BUCKET)
       filename = urlparse(filename).path[1:]
       bucket.delete_object(filename)
    else:
        if os.path.isfile(filename):
            os.remove(filename)
    logging.info("remove file %s." % filename)

def add_tags(blog_id,tags):
    if not tags:
        return
    if not tags[0]:
        return
    for tag in tags:
        t=Tag.find_by('where name=?',tag)
        if t:
            t = t[0]
        if not t:
            t = Tag(name=tag)
            t.insert()
        bt = BlogTag(blog_id=blog_id,tag_id=t.id)
        bt.insert()
        logging.info("######add tag %s----%s" % (blog_id,tag))



@post('/api/blogs')
def api_create_blog():
    check_admin()
    i = ctx.request.input(title='', content='')
    logging.info(i)
    title = i.title.strip()
    content = i.content.strip()
    image = i.image
    tags = i.tags.strip()
    logging.info("upload image name:%s,type:%s" % (image.filename,type(image.filename)))
    if not title:
        raise APIValueError('name', 'name cannot be empty.')
    #if not summary:
        #raise APIValueError('summary', 'summary cannot be empty.')
    if not content:
        raise APIValueError('content', 'content cannot be empty.')
    filename = upload(image)
    user = ctx.request.user
    blog = Blog(user_id=user.id,  title=title,  content=content,image=filename)
    blog.insert()
    add_tags(blog.id,tags.split(' '))
    raise seeother('/blog/%s' % blog.id)
    return blog

@view("add_blog.html")
@get('/manage/add_blog')
def add_blog():
    user = ctx.request.user
    return dict(user=user)


@interceptor('/manage/')
def manage_interceptor(next):
    user = ctx.request.user
    if user and user.admin:
        return next()
    raise seeother('/signin')

@view("blog.html")
@get('/blog/:id')
def blog(id):
    blog = Blog.get(id)
    blog.content = markdown2.markdown(blog.content)
    if 'SERVER_SOFTWARE' not in os.environ:
        blog.image = '/'+blog.image
    if blog:
        tags = get_tags_from_blog(blog)
        return dict(blog=blog,user=ctx.request.user,tags=tags)
    raise notfound()

@view("edit_blog.html")
@get('/manage/edit/:id')
def edit_blog(id):
    blog = Blog.get(id)
    if not blog:
        raise notfound()
    tags = get_tags_from_blog(blog)
    return dict(blog=blog,user=ctx.request.user,tags=tags)

    
def update_tags(blog,tag_checkbox,tags):
    origin = get_tags_from_blog(blog)
    origin_ids = [tag.id for tag in origin]
    origin_names = [tag.name for tag in origin]

    #remove用的id
    remove = list(set(origin_ids).difference(set(tag_checkbox)))
    remove_blogtag(blog,remove)
    #add用的name
    if tags and tags[0]:
        add = list(set(tags).difference(set(origin_names)))
        add_tags(blog.id,add)

    

@post('/manage/edit/:id')
def api_edit_blog(id):
    check_admin()
    i = ctx.request.input()
    logging.info(i)
    title = i.title.strip()
    content = i.content.strip()
    image = i.image
    tags = i.tags
    try:
        tag_checkbox = ctx.request.gets('tag_checkbox')
    except KeyError:
        tag_checkbox = []
    logging.info("##################")
    logging.info(tag_checkbox)
    if not title:
        raise APIValueError('name', 'name cannot be empty.')
    if not content:
        raise APIValueError('content', 'content cannot be empty.')
    blog = Blog.get(id)
    if not blog:
        raise notfound()
    blog.title = title
    blog.content = content
    if image:
        delete_upload(blog.image)
        filename = upload(image)
        blog.image = filename
    blog.update()
    update_tags(blog,tag_checkbox,tags.split(' '))
    raise seeother('/blog/%s' % blog.id)

@post('/manage/delete/:id')
def delete_blog(id):
    check_admin()
    blog = Blog.get(id)
    if not blog:
        raise notfound()
    delete_upload(blog.image)
    blog.delete()
    return "/"
