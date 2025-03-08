from django.contrib import admin

# Register your models here.
from .models import DetectionRecord ,SliderItem ,ContactMessage

admin.site.register(DetectionRecord)
admin.site.register(SliderItem)
admin.site.register(ContactMessage)