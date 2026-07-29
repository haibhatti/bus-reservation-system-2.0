import random
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone
from django.db import models
from .models import Trip, Location, FareCalculation, Ticket, PaymentConfig
from .forms import RouteSearchForm, TicketForm

# generate 6 digit otp for email verification
def generate_otp():
    return str(random.randint(100000, 999999))

# send e-ticket when paid
def send_booking_confirmation(ticket):
    subject = f"Booking Confirmed - PNR: {ticket.pnr_number}"
    message = (
        f"Dear {ticket.passenger_name},\n\n"
        f"Your ticket from {ticket.origin} to {ticket.destination} "
        f"on {ticket.trip.date} at {ticket.trip.departure_time.strftime('%H:%M')} is confirmed.\n"
        f"Seat Number: {ticket.seat_number}\n"
        f"Fare Amount: Rs. {ticket.fare_paid}\n\n"
        f"Thank you for choosing Bus Reservation System."
    )
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [ticket.passenger_email], fail_silently=False)

# handle all cancellation and refund emails smartly
def send_smart_cancellation_email(ticket, reason_text, refund_type=None):
    subject = f"Reservation Update - PNR: {ticket.pnr_number}"
    
    message_body = (
        f"Dear {ticket.passenger_name},\n\n"
        f"Your ticket reference (PNR: {ticket.pnr_number}) for traveling from {ticket.origin} to {ticket.destination} "
        f"on {ticket.trip.date} has been CANCELLED.\n\n"
        f"Reason: {reason_text}\n\n"
    )

    if refund_type == 'ONLINE_REFUND_QUEUE':
        message_body += (
            "--- REFUND INSTRUCTIONS ---\n"
            "As you paid via Online Banking / Transfer, your refund is now in our processing queue.\n"
            "Please REPLY to this email with your: Bank Name, Account Title, and Account Number.\n"
            "Our team will transfer your refund within 3 business days.\n\n"
        )
    elif refund_type == 'CASH_REFUND_QUEUE':
        message_body += (
            "--- REFUND INSTRUCTIONS ---\n"
            "Our records show you paid cash at the terminal counter.\n"
            "To collect your refund, please visit our terminal desk and present your original CNIC.\n"
        )
    elif refund_type == 'INSTANT_CASH_REFUNDED':
        message_body += (
            "--- REFUND PROCESSED ---\n"
            f"As this cancellation was handled at the terminal desk, your cash refund of Rs. {ticket.fare_paid} "
            "has been processed across the counter. No further action is required.\n\n"
        )
    else:
        message_body += (
            "--- PAYMENT STATUS ---\n"
            "As this reservation was cancelled before payment was completed, your pending balance is Rs. 0.00.\n"
            "No payment is owed, and your seat has been released.\n\n"
        )

    message_body += "Thank you for using Bus Reservation System."
    send_mail(subject, message_body, settings.DEFAULT_FROM_EMAIL, [ticket.passenger_email], fail_silently=False)


# display upcoming trips on homepage
def home(request):
    today = timezone.now().date()
    upcoming_trips = Trip.objects.filter(
        status=Trip.TripStatus.SCHEDULED,
        date__gte=today,
        fares__isnull=False
    ).distinct().order_by('date', 'departure_time')[:8]
    
    return render(request, 'home.html', {'upcoming_trips': upcoming_trips})

# route search and matching logic
def search_route(request):
    form = RouteSearchForm()
    trips = None 

    if request.method == 'POST':
        form = RouteSearchForm(request.POST)
        if form.is_valid():
            origin = form.cleaned_data['origin']
            destination = form.cleaned_data['destination']
            
            # save to session for next step
            request.session['search_origin_id'] = origin.id
            request.session['search_destination_id'] = destination.id

            fare_rules = FareCalculation.objects.filter(origin=origin, destination=destination)
            trip_ids = fare_rules.values_list('trip_id', flat=True).distinct()
            trips = Trip.objects.filter(id__in=trip_ids, status=Trip.TripStatus.SCHEDULED)
            
            return render(request, 'search_route.html', {'form': form, 'trips': trips})

    return render(request, 'search_route.html', {'form': form})

