from django import forms
from .models import Ticket, Location

class RouteSearchForm(forms.Form):
    origin = forms.ModelChoiceField(
        queryset=Location.objects.all(), 
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    destination = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['trip', 'passenger_name', 'seat_number']
        widgets = {
            'trip': forms.Select(attrs={'class': 'form-select'}),
            'passenger_name': forms.TextInput(attrs={'class': 'form-control'}),
            'seat_number': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

   # Custom Validation for Seats
    def clean(self):
        cleaned_data = super().clean()
        trip = cleaned_data.get('trip')
        seat_number = cleaned_data.get('seat_number')

        if trip and seat_number:
            existing_ticket = Ticket.objects.filter(
                trip=trip, 
                seat_number=seat_number
            ).exclude(
                ticket_status__in=[
                    Ticket.TicketStatus.CANCELLED_BY_PASSENGER, 
                    Ticket.TicketStatus.CANCELLED_BY_COMPANY, 
                    Ticket.TicketStatus.CANCELLED
                ]
            )
            
            
            if self.instance and self.instance.pk:
                existing_ticket = existing_ticket.exclude(pk=self.instance.pk)

            if existing_ticket.exists():
                raise forms.ValidationError(f"Seat #{seat_number} is already occupied on {trip.route_name}! Please choose a different seat.")
                
        return cleaned_data