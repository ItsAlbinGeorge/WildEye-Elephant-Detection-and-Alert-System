import threading
import cv2
from ultralytics import YOLO
from tracker import Tracker
import random
import time
import os
import sys
import django
from datetime import datetime
from django.core.files import File
import subprocess
from collections import OrderedDict

# Add project directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "your_project.settings")
django.setup()

#  Now import settings
from django.conf import settings
from django.core.mail import EmailMessage
from django.contrib.auth.models import User
from WildEye_Portal.models import DetectionRecord

def send_email_with_photo(photo_path, detection_time_str):
    subject = "Wildlife Detection Alert"
    message = f"A detection has been made at {detection_time_str}. Please check the attached photo."

    # Retrieve all user emails
    user_emails = list(User.objects.values_list('email', flat=True))

    if not user_emails:
        print("No user emails found.")
        return

    email = EmailMessage(
        subject,
        message,
        settings.EMAIL_HOST_USER,  # Admin email from settings.py
        user_emails
    )


    # Attach the photo
    with open(photo_path, 'rb') as photo_file:
        email.attach(f'Detection_{detection_time_str}.jpg', photo_file.read(), 'image/jpeg')

    email.send()
    print(f"Email sent successfully to {', '.join(user_emails)}")



is_running = False  # Global flag to track the process