# step 1: seat layout and passenger details
def book_ticket_step_1(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    
    origin_id = request.session.get('search_origin_id')
    dest_id = request.session.get('search_destination_id')

    if not origin_id or not dest_id:
        messages.error(request, "Please search for a route and select your cities first.")
        return redirect('search_route')

    origin = get_object_or_404(Location, id=origin_id)
    destination = get_object_or_404(Location, id=dest_id)

    try:
        fare_rule = FareCalculation.objects.get(trip=trip, origin=origin, destination=destination)
    except FareCalculation.DoesNotExist:
        messages.error(request, "Pricing has not been configured for this route yet.")
        return redirect('search_route')

    # list of seats already booked
    booked_seats = Ticket.objects.filter(trip=trip).exclude(
        ticket_status__in=[Ticket.TicketStatus.CANCELLED_BY_PASSENGER, Ticket.TicketStatus.CANCELLED_BY_COMPANY]
    ).values_list('seat_number', flat=True)

    if request.method == 'POST':
        passenger_name = request.POST.get('passenger_name')
        passenger_cnic = request.POST.get('passenger_cnic')
        passenger_email = request.POST.get('passenger_email')
        passenger_phone = request.POST.get('passenger_phone')
        seat_number = int(request.POST.get('seat_number'))
        payment_method = request.POST.get('payment_method', 'TERMINAL')
        sender_account_name = request.POST.get('sender_account_name', '').strip()

        # check cnic regex
        if not re.match(r'^\d{5}-\d{7}-\d{1}$', passenger_cnic):
            messages.error(request, "CNIC must be in the standard format: 35202-1234567-1")
            return render(request, 'book_step_1.html', {
                'trip': trip, 'origin': origin, 'destination': destination, 'fare': fare_rule.price,
                'booked_seats': list(booked_seats), 'total_seats_range': range(1, trip.bus.total_seats + 1),
                'payment_config': PaymentConfig.objects.first()
            })

        # ensure seat is not tampered
        if seat_number in booked_seats:
            messages.error(request, f"Seat #{seat_number} has already been taken. Please pick another.")
            return redirect('book_ticket_step_1', trip_id=trip.id)

        # bypass otp for logged-in staff at counter
        if request.user.is_authenticated:
            is_cash = (payment_method == 'TERMINAL')
            
            ticket = Ticket.objects.create(
                trip=trip, origin=origin, destination=destination,
                seat_number=seat_number, fare_paid=str(fare_rule.price),
                passenger_name=passenger_name, passenger_cnic=passenger_cnic,
                passenger_email=passenger_email, passenger_phone=passenger_phone,
                is_verified=True, 
                ticket_status=Ticket.TicketStatus.CONFIRMED if is_cash else Ticket.TicketStatus.RESERVED,
                payment_status=Ticket.PaymentStatus.PAID_TERMINAL if is_cash else Ticket.PaymentStatus.PENDING_ONLINE,
                sender_account_name=sender_account_name
            )
            
            if is_cash:
                messages.success(request, f"Walk-in cash ticket confirmed for {passenger_name}!")
            else:
                messages.warning(request, f"Online reservation created for {passenger_name}. Please verify bank transfer on dashboard to confirm!")
                
            return redirect('booking_success', pnr=ticket.pnr_number)
        
        # save passenger details in session and send otp
        otp = generate_otp()
        request.session['temp_booking'] = {
            'trip_id': trip.id, 'origin_id': origin.id, 'destination_id': destination.id,
            'passenger_name': passenger_name, 'passenger_cnic': passenger_cnic,
            'passenger_email': passenger_email, 'passenger_phone': passenger_phone,
            'seat_number': seat_number, 'fare_paid': str(fare_rule.price),
            'payment_method': payment_method, 'otp': otp,
            'sender_account_name': sender_account_name
        }

        subject = f"Verification Code: {otp} - Bus Reservation System"
        message = f"Dear {passenger_name},\n\nYour verification code to lock Seat #{seat_number} is: {otp}\n\nPlease enter this on the website to finalize your reservation."
        
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [passenger_email])
            return redirect('verify_otp_step_2')
        except Exception as e:
            messages.error(request, f"Email delivery failed. Please check your internet or Mailtrap settings. Error: {e}")
            return redirect('book_ticket_step_1', trip_id=trip.id)

    return render(request, 'book_step_1.html', {
        'trip': trip, 'origin': origin, 'destination': destination,
        'fare': fare_rule.price, 'booked_seats': list(booked_seats),
        'total_seats_range': range(1, trip.bus.total_seats + 1),
        'payment_config': PaymentConfig.objects.first()
    })

