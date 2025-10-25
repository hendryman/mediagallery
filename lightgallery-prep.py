#!/usr/bin/env python3

import os
import sys
import json
import subprocess
from PIL import Image

# --- Check for HEIC/HEIF support ---
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:
    HEIF_SUPPORT = False
# -----------------------------------

# --- Configuration ---
THUMB_DIR_NAME = "thumbnails"
THUMB_SIZE = (400, 400)
JSON_FILE_NAME = "-gallery.json"
SUPPORTED_IMG_EXTS = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif']
SUPPORTED_VID_EXTS = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
# ---------------------

def print_warning(message):
    """Prints a formatted warning message to stderr."""
    print(f"\033[93mWarning: {message}\033[0m", file=sys.stderr)

def print_error(message):
    """Prints a formatted error message to stderr."""
    print(f"\033[91mError: {message}\033[0m", file=sys.stderr)

def print_success(message):
    """Prints a formatted success message."""
    print(f"\033[92m{message}\033[0m")

def get_relative_path(base_path, file_path):
    """Calculates the relative path of a file from its base folder."""
    return os.path.relpath(file_path, base_path)

def create_thumbnail(file_path, thumb_dir, media_type):
    """Creates a thumbnail for an image or video file."""
    base_name = os.path.basename(file_path)
    thumb_name = f"{os.path.splitext(base_name)[0]}_thumb.jpg"
    thumb_path = os.path.join(thumb_dir, thumb_name)
    thumb_rel_path = os.path.join(THUMB_DIR_NAME, thumb_name)

    try:
        if media_type == 'image':
            img = Image.open(file_path)
            # Handle EXIF orientation data for correct rotation
            img = ImageOps.exif_transpose(img)
            img.thumbnail(THUMB_SIZE)
            # Convert to RGB if it's not (e.g., RGBA or P) to ensure saving as JPEG
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(thumb_path, 'JPEG', quality=85)
            
        elif media_type == 'video':
            # Use ffmpeg to extract the first frame as a thumbnail
            # -vf "thumbnail,scale=400:-1" is a robust way to get a good frame
            cmd = [
                'ffmpeg',
                '-i', file_path,
                '-ss', '00:00:01.000', # Grab frame at 1 second
                '-vframes', '1',
                '-vf', f'thumbnail,scale={THUMB_SIZE[0]}:-1', # Find a good frame and scale
                thumb_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print(f"  Created thumbnail: {thumb_rel_path}")
        return thumb_rel_path

    except ImportError:
        # This can happen if PIL/Pillow is not installed, though the script would fail earlier.
        print_warning(f"Python Imaging Library (Pillow) not found. Cannot create image thumbnails.")
        return None
    except (IOError, OSError) as e:
        print_warning(f"Could not create thumbnail for {file_path}. Error: {e}")
        return None
    except subprocess.CalledProcessError as e:
        print_warning(f"ffmpeg failed to create thumbnail for {file_path}. Is ffmpeg installed correctly?")
        return None
    except Exception as e:
        # Catch any other unexpected errors from PIL or ffmpeg
        print_warning(f"An unexpected error occurred during thumbnail generation for {file_path}. Error: {e}")
        return None

def get_media_dimensions(file_path, media_type):
    """Gets the width and height of an image or video file."""
    try:
        if media_type == 'image':
            with Image.open(file_path) as img:
                # Get dimensions *after* applying EXIF orientation
                img_oriented = ImageOps.exif_transpose(img)
                return img_oriented.width, img_oriented.height
                
        elif media_type == 'video':
            # Use ffprobe to get video stream dimensions as JSON
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,tags=rotate',
                '-of', 'json',
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            if not data.get('streams') or len(data['streams']) == 0:
                print_warning(f"ffprobe found no video streams for {file_path}.")
                return None, None
                
            stream = data['streams'][0]
            width = int(stream['width'])
            height = int(stream['height'])
            
            # Check for rotation tag (common in .MOV files from phones)
            rotation = stream.get('tags', {}).get('rotate')
            if rotation in ['90', '-90', '270', '-270']:
                # If rotated 90 or 270 degrees, swap width and height
                return height, width
            else:
                return width, height
            
    except subprocess.CalledProcessError as e:
        print_warning(f"Could not get dimensions for {file_path}. ffprobe failed.")
        print_error(f"ffprobe stdout: {e.stdout}")
        print_error(f"ffprobe stderr: {e.stderr}")
        return None, None
    except (IOError, OSError) as e:
        print_warning(f"Could not get dimensions for {file_path}. Error: {e}")
        return None, None
    except Exception as e:
        print_warning(f"An unexpected error occurred getting dimensions for {file_path}. Error: {e}")
        return None, None


def main(folder_path):
    if not os.path.isdir(folder_path):
        print_error(f"Error: Path '{folder_path}' is not a valid directory.")
        sys.exit(1)

    if not HEIF_SUPPORT:
        print_warning("'pillow-heif' not installed. HEIC/HEIF files may not be processed.")
        print_warning("Run: pip3 install pillow-heif")

    thumb_dir = os.path.join(folder_path, THUMB_DIR_NAME)
    
    if not os.path.exists(thumb_dir):
        os.makedirs(thumb_dir)
        print(f"Created directory: {thumb_dir}")

    gallery_items = []
    
    print(f"Walking directory: {folder_path}...")

    # Walk the directory
    for root, dirs, files in os.walk(folder_path):
        # Skip the thumbnail directory itself
        if os.path.basename(root) == THUMB_DIR_NAME:
            continue
            
        # Sort files for predictable order
        files.sort()
        
        for file in files:
            file_lower = file.lower()
            media_type = None

            if any(file_lower.endswith(ext) for ext in SUPPORTED_IMG_EXTS):
                media_type = 'image'
            elif any(file_lower.endswith(ext) for ext in SUPPORTED_VID_EXTS):
                media_type = 'video'

            # If the file is not a supported media type, skip it
            if media_type is None:
                continue

            file_path = os.path.join(root, file)
            
            print(f"Processing file: {file_path}")
            
            thumb_rel_path = create_thumbnail(file_path, thumb_dir, media_type)
            width, height = get_media_dimensions(file_path, media_type)
            
            # If either function failed, it will return None.
            # We should skip this file if that's the case.
            if thumb_rel_path is None or width is None:
                print_warning(f"Skipping {file_path} due to processing errors (e.g., corrupt file or missing dimensions).")
                continue # Skip to the next file
            
            # If we are here, both functions succeeded.
            file_name_no_ext = os.path.splitext(file)[0]
            
            gallery_items.append({
                "type": media_type,
                "full": get_relative_path(folder_path, file_path),
                "thumbnail": thumb_rel_path,
                "title": file_name_no_ext.replace('-', ' ').replace('_', ' ').title(),
                "description": f"File: {file}",
                "alt": file_name_no_ext,
                "width": width,
                "height": height
            })

    # Write the JSON file
    json_path = os.path.join(folder_path, JSON_FILE_NAME)
    try:
        with open(json_path, 'w') as f:
            json.dump(gallery_items, f, indent=4)
        print_success(f"\nSuccessfully created gallery file: {json_path}")
    except (IOError, OSError) as e:
        print_error(f"\nError writing JSON file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Import ImageOps here so the script can still run if Pillow isn't installed
    # (it will just fail gracefully on images)
    try:
        from PIL import ImageOps
    except ImportError:
        print_error("Pillow (Python Imaging Library) not found.")
        print_error("Please install it by running: pip3 install Pillow")
        sys.exit(1)

    if len(sys.argv) != 2:
        print("Usage: ./create_gallery_info.py <path_to_your_content_folder>")
        sys.exit(1)
        
    target_folder = sys.argv[1]
    main(target_folder)

