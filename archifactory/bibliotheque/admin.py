from django.contrib import admin

# Register your models here.

from .models import Application, Person, Environnement, DAT, ComposantLogiciel, Environnement

admin.site.register(Person)
admin.site.register(Environnement)
admin.site.register(DAT)
admin.site.register(ComposantLogiciel)

class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'ApplicationID', 'UrbaID') 

admin.site.register(Application, ApplicationAdmin)