# step 2: process otp and save ticket
def verify_otp_step_2(request):
    temp = request.session.get('temp_booking')
    
    if not temp:
        messages.error(request, "Your booking session expired or is invalid. Please start again.")
        return redirect('home')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp_code')

        if entered_otp == temp['otp']:
            # race condition check: verify seat is still empty
            seat_taken = Ticket.objects.filter(
                trip_id=temp['trip_id'], seat_number=temp['seat_number']
            ).exclude(
                ticket_status__in=[Ticket.TicketStatus.CANCELLED_BY_PASSENGER, Ticket.TicketStatus.CANCELLED_BY_COMPANY]
            ).exists() 

            if seat_taken:
                messages.error(request, f"We apologize, but Seat #{temp['seat_number']} was just bought by someone else while you were verifying.")
                del request.session['temp_booking']  
                return redirect('book_ticket_step_1', trip_id=temp['trip_id'])

            trip = get_object_or_404(Trip, id=temp['trip_id'])
            origin = get_object_or_404(Location, id=temp['origin_id'])
            destination = get_object_or_404(Location, id=temp['destination_id'])

            pay_method = temp.get('payment_method', 'TERMINAL')
            if pay_method == 'ONLINE':
                initial_pay_status = Ticket.PaymentStatus.PENDING_ONLINE
            else:
                initial_pay_status = Ticket.PaymentStatus.PENDING_TERMINAL

            ticket = Ticket.objects.create(
                trip=trip, origin=origin, destination=destination,
                seat_number=temp['seat_number'], fare_paid=temp['fare_paid'],
                passenger_name=temp['passenger_name'], passenger_cnic=temp['passenger_cnic'],
                passenger_email=temp['passenger_email'], passenger_phone=temp['passenger_phone'],
                verification_code=entered_otp, is_verified=True,
                ticket_status=Ticket.TicketStatus.RESERVED, payment_status=initial_pay_status,
                sender_account_name=temp.get('sender_account_name', '')
            )

            del request.session['temp_booking']
            return redirect('booking_success', pnr=ticket.pnr_number)
        else:
            messages.error(request, "Invalid verification code entered. Please check your email and try again.")

    return render(request, 'verify_otp.html', {'email': temp['passenger_email']})

# final receipt view
def booking_success(request, pnr):
    ticket = get_object_or_404(Ticket, pnr_number=pnr)
    payment_config = PaymentConfig.objects.first()
    
    return render(request, 'booking_success.html', {
        'ticket': ticket,
        'payment_config': payment_config
    })

# passenger tracking 
def track_booking(request):
    ticket = None
    if request.method == 'POST':
        pnr = request.POST.get('pnr_number', '').strip().upper()
        cnic = request.POST.get('passenger_cnic', '').strip()
        
        ticket = Ticket.objects.filter(pnr_number=pnr, passenger_cnic=cnic).first()
        
        if not ticket:
            messages.error(request, "No reservation found matching this PNR and CNIC combination. Please check your spelling.")
            
    return render(request, 'track_booking.html', {'ticket': ticket})

# passenger self-cancellation
def cancel_booking_passenger(request, pnr):
    if request.method == 'POST':
        ticket = get_object_or_404(Ticket, pnr_number=pnr)

        if ticket.ticket_status in [Ticket.TicketStatus.RESERVED, Ticket.TicketStatus.CONFIRMED]:
            ticket.ticket_status = Ticket.TicketStatus.CANCELLED_BY_PASSENGER
            
            if ticket.payment_status == Ticket.PaymentStatus.PAID_ONLINE:
                ticket.payment_status = Ticket.PaymentStatus.REFUND_REQUESTED
                refund_mode = 'ONLINE_REFUND_QUEUE'
                
            elif ticket.payment_status == Ticket.PaymentStatus.PAID_TERMINAL:
                ticket.payment_status = Ticket.PaymentStatus.REFUND_REQUESTED
                refund_mode = 'CASH_REFUND_QUEUE'
                
            else:
                ticket.payment_status = Ticket.PaymentStatus.CANCELLED
                refund_mode = None

            ticket.save()
            send_smart_cancellation_email(ticket, "You initiated a cancellation from the online tracking portal.", refund_type=refund_mode)
            messages.success(request, f"Reservation {pnr} cancelled successfully.")
        else:
            messages.warning(request, "This reservation is already inactive or has been processed.")
            
        return redirect('track_booking')
    return redirect('home')

# staff login
def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard') 
    else:
        form = AuthenticationForm()
        
    return render(request, 'userlogin.html', {'form': form})

@login_required(login_url='/employee/login/')
def dashboard_view(request):
    return render(request, 'dashboard.html')

def user_logout(request):
    logout(request)
    return redirect('home')