def detect_frame():
    global is_running
    is_running = True  # Set flag to running
    # Load your custom-trained YOLO model
    model = YOLO('train/weights/best.pt')

    # Load video path
    #video_path = "input/footage1.mp4"
    video_path = "input/new_test.mp4"
    cap = cv2.VideoCapture(video_path)
    #cap = cv2.VideoCapture(0)

    # Initialize tracker
    tracker = Tracker()

    # A list with 10 random colors
    colors = [(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)) for j in range(10)]

    # Read a frame from the video
    ret, frame = cap.read()

    # Get video properties
    fps = int(cap.get(cv2.CAP_PROP_FPS))  # Frames per second
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # Dictionary to store detection start times for each track ID
    detection_times = OrderedDict()

    # Dictionary to store video writers for each track ID
    video_writers = OrderedDict()

    # Dictionary to track the last frame number an object was seen
    last_seen_frame = OrderedDict()

    # Frame buffer for generating additional short videos
    initial_frame_buffers = OrderedDict()

    # Flag to indicate if a short video has been generated
    photo_generated = OrderedDict()

    # Flag to indicate if a video has been pushed
    video_pushed = OrderedDict()

    # Dictionary to track elapsed time
    elapsed = OrderedDict()

    

    # Frame counter
    frame_count = 0

    # Detection threshold
    detection_threshold = 0.5  # Adjust this to optimize the results

    # Maximum frames to consider an object as "not seen"
    max_frames_not_seen = 10
    time_limit = 50

    def get_last_track_id():
        try:
            last_record = DetectionRecord.objects.latest('track_id')
            return last_record.track_id
        except DetectionRecord.DoesNotExist:
            return 0  # If no records exist, start from 0
    
    # Ensure dictionary size does not exceed 50 items
    def maintain_dict_size(dictionary):
        if len(dictionary) > 50:
            dictionary.popitem(last=False)  # Removes the first (oldest) inserted item

    last_track_id = get_last_track_id()  # Fetch the last track_id

    while ret and is_running:
        frame_count += 1
        results = model(frame)  # Calling model

        # Current active track IDs
        active_track_ids = set()

        # Iterate through results
        for result in results:
            detections = []
            for r in result.boxes.data.tolist():
                x1, y1, x2, y2, score, class_id = r
                x1 = int(x1)
                y1 = int(y1)
                x2 = int(x2)
                y2 = int(y2)
                class_id = int(class_id)
                if score > detection_threshold:
                    detections.append([x1, y1, x2, y2, score])

            # Calling tracker
            tracker.update(frame, detections)

            # Iterate through tracks
            for track in tracker.tracks:
                bbox = track.bbox
                x1, y1, x2, y2 = bbox
                track_id = last_track_id + track.track_id
                
                # Mark this track ID as active
                active_track_ids.add(track_id)

                # Start timing and frame buffer if the object is newly detected
                if track_id not in detection_times:
                    detection_times[track_id] = time.time()
                    initial_frame_buffers[track_id] = []
                    photo_generated[track_id] = False
                    video_pushed[track_id] = False

                # Maintain only 50 elements in each dictionary
                maintain_dict_size(detection_times)
                maintain_dict_size(video_writers)
                maintain_dict_size(last_seen_frame)
                maintain_dict_size(initial_frame_buffers)
                maintain_dict_size(photo_generated)
                maintain_dict_size(video_pushed)
                maintain_dict_size(elapsed)


                # Add frame to the initial frame buffer for this track ID
                if track_id in initial_frame_buffers and len(initial_frame_buffers[track_id]) < time_limit:
                    initial_frame_buffers[track_id].append(frame.copy())

                # Update the last seen frame for this track ID
                last_seen_frame[track_id] = frame_count

                # Calculate elapsed time
                elapsed_time = time.time() - detection_times[track_id]
                elapsed[track_id] = elapsed_time
                elapsed_time_str = f"{elapsed_time:.1f}s"

                # Draw bounding box and text
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (colors[track_id % len(colors)]), 3)
                cv2.putText(frame, f"ID: {track_id}", (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                cv2.putText(frame, elapsed_time_str, (int(x1), int(y1) - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # Generate photo if elapsed time > 20 seconds
                if elapsed_time > time_limit and not photo_generated[track_id]:
                    #photo_path = f"{output_dir}/track_{track_id}_photo.jpg"
                    photo_frame = initial_frame_buffers[track_id][0]
                    # Define the new photo path inside Django's media folder
                    photo_filename = f"track_{track_id}_photo.jpg"
                    photo_path = os.path.join(settings.MEDIA_ROOT, "detections/photos", photo_filename)

                    # Ensure directory exists
                    os.makedirs(os.path.dirname(photo_path), exist_ok=True)

                    detection_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(detection_times[track_id]))
                    detection_datetime = datetime.strptime(detection_time_str, '%Y-%m-%d %H:%M:%S')

                    cv2.rectangle(photo_frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 3)
                    cv2.putText(photo_frame, f"ID: {track_id}", (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                    cv2.putText(photo_frame, f"Detected: {detection_time_str}", (int(x1), int(y2) + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
                    cv2.imwrite(photo_path, photo_frame)
                    print(f"Generated photo for track ID {track_id}: {photo_path}")
                    photo_generated[track_id] = True

                    # Save relative path in the database
                    photo_relative_path = f"detections/photos/{photo_filename}"

                    # Save detection details to the database
                    record, created = DetectionRecord.objects.get_or_create(
                        track_id=track_id,
                        defaults={
                            'date': detection_datetime.date(),
                            'time': detection_datetime.time(),
                            'photo': photo_relative_path,  # Save relative path
                            'location': "Munnar"
                        }
                    )

                    # Send email with the generated photo
                    send_email_with_photo(photo_path, detection_time_str)

                # Save frames containing specific track IDs to separate videos
                if track_id not in video_writers:
                    # Create a new video writer for this track ID
                    #output_path = f"{output_dir}/track_{track_id}.mp4"
                    video_filename = f"track_{track_id}.mp4"
                    video_path = os.path.join(settings.MEDIA_ROOT, "detections/videos", video_filename)
                    
                    # Ensure the directory exists
                    os.makedirs(os.path.dirname(video_path), exist_ok=True)
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    #video_writers[track_id] = cv2.VideoWriter(output_path, fourcc, fps, (frame_width, frame_height))
                    video_writers[track_id] = cv2.VideoWriter(video_path, fourcc, fps, (frame_width, frame_height))

                # Write the frame to the corresponding video
                video_writers[track_id].write(frame)

        # Delete videos for tracks not seen in the last 10 frames
        
        for track_id in list(last_seen_frame.keys()):
            if frame_count - last_seen_frame[track_id] > max_frames_not_seen:
                # Release and delete the video writer
                if track_id in video_writers:
                    video_writers[track_id].release()
                    del video_writers[track_id]
                    video_path = os.path.join(settings.MEDIA_ROOT, "detections/videos", f"track_{track_id}.mp4")
                    if os.path.exists(video_path):
                        if elapsed[track_id] < time_limit:
                            print(f"Video for track ID {track_id} elapsed time: {time.time() - detection_times[track_id]:.1f}s")
                            os.remove(video_path)
                            print(f"Deleted video for track ID {track_id} due to inactivity.")
                        else:
                            # Convert video to H.264 format
                            converted_video_path = os.path.join(settings.MEDIA_ROOT, "detections/videos", f"track_{track_id}_converted.mp4")
                            ffmpeg_cmd = [
                                "ffmpeg", "-y", "-i", video_path, "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                                "-c:a", "aac", "-b:a", "128k", converted_video_path
                            ]

                            # Run FFmpeg conversion
                            subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                            # Save converted video to Django database
                            if os.path.exists(converted_video_path):
                                with open(converted_video_path, 'rb') as video_file:
                                    record, created = DetectionRecord.objects.update_or_create(
                                        track_id=track_id,
                                        defaults={'video': File(video_file, name=f"track_{track_id}_pushed.mp4")}
                                    )
                                video_pushed[track_id] = True
                                os.remove(video_path)
                                os.remove(converted_video_path)  # Remove original video
                del last_seen_frame[track_id]
                del detection_times[track_id]
                if track_id in initial_frame_buffers:
                    del initial_frame_buffers[track_id]

        # Show frame
        cv2.imshow('frame', frame)
        cv2.waitKey(25)  # 25 milliseconds; adjust this value to change frame speed
        ret, frame = cap.read()
    
    # Ensure videos are saved properly if elapsed time > time_limit
    # When stopping the process, check running video writers
    for track_id in list(video_writers.keys()):
        video_writers[track_id].release()
        video_filename = f"track_{track_id}.mp4"
        video_path = os.path.join(settings.MEDIA_ROOT, "detections/videos", video_filename)
        
        if elapsed[track_id] > time_limit:
            converted_video_path = os.path.join(settings.MEDIA_ROOT, "detections/videos", f"track_{track_id}_converted.mp4")
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", video_path, "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                "-c:a", "aac", "-b:a", "128k", converted_video_path
            ]

            # Run FFmpeg conversion
            subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Save converted video to Django database
            if os.path.exists(converted_video_path):
                with open(converted_video_path, 'rb') as video_file:
                    record, created = DetectionRecord.objects.update_or_create(
                        track_id=track_id,
                        defaults={'video': File(video_file, name=f"track_{track_id}_pushed.mp4")}
                    )
                video_pushed[track_id] = True
                os.remove(converted_video_path)  # Remove original video
        os.remove(video_path)

    # Release resources
    cap.release()
    for writer in video_writers.values():
        writer.release()
    cv2.destroyAllWindows()
    is_running = False  # Reset flag

# Function to start detection
def start_detection():
    if not is_running:
        detection_thread = threading.Thread(target=detect_frame, daemon=True)
        detection_thread.start()
        return True
    return False

# Function to stop detection
def stop_detection():
    global is_running
    is_running = False
    return True
