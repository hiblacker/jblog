#!/usr/bin/env python
#-*- coding:utf-8 -*-

import time,uuid
from framework.db import next_id
from framework.orm import Model,StringField,BooleanField,FloatField,TextField
from framework import db
import logging

class User(Model):
    __table__ = "users"

    id = StringField(primary_key=True,default=next_id,ddl='varchar(50)')
    email = StringField(updatable=False,ddl='varchar(50)')
    password = StringField(ddl='varchar(50)')
    admin = BooleanField()
    created_at = FloatField(updatable=False,default=time.time)

class Blog(Model):
    __table__ = 'blogs'

    id = StringField(primary_key=True,default=next_id,ddl='varchar(50)')
    user_id = StringField(updatable=False,ddl='varchar(50)')
    title = StringField(ddl='varchar(50)')
    content = TextField()
    image = StringField(ddl='varchar(500)')
    created_at = FloatField(updatable=False,default=time.time)

class Tag(Model):
    __table__ = 'tags'
    id = StringField(primary_key=True,default=next_id,ddl='varchar(50)')
    name = StringField(ddl='varchar(50)')

class BlogTag(Model):
    __table__ = 'blogtag'
    id = StringField(primary_key=True,default=next_id,ddl='varchar(50)')
    blog_id = StringField(updatable=False,ddl='varchar(50)')
    tag_id = StringField(updatable=False,ddl='varchar(50)')


def get_tags_from_blog(blog):
    tags = db.select('select tags.id,tags.name from tags,blogtag where tags.id=blogtag.tag_id and blogtag.blog_id="%s"' % blog.id)
    return tags

def remove_blogtag(blog,remove):
    if not remove:
        return
    remove_string = "','".join(remove)
    s='delete from blogtag where blogtag.blog_id="%s" and blogtag.tag_id in (\'%s\')' % (blog.id,remove_string)
    logging.info('#########')
    logging.info(s)
    db.update(s)
