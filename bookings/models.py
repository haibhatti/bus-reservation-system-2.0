import uuid
from django.db import models

class Location(models.Model):
    name = models.CharField(max_length=250, unique=True)
    def __str__(self):
        return self.name

class Bus(models.Model):
    bus_name = models.CharField(max_length=250, unique=True)
    total_seats = models.IntegerField(default=40)
    
    is_active = models.BooleanField(default=True, help_text="Set to False to retire a bus without deleting historical tickets.")

    def __str__(self):
        return f"{self.bus_name} ({self.total_seats} Seats)"

class Trip(models.Model):
    class TripStatus(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Scheduled'
        DELAYED = 'DELAYED', 'Delayed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        COMPLETED = 'COMPLETED', 'Completed'

    bus = models.ForeignKey(Bus, on_delete=models.PROTECT, related_name='trips')
    route_name = models.CharField(max_length=255)
    date = models.DateField()
    departure_time = models.TimeField()
    status = models.CharField(max_length=20, choices=TripStatus.choices, default=TripStatus.SCHEDULED)

    def __str__(self):
        return f"{self.route_name} | {self.date} at {self.departure_time.strftime('%H:%M')}"

class FareCalculation(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='fares')
    origin = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='fare_origins')
    destination = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='fare_destinations')
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('trip', 'origin', 'destination')

    def __str__(self):
        return f"{self.origin} → {self.destination}: Rs. {self.price}"

class Ticket(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING_TERMINAL = 'PENDING_TERMINAL', 'Pending Terminal Cash Payment'
        PENDING_ONLINE = 'PENDING_ONLINE', 'Pending Online Payment'
        PAID_TERMINAL = 'PAID_TERMINAL', 'Paid at Terminal Counter'
        PAID_ONLINE = 'PAID_ONLINE', 'Paid Online'
        REFUND_REQUESTED = 'REFUND_REQUESTED', 'Refund Requested'
        REFUNDED = 'REFUNDED', 'Refunded'
        CANCELLED = 'CANCELLED', 'Cancelled (No Payment Owed)'

    class TicketStatus(models.TextChoices):
        PENDING_OTP = 'PENDING_OTP', 'Pending OTP Verification'
        RESERVED = 'RESERVED', 'Reserved (Awaiting Payment)'
        CONFIRMED = 'CONFIRMED', 'Confirmed & Paid'
        CANCELLED_BY_PASSENGER = 'CANCELLED_USER', 'Cancelled by Passenger'
        CANCELLED_BY_COMPANY = 'CANCELLED_COMPANY', 'Cancelled by Bus Company'
        CANCELLED = 'CANCELLED', 'Cancelled (No Payment Owed)'

    trip = models.ForeignKey(Trip, on_delete=models.PROTECT, related_name='tickets')
    origin = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='ticket_origins')
    destination = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='ticket_destinations')
    
    seat_number = models.IntegerField()
    fare_paid = models.DecimalField(max_digits=10, decimal_places=2)

    passenger_name = models.CharField(max_length=255)
    passenger_cnic = models.CharField(max_length=15)
    passenger_email = models.EmailField()
    passenger_phone = models.CharField(max_length=20)
    sender_account_name = models.CharField(max_length=255, blank=True, null=True)

    pnr_number = models.CharField(max_length=8, unique=True, editable=False)
    verification_code = models.CharField(max_length=6, blank=True, null=True)
    is_verified = models.BooleanField(default=False)

    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING_TERMINAL)
    ticket_status = models.CharField(max_length=20, choices=TicketStatus.choices, default=TicketStatus.PENDING_OTP)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('trip', 'seat_number')
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.pnr_number:
            self.pnr_number = uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"PNR: {self.pnr_number} | {self.passenger_name} (Seat {self.seat_number})"


class PaymentConfig(models.Model):
    account_title = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    payment_option_1 = models.CharField(max_length=20, blank=True, null=True)
    payment_option_2 = models.CharField(max_length=20, blank=True, null=True)
    instructions = models.TextField(blank=True, help_text="Additional payment instructions")
    
    def __str__(self):
        return "Payment Settings"