from django.db import models
from django.utils import timezone

# Create your models here.

class DetectionRecord(models.Model):
    track_id = models.IntegerField(unique=True, default=1)
    date = models.DateField(default=timezone.now)  # Default to current date
    time = models.TimeField(default=timezone.now)  # Default to current time
    photo = models.ImageField(upload_to='detections/photos/', blank=True, null=True)
    video = models.FileField(upload_to='detections/videos/', blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Detection {self.track_id} on {self.date} at {self.time} (Location: {self.location})"


class SliderItem(models.Model):
    title = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    description = models.TextField()
    background_image = models.ImageField(upload_to='slider_images/')

    def __str__(self):
        return f"{self.title} - {self.name}"


class ContactMessage(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=15, blank=True, null=True)
    message = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message from {self.name} ({self.email})"