from django.db import models


class City(models.Model):
    name = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    lat = models.FloatField()
    lng = models.FloatField()

    class Meta:
        indexes = [models.Index(fields=["name", "state"])]
        unique_together = [("name", "state")]

    def __str__(self):
        return f"{self.name}, {self.state}"


class Station(models.Model):
    opis_id = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    price = models.FloatField()
    lat = models.FloatField()
    lng = models.FloatField()

    class Meta:
        indexes = [
            models.Index(fields=["lat", "lng"]),
            models.Index(fields=["state"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"
