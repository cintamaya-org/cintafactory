from django.shortcuts import render
from django.views import generic

from .models import Application, DAT, Person

# Create your views here.
class PersonListView(generic.ListView):
    model=Person
    
class DATListView(generic.ListView):
    model=DAT

def index(request):
    
    num_dossier = DAT.objects.all().count()
    num_person = Person.objects.all().count()
