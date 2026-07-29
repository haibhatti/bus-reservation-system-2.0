from django.contrib import admin
from .models import Location, Bus, Trip, FareCalculation, Ticket, PaymentConfig

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ('bus_name', 'total_seats')
    search_fields = ('bus_name',)

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('route_name', 'bus', 'date', 'departure_time', 'status')
    list_filter = ('status', 'date', 'bus')
    search_fields = ('route_name', 'bus__bus_name')
    list_editable = ('status',)  # Allows quick status changes right from the list table!

@admin.register(FareCalculation)
class FareCalculationAdmin(admin.ModelAdmin):
    list_display = ('origin', 'destination', 'trip', 'price')
    list_filter = ('origin', 'destination')
    search_fields = ('trip__route_name',)

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('pnr_number', 'passenger_name', 'trip', 'seat_number', 'fare_paid', 'payment_status', 'ticket_status', 'is_verified')
    list_filter = ('payment_status', 'ticket_status', 'is_verified', 'created_at')
    search_fields = ('pnr_number', 'passenger_name', 'passenger_cnic', 'passenger_phone')
    readonly_fields = ('pnr_number', 'created_at')

@admin.register(PaymentConfig)
class PaymentConfigAdmin(admin.ModelAdmin):
    pass