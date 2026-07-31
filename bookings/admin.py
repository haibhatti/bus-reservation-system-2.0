from django.contrib import admin
from .models import Location, Bus, Trip, FareCalculation, Ticket, PaymentConfig

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

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('pnr_number', 'passenger_name', 'trip', 'seat_number', 'ticket_status', 'payment_status')
    search_fields = ('pnr_number', 'passenger_name', 'passenger_cnic')
    list_filter = ('ticket_status', 'payment_status', 'created_at')