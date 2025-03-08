from django.shortcuts import render,redirect
from django.contrib.auth.models import User, auth
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.conf import settings
import random
import time
from django.utils.timezone import now
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from detection_script import start_detection, stop_detection, is_running, detect_frame
from django.http import StreamingHttpResponse
from .models import DetectionRecord, ContactMessage
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth import update_session_auth_hash


# Create your views here.

def home(request):
    return render(request, 'home.html')

def login(request):
    if request.method=='POST':
        c_email=request.POST.get('user_email')
        c_password=request.POST.get('user_password')
        user=auth.authenticate(username=c_email,password=c_password)
        if user is not None:
            auth.login(request,user)
            #messages.success(request,"Login Successfull")
            return redirect('/landing')
        else:
            messages.error(request, "Invalid credentials !")
            return render(request, "login.html", {
                "user_email": c_email,
                "user_password": c_password,
            })
        
    return render(request,'login.html')

# Store OTPs temporarily (use cache or DB for production)
otp_storage = {}

def register(request):
    if request.method=='POST':
        c_Name=request.POST['user_name']
        c_Email=request.POST['user_email']
        password1=request.POST['password1']
        password2=request.POST['password2']
        if password2==password1:
            if User.objects.filter(username=c_Email).exists():
                messages.error(request, "Email already taken !")
                return render(request, "register.html", {
                    "user_name": c_Name,
                    "user_email": c_Email,
                    "password1": password1,
                    "password2":password2
                })

            else:
                # Generate OTP
                otp = random.randint(100000, 999999)
                expiry_time = now() + timedelta(minutes=2)  # OTP valid for 1 min
                otp_storage[c_Email] = {"otp": otp, "expires_at": expiry_time}

                email_subject='WildEye Registration OTP'
                email_message=f'Your OTP code is {otp}. Do not share it with anyone. OTP is valid only for 60 seconds. Do not reply to this mail.'

                # Send OTP via email
                send_mail(
                    email_subject,
                    email_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [c_Email],
                    fail_silently=False
                )

                # Redirect to OTP verification page
                request.session['registration_data'] = {
                    "user_name": c_Name,
                    "user_email": c_Email,
                    "password1": password1
                }
                return redirect('verify_otp')
        
        else:
            messages.error(request, "Password doesn't matches !")
            return render(request, "register.html", {
                "user_name": c_Name,
                "user_email": c_Email,
                "password1": password1,
                "password2":password2
            })

    return render(request, 'register.html')

def verify_otp(request):
    if request.method == 'POST':
        email = request.session.get('registration_data', {}).get('user_email')
        entered_otp = request.POST['otp']
        
        if not email or email not in otp_storage:
            messages.error(request, "Invalid request.")
            return redirect('/register')
        
        stored_otp_data = otp_storage.get(email)

        # Check if OTP has expired
        if now() > stored_otp_data["expires_at"]:
            del otp_storage[email]  # Remove expired OTP
            messages.error(request, "OTP has expired. Please request a new one.")
            return redirect('verify_otp')

        # Validate OTP
        if stored_otp_data["otp"] == int(entered_otp):
            # Create user
            data = request.session.get('registration_data')
            user = User.objects.create_user(username=data['user_email'], email=data['user_email'], password=data['password1'], first_name=data['user_name'])
            user.save()

            # Clean up session and OTP
            del otp_storage[email]
            del request.session['registration_data']

            #messages.success(request, "Registration successful! You can now log in.")
            return redirect('/login')
        else:
            messages.error(request, "Invalid OTP. Try again.")

    return render(request, 'otp.html')

def resend_otp(request):
    email = request.session.get('registration_data', {}).get('user_email')

    if email:
        # Generate new OTP
        otp = random.randint(100000, 999999)
        expiry_time = now() + timedelta(minutes=2)  # OTP valid for 1 min
        otp_storage[email] = {"otp": otp, "expires_at": expiry_time}

        # Send OTP via email
        email_subject = 'WildEye Registration OTP - Resend'
        email_message = f'Your new OTP code is {otp}. Do not share it with anyone. OTP is valid only for 60 seconds. Do not reply to this mail.'

        send_mail(
            email_subject,
            email_message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False
        )

        #messages.success(request, "A new OTP has been sent to your email.")
    else:
        messages.error(request, "Invalid request. Please register again.")
        return redirect('/register')

    return redirect('verify_otp')



