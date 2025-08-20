from django.shortcuts import render

# Create your views here.

from .models import Application, DAT, Person

def index(request):
    
    num_dossier = DAT.objects.all().count()
    num_person = Person.objects.all().count()



