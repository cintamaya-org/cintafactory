from django.contrib import admin

# Register your models here.

from .models import Application, Person, Environnement, DAT

admin.site.register(Person)
admin.site.register(Application)
admin.site.register(Environnement)
admin.site.register(DAT)

