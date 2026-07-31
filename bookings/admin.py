from django.contrib import admin
from .models import Location, Bus, Trip, FareCalculation, Ticket, PaymentConfig
from django.core.exceptions import ValidationError

admin.site.register(Location)
admin.site.register(Bus)
admin.site.register(PaymentConfig)

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('route_name', 'date', 'departure_time', 'arrival_time', 'status', 'bus')
    list_filter = ('date', 'status')

@admin.register(FareCalculation)
class FareCalculationAdmin(admin.ModelAdmin):
    list_display = ('trip', 'origin', 'destination', 'price', 'segment_departure_time', 'segment_arrival_time')
    list_filter = ('origin', 'destination')
    def clean(self):
        
        if self.segment_departure_time and self.segment_departure_time < self.trip.departure_time:
            raise ValidationError(f"Error: Segment departure time ({self.segment_departure_time}) cannot be earlier than the main trip departure time ({self.trip.departure_time}).")
        
        
        if self.trip.arrival_time and self.segment_arrival_time:
            if self.segment_arrival_time > self.trip.arrival_time:
                raise ValidationError(f"Error: Segment arrival time ({self.segment_arrival_time}) cannot be later than the main trip arrival time ({self.trip.arrival_time}).")

    def save(self, *args, **kwargs):
        self.clean() # Force the clean method to run before saving
        super().save(*args, **kwargs)

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('pnr_number', 'passenger_name', 'trip', 'seat_number', 'ticket_status', 'payment_status')
    search_fields = ('pnr_number', 'passenger_name', 'passenger_cnic')
    list_filter = ('ticket_status', 'payment_status', 'created_at')