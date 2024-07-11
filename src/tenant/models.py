from django.db import models
from django.db.models.signals import post_save
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
import json
from django.conf import settings
import os


class Client(models.Model):
    username = models.CharField(unique=True, max_length=250)
    email = models.EmailField(max_length=250)
    password = models.CharField(max_length=250)

    def __str__(self) -> str:
        return self.username


# Create your models here.
class Tenant(models.Model):
    name = models.CharField(unique=True, max_length=250)
    db_name = models.CharField(unique=True, max_length=250)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if len(self.db_name.split(" ")) > 1:
            raise Exception("db_name cannot have spaces.")

        return super().save(*args, **kwargs)


import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def add_to_local_json(config, db_name):
    file_path = "{}/{}".format(settings.BASE_DIR, 'db.json')
    existing_data = None

    if not os.path.isfile(file_path):
        with open(file_path, 'w') as file:
            json.dump({}, file)
            existing_data = {}
    else:
        with open(file_path, 'r') as file:
            existing_data = json.load(file)

    if type(existing_data) == dict:
        existing_data[db_name] = config
    
    with open(file_path, 'w') as file:
        file.write(json.dumps(existing_data, indent=4))

def make_config(db_name):
    return {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": db_name,
        "USER": "admin",
        "PASSWORD": "admin",
        "HOST": "localhost",
        "PORT": "5432",
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {},
        "TIME_ZONE": None,
        "TEST": {
            "CHARSET": None,
            "COLLATION": None,
            "MIGRATE": True,
            "MIRROR": None,
            "NAME": None,
        },
    }

def internal_migrate(db_name: str):
    call_command("migrate", "--database={}".format(db_name))

def create_superuser(username, email, password, db_name):
    User: type[AbstractUser] = get_user_model()
    if not User.objects.using(db_name).filter(username=username).exists():
        user = User.objects.using(db_name).create(
            username=username,
            email=email,
            is_superuser=True,
            is_staff=True            
        )
        user.set_password(password)
        user.save(using=db_name)

        print(f"Superuser {username} created successfully.")
    else:
        print(f"Superuser {username} already exists.")


def create_db(sender, instance: Tenant, **kwargs):
    print(
        "Creating data for tenant, id: {}, name: {}".format(instance.pk, instance.name)
    )
    conn = psycopg2.connect(
        database="tenantdefault", user="admin", password="admin", host="localhost"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    db_name = sql.Identifier(instance.db_name).string
    try:
        cur.execute(sql.SQL("CREATE DATABASE {};".format(db_name)))
        add_to_local_json(make_config(db_name), db_name)
        settings.DATABASES[db_name] = make_config(db_name)
        internal_migrate(db_name=db_name)
    except Exception as e:
        print(str(e))
        cur.execute(sql.SQL("DELETE DATABASE {};".format(db_name)))

    if instance.client:
        create_superuser(
            instance.client.username,
            instance.client.email,
            instance.client.password,
            db_name,
        )


post_save.connect(create_db, Tenant)