# terminal master manifest
@login_required(login_url='/employee/login/')
def view_bookings(request):
    # handle 1-click status updates
    if request.method == 'POST':
        ticket_id = request.POST.get('ticket_id')
        action = request.POST.get('action')
        
        if ticket_id and action:
            t = get_object_or_404(Ticket, id=ticket_id)

            if action == 'mark_paid':
                if 'CANCELLED' in t.ticket_status:
                    messages.error(request, f"Action Blocked: PNR {t.pnr_number} was previously cancelled and cannot be marked paid.")
                else:
                    t.payment_status = Ticket.PaymentStatus.PAID_TERMINAL
                    t.ticket_status = Ticket.TicketStatus.CONFIRMED
                    t.save()
                    send_booking_confirmation(t)
                    messages.success(request, f"PNR {t.pnr_number} confirmed — Cash collected at counter.")

            elif action == 'mark_paid_online':
                if 'CANCELLED' in t.ticket_status:
                    messages.error(request, f"Action Blocked: PNR {t.pnr_number} is cancelled and cannot be confirmed.")
                else:
                    t.payment_status = Ticket.PaymentStatus.PAID_ONLINE
                    t.ticket_status = Ticket.TicketStatus.CONFIRMED
                    t.save()
                    send_booking_confirmation(t)
                    messages.success(request, f"PNR {t.pnr_number} confirmed — Online bank transfer verified.")

            elif action == 'process_refund':
                t.payment_status = Ticket.PaymentStatus.REFUNDED
                t.save()
                send_smart_cancellation_email(t, "Refund approved and processed by terminal accounting.", refund_type='INSTANT_CASH_REFUNDED')
                messages.success(request, f"PNR {t.pnr_number} ledger closed — Refund processed.")

        return redirect('view_bookings')

    query = request.GET.get('q', '').strip()
    
    if query and 'status' not in request.GET:
        status_filter = 'all'
    else:
        status_filter = request.GET.get('status', 'active')
    
    tickets = Ticket.objects.all().order_by('-id')

    # global search across multiple fields
    if query:
        tickets = tickets.filter(
            models.Q(pnr_number__icontains=query) |
            models.Q(passenger_cnic__icontains=query) |
            models.Q(passenger_name__icontains=query) |
            models.Q(passenger_phone__icontains=query)
        )

    # status tab filters
    if status_filter == 'active':
        tickets = tickets.exclude(ticket_status__in=[Ticket.TicketStatus.CANCELLED_BY_PASSENGER, Ticket.TicketStatus.CANCELLED_BY_COMPANY])
    elif status_filter == 'cancelled':
        tickets = tickets.filter(ticket_status__in=[Ticket.TicketStatus.CANCELLED_BY_PASSENGER, Ticket.TicketStatus.CANCELLED_BY_COMPANY])
    elif status_filter == 'pending_payment':
        tickets = tickets.filter(
            models.Q(payment_status=Ticket.PaymentStatus.PENDING_TERMINAL) |
            models.Q(payment_status=Ticket.PaymentStatus.PENDING_ONLINE)
        ).exclude(ticket_status__in=[Ticket.TicketStatus.CANCELLED_BY_PASSENGER, Ticket.TicketStatus.CANCELLED_BY_COMPANY])
    elif status_filter == 'refund_requested':
        tickets = tickets.filter(payment_status=Ticket.PaymentStatus.REFUND_REQUESTED)

    return render(request, 'booking_list.html', {
        'tickets': tickets, 'query': query, 'status_filter': status_filter
    })

# edit passenger details
@login_required(login_url='/employee/login/')
def edit_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)

    # prevent direct url edits for cancelled tickets
    if 'CANCELLED' in ticket.ticket_status:
        messages.error(request, f"Security Alert: PNR {ticket.pnr_number} is cancelled. Historical audit records cannot be modified!")
        return redirect('view_bookings')

    if request.method == 'POST':
        form = TicketForm(request.POST, instance=ticket)
        if form.is_valid():
            form.save()
            messages.success(request, f"Booking details for PNR {ticket.pnr_number} updated successfully.")
            return redirect('view_bookings')
    else:
        form = TicketForm(instance=ticket)

    return render(request, 'edit_ticket.html', {'form': form, 'ticket': ticket})

# staff cancellation logic
@login_required(login_url='/employee/login/')
def delete_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)

    if request.method == 'POST':
        ticket.ticket_status = Ticket.TicketStatus.CANCELLED_BY_COMPANY

        if ticket.payment_status == Ticket.PaymentStatus.PAID_ONLINE:
            ticket.payment_status = Ticket.PaymentStatus.REFUND_REQUESTED
            refund_mode = 'ONLINE_REFUND_QUEUE'
            
        elif ticket.payment_status == Ticket.PaymentStatus.PAID_TERMINAL:
            ticket.payment_status = Ticket.PaymentStatus.REFUNDED
            refund_mode = 'INSTANT_CASH_REFUNDED'
            
        else:
            ticket.payment_status = Ticket.PaymentStatus.CANCELLED
            refund_mode = None

        ticket.save()
        send_smart_cancellation_email(ticket, "Trip schedule adjusted or cancelled by terminal management.", refund_type=refund_mode)
        messages.success(request, f"PNR {ticket.pnr_number} cancelled by management.")
        return redirect('view_bookings')

    return render(request, 'delete_ticket.html', {'ticket': ticket})