@login_required(login_url='/')
def landing(request):
    return render(request, 'landing.html')

def otp(request):
    return render(request,'otp.html')


#FORGOT PASSWORD
#===============

reset_otp_storage = {}

def forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        
        # Check if user exists
        if not User.objects.filter(email=email).exists():
            messages.error(request, "No account found with this email.")
            return render(request, "forgot_password.html", {"email": email})

        # Generate OTP
        otp = random.randint(100000, 999999)
        expiry_time = now() + timedelta(minutes=2)  # OTP valid for 1 min
        reset_otp_storage[email] = {"otp": otp, "expires_at": expiry_time}

        # Send OTP email
        email_subject = 'WildEye Password Reset OTP'
        email_message = f'Your OTP code is {otp}. Do not share it with anyone. OTP is valid only for 60 seconds. Do not reply to this mail.'

        send_mail(
            email_subject,
            email_message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False
        )

        request.session['reset_email'] = email  # Store email in session
        return redirect('verify_reset_otp')

    return render(request, 'forgot_password.html')

def verify_reset_otp(request):
    if request.method == 'POST':
        email = request.session.get('reset_email')
        entered_otp = request.POST.get('otp')

        if not email or email not in reset_otp_storage:
            messages.error(request, "Invalid request.")
            return redirect('forgot_password')

        stored_otp_data = reset_otp_storage.get(email)

        # Check if OTP has expired
        if now() > stored_otp_data["expires_at"]:
            del reset_otp_storage[email]  # Remove expired OTP
            messages.error(request, "OTP has expired. Please request a new one.")
            return redirect('verify_reset_otp')

        # Validate OTP
        if stored_otp_data["otp"] == int(entered_otp):
            del reset_otp_storage[email]  # Remove OTP after successful validation
            return redirect('reset_password')
        else:
            messages.error(request, "Invalid OTP. Try again.")

    return render(request, 'reset_otp.html')

def reset_password(request):
    email = request.session.get('reset_email')

    if not email:
        messages.error(request, "Session expired. Please try again.")
        return redirect('forgot_password')

    if request.method == 'POST':
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, "reset_password.html")

        # Update user password
        user = User.objects.get(email=email)
        user.set_password(password1)
        user.save()

        del request.session['reset_email']  # Remove session data
        #messages.success(request, "Password reset successful. You can now log in.")
        return redirect('/')

    return render(request, 'reset_password.html')

def forgot_resend_otp(request):
    email = request.session.get('reset_email')

    if email:
        # Generate new OTP
        otp = random.randint(100000, 999999)
        expiry_time = now() + timedelta(minutes=2)  # OTP valid for 1 min
        reset_otp_storage[email] = {"otp": otp, "expires_at": expiry_time}

        # Send OTP via email
        email_subject = 'WildEye Password Reset OTP - Resend'
        email_message = f'Your new OTP code is {otp}. Do not share it with anyone. OTP is valid only for 60 seconds. Do not reply to this mail.'

        send_mail(
            email_subject,
            email_message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False
        )
        #messages.success(request, "A new OTP has been sent to your email.")
    else:
        messages.error(request, "Invalid request. Please try again.")
        return redirect('forgot_password')

    return redirect('verify_reset_otp')




"""
YOLO Part
"""
# Helper function to check if the user is a superuser
def is_superuser(user):
    return user.is_authenticated and user.is_superuser

@user_passes_test(is_superuser, login_url='/')
def yolo(request):
    return render(request,'yolo.html')

# Global variable to store detection state (replace with DB if needed)
detection_running = False

@csrf_exempt
def start_detection_view(request):
    global detection_running
    if request.method == "POST":
        if not detection_running:
            detection_running = True  # Set state to running
            start_detection()
            return JsonResponse({"status": "Running"})
        return JsonResponse({"status": "Already running"})

@csrf_exempt
def stop_detection_view(request):
    global detection_running
    if request.method == "POST":
        detection_running = False  # Set state to stopped
        stop_detection()
        return JsonResponse({"status": "Stopped"})

@csrf_exempt
def get_detection_status(request):
    """ API to get the current detection state """
    return JsonResponse({"status": "Running" if detection_running else "Stopped"})


#Custom admin

def custom_admin(request):
    if request.method=='POST':
        c_user=request.POST.get('user_name')
        c_password=request.POST.get('user_password')
        user=auth.authenticate(username=c_user,password=c_password)
        if user is not None and user.is_superuser:
            auth.login(request,user)
            #messages.success(request,"Login Successfull")
            return redirect('/yolo')
        else:
            messages.error(request, "Invalid credentials !")
            return render(request, "admin_login.html", {
                "user_name": c_user,
                "user_password": c_password,
            })
    return render(request,'admin_login.html') 



@user_passes_test(is_superuser, login_url='/')  # Redirect to home if unauthorized
def admin_cards(request):
    records = DetectionRecord.objects.all().order_by('-date', '-time')  # Fetch all records
    return render(request, 'admin_cards.html', {'records': records})

@user_passes_test(is_superuser, login_url='/')
def message_cards(request):
    messages = ContactMessage.objects.all().order_by('-submitted_at')  # Fetch all records
    return render(request, 'message_cards.html', {'messages': messages})

@csrf_exempt
def delete_message(request, record_id):
    if request.method == "DELETE":
        try:
            record = ContactMessage.objects.get(id=record_id)
            record.delete()
            return JsonResponse({"success": True})
        except ContactMessage.DoesNotExist:
            return JsonResponse({"success": False, "error": "Record not found"})
    return JsonResponse({"success": False, "error": "Invalid request"})

@csrf_exempt
def delete_record(request, record_id):
    if request.method == "DELETE":
        try:
            record = DetectionRecord.objects.get(id=record_id)
            record.delete()
            return JsonResponse({"success": True})
        except DetectionRecord.DoesNotExist:
            return JsonResponse({"success": False, "error": "Record not found"})
    return JsonResponse({"success": False, "error": "Invalid request"})

@user_passes_test(is_superuser, login_url='/')
def admin_table(request):
    records = DetectionRecord.objects.all()  # Fetch all records
    return render(request, 'admin_table.html', {'records': records})

@login_required(login_url='/')
def user_table(request):
    records = DetectionRecord.objects.all()  # Fetch all records
    return render(request, 'user_table.html', {'records': records})

@login_required(login_url='/')
def user_cards(request):
    records = DetectionRecord.objects.all()  # Fetch all records
    return render(request, 'user_cards.html', {'records': records})


#common urls
def about(request):
    return render(request, 'about.html')

def services(request):
    return render(request, 'services.html')

def team(request):
    return render(request, 'team.html')

def terms(request):
    return render(request, 'terms.html')

def contact(request):
    if request.method=='POST':
        Name=request.POST['name']
        Email=request.POST['email']
        Phone=request.POST['phone']
        Message=request.POST['message']
        # Save the contact message in the database
        ContactMessage.objects.create(
            name=Name,
            email=Email,
            phone=Phone,
            message=Message
        )
        # Show a success message
        messages.success(request, "Your message has been sent successfully!")
        return redirect('contact') 
    return render(request, 'contact.html')


@login_required(login_url='/')
def change_password(request):
    if request.method == "POST":
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        user = request.user

        # Check if current password is correct
        if not user.check_password(current_password):
            messages.error(request, "Current password is incorrect.")
            return redirect("change_password")

        # Check if new passwords match
        if new_password != confirm_password:
            messages.error(request, "New passwords do not match.")
            return redirect("change_password")


        # Update the password
        user.set_password(new_password)
        user.save()

        # Keep the user logged in after password change
        update_session_auth_hash(request, user)

        #messages.success(request, "Your password has been updated successfully.")
        return redirect('/login')  # Redirect to success page

    return render(request, "change_password.html")

@login_required(login_url='/')
def user_logout(request):
    auth.logout(request)  # Logs out the user
    messages.success(request, "You have been logged out successfully.")
    return redirect('/login')

@user_passes_test(is_superuser, login_url='/')
def admin_logout(request):
    auth.logout(request)  # Logs out the user
    messages.success(request, "You have been logged out successfully.")
    return redirect('/custom_admin')

@user_passes_test(is_superuser, login_url='/')
def user_list(request):
    users=User.objects.all()
    return render(request,'user_list.html',{'users':users})