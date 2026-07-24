from django.contrib import admin

from .models import IncomingOrder, Menu, MenuItem, Restaurant

admin.site.register(Restaurant)
admin.site.register(Menu)
admin.site.register(MenuItem)
admin.site.register(IncomingOrder)
