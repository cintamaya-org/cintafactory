from django.test import TestCase

class SmokeTest(TestCase):
    def test_import(self):
        from .models import DAT
        self.assertTrue(DAT)
