from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import requests
import json
import os
import re
import io
import zipfile
from datetime import datetime, timedelta
from urllib.parse import urlparse
import mimetypes
import pytz
import threading
import time

app = Flask(__name__)
CORS(app)

# Your API token
API_TOKEN = "5ae60cb46979c92bc6454e41ff94ab44a6ffb2d9fca6f4c7afa30fcaf7d05a47"

# Cache file
CACHE_FILE = "posts_cache.json"
SPECIAL_PROFILES_FILE = "special_profiles.json"

# Timezone
TIMEZONE = pytz.timezone('Africa/Nairobi')

# ============================================================
# KEEP ALIVE - Prevents server from sleeping
# ============================================================
class KeepAlive:
    def __init__(self):
        self.running = True
    
    def start(self):
        """Start keep-alive thread"""
        def keep_alive():
            while self.running:
                try:
                    # Ping the health endpoint every 30 seconds
                    time.sleep(30)
                    with app.test_client() as client:
                        response = client.get('/health')
                        if response.status_code == 200:
                            print(f"💓 Keep-alive ping at {datetime.now().strftime('%I:%M:%S %p EAT')}")
                except Exception as e:
                    print(f"⚠️ Keep-alive error: {e}")
        
        thread = threading.Thread(target=keep_alive, daemon=True)
        thread.start()
        print("✅ Keep-alive thread started (pings every 30 seconds)")
    
    def stop(self):
        """Stop keep-alive thread"""
        self.running = False

# Start keep-alive
keep_alive = KeepAlive()
keep_alive.start()

# ============================================================
# Default special profiles - NO ICONS
# ============================================================
DEFAULT_SPECIAL_PROFILES = [
    {
        "id": "profile61590243822144",
        "name": "My Profile",
        "url": "https://www.facebook.com/profile.php?id=61590243822144",
        "category": "Special"
    },
    {
        "id": "unexpressedfeelings",
        "name": "Unexpressed Feelings",
        "url": "https://www.facebook.com/UnexpressedFeelings4U",
        "category": "Special"
    },
    {
        "id": "miraclebidemi",
        "name": "Miracle Bidemi Miranda",
        "url": "https://www.facebook.com/miraclebidemi.miranda",
        "category": "Special"
    },
    {
        "id": "lovequotesmedia",
        "name": "Love Quotes Media",
        "url": "https://www.facebook.com/lovequotesmedia",
        "category": "Special"
    }
]

# Hardcoded Facebook profiles - NO ICONS
FACEBOOK_PROFILES = [
    {"id": "bbcnews", "name": "BBC News", "url": "https://www.facebook.com/bbcnews", "category": "News"},
    {"id": "nasa", "name": "NASA", "url": "https://www.facebook.com/nasa", "category": "Science"},
    {"id": "nike", "name": "Nike", "url": "https://www.facebook.com/nike", "category": "Sports"},
    {"id": "natgeo", "name": "National Geographic", "url": "https://www.facebook.com/natgeo", "category": "Nature"},
    {"id": "nytimes", "name": "The New York Times", "url": "https://www.facebook.com/nytimes", "category": "News"},
    {"id": "cnn", "name": "CNN", "url": "https://www.facebook.com/cnn", "category": "News"},
    {"id": "taylorswift", "name": "Taylor Swift", "url": "https://www.facebook.com/taylorswift", "category": "Music"},
    {"id": "cristiano", "name": "Cristiano Ronaldo", "url": "https://www.facebook.com/cristiano", "category": "Sports"},
    {"id": "netflix", "name": "Netflix", "url": "https://www.facebook.com/netflix", "category": "Entertainment"},
    {"id": "marvel", "name": "Marvel", "url": "https://www.facebook.com/marvel", "category": "Entertainment"},
    {"id": "spacex", "name": "SpaceX", "url": "https://www.facebook.com/spacex", "category": "Science"},
    {"id": "tesla", "name": "Tesla", "url": "https://www.facebook.com/tesla", "category": "Technology"},
    {"id": "apple", "name": "Apple", "url": "https://www.facebook.com/apple", "category": "Technology"}
]

def load_special_profiles():
    """Load special profiles from file or use defaults"""
    if os.path.exists(SPECIAL_PROFILES_FILE):
        try:
            with open(SPECIAL_PROFILES_FILE, 'r') as f:
                return json.load(f)
        except:
            return DEFAULT_SPECIAL_PROFILES.copy()
    return DEFAULT_SPECIAL_PROFILES.copy()

def save_special_profiles(profiles):
    """Save special profiles to file"""
    with open(SPECIAL_PROFILES_FILE, 'w') as f:
        json.dump(profiles, f, indent=2)

def format_number(value):
    """Safely format numbers"""
    if value is None:
        return "0"
    if isinstance(value, (int, float)):
        return f"{value:,}"
    return str(value)

def parse_time_to_datetime(time_str):
    """Parse time string to datetime object for sorting"""
    try:
        if time_str and time_str != "N/A":
            if 'T' in str(time_str):
                clean_time = str(time_str).replace('Z', '+00:00')
                dt = datetime.fromisoformat(clean_time)
                return dt.replace(tzinfo=pytz.UTC)
    except Exception as e:
        print(f"Parse error: {e}")
    return None

def format_time_eat(time_str):
    """Convert time to Nairobi (EAT) timezone and format as 12-hour with AM/PM"""
    try:
        if time_str and time_str != "N/A":
            if 'T' in str(time_str):
                clean_time = str(time_str).replace('Z', '+00:00')
                dt = datetime.fromisoformat(clean_time)
                dt_utc = dt.replace(tzinfo=pytz.UTC)
                dt_eat = dt_utc.astimezone(TIMEZONE)
                return dt_eat.strftime("%I:%M %p EAT")
            else:
                return time_str
    except Exception as e:
        print(f"Time conversion error: {e}")
        return time_str
    return time_str

def get_relative_time(time_str):
    """Convert time to relative format"""
    try:
        if time_str and time_str != "N/A":
            if 'T' in str(time_str):
                clean_time = str(time_str).replace('Z', '+00:00')
                dt = datetime.fromisoformat(clean_time)
                dt_utc = dt.replace(tzinfo=pytz.UTC)
                dt_eat = dt_utc.astimezone(TIMEZONE)
                
                now = datetime.now(TIMEZONE)
                diff = now - dt_eat
                
                seconds = diff.total_seconds()
                minutes = int(seconds // 60)
                hours = int(minutes // 60)
                days = int(hours // 24)
                weeks = int(days // 7)
                months = int(days // 30)
                years = int(days // 365)
                
                if seconds < 60:
                    return "Just now"
                elif minutes < 60:
                    return f"{minutes}m ago"
                elif hours < 24:
                    return f"{hours}h ago"
                elif days < 7:
                    return f"{days}d ago"
                elif weeks < 4:
                    return f"{weeks}w ago"
                elif months < 12:
                    return f"{months}mo ago"
                else:
                    return f"{years}y ago"
    except Exception as e:
        print(f"Relative time error: {e}")
        return ""
    return ""

def is_valid_post_image(url):
    """Check if a URL is a real post image"""
    if not url or not isinstance(url, str):
        return False
    
    url_lower = url.lower()
    
    if 'ctp=s1080x1350' in url_lower:
        return True
    if 'ctp=s640x640' in url_lower:
        return True
    if 'ctp=s960x960' in url_lower:
        return True
    if '_nc_sid=127cfc' in url_lower:
        return True
    
    if 'fbcdn.net' in url_lower:
        if 'ctp=s80x80' in url_lower:
            return False
        if '_nc_sid=2d3e12' in url_lower:
            return False
        if 'ctp=s64x64' in url_lower:
            return False
        if '_nc_sid=e99d92' in url_lower:
            return False
        if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return True
        if 'ctp=s' in url_lower:
            return True
    
    return False

def extract_image_urls(post):
    """Extract image URLs from a post"""
    all_image_urls = []
    
    def add_url(url):
        if url and isinstance(url, str):
            if url.startswith('{"uri":"'):
                try:
                    parsed = json.loads(url)
                    url = parsed.get('uri', url)
                except:
                    pass
            if url.startswith('http'):
                if url not in all_image_urls:
                    all_image_urls.append(url)
    
    values = post.get("values", {})
    photo_image = values.get("photo_image")
    if photo_image:
        add_url(photo_image)
    
    details = post.get("details", {})
    media = details.get("media", [])
    if media and isinstance(media, list):
        for item in media:
            if isinstance(item, dict):
                for field in ['uri', 'image', 'url', 'src', 'thumbnail']:
                    if field in item and item[field]:
                        add_url(item[field])
    
    images_field = details.get("images", [])
    if images_field and isinstance(images_field, list):
        for img in images_field:
            if isinstance(img, str):
                add_url(img)
            elif isinstance(img, dict):
                for key in ['uri', 'url', 'src']:
                    if key in img and img[key]:
                        add_url(img[key])
    
    if not all_image_urls:
        post_str = json.dumps(post)
        patterns = [
            r'https://[^"]*\.fbcdn\.net[^"]*ctp=s1080x1350[^"]*',
            r'https://[^"]*\.fbcdn\.net[^"]*ctp=s640x640[^"]*',
            r'https://[^"]*\.fbcdn\.net[^"]*ctp=s960x960[^"]*',
            r'https://[^"]*\.fbcdn\.net[^"]*_nc_sid=127cfc[^"]*',
            r'https://[^"]*\.fbcdn\.net[^"]*[^"]*\.(jpg|jpeg|png|gif|webp)[^"]*',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, post_str, re.IGNORECASE)
            for url in matches:
                add_url(url)
    
    filtered_images = [url for url in all_image_urls if is_valid_post_image(url)]
    
    if len(filtered_images) == 0 and len(all_image_urls) > 0:
        for url in all_image_urls:
            if 's1080x1350' in url or 's640x640' in url:
                filtered_images.append(url)
                break
        if not filtered_images:
            filtered_images = all_image_urls[:1]
    
    return filtered_images

def download_image_with_retry(url, max_retries=3):
    """Download an image with retry logic"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.facebook.com/',
        'Connection': 'keep-alive',
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30, stream=True)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' in content_type:
                    if attempt < max_retries - 1:
                        continue
                    else:
                        headers['Accept'] = 'image/jpeg,image/png,image/webp'
                        continue
                if any(img_type in content_type for img_type in ['image/', 'application/octet-stream']):
                    return response.content, content_type
                else:
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return None, None
            else:
                if attempt < max_retries - 1:
                    continue
                else:
                    return None, None
        except Exception as e:
            if attempt < max_retries - 1:
                continue
            else:
                return None, None
    
    return None, None

def get_file_extension(content_type, url):
    """Get file extension from content-type or URL"""
    if content_type:
        if 'png' in content_type:
            return 'png'
        elif 'gif' in content_type:
            return 'gif'
        elif 'webp' in content_type:
            return 'webp'
        elif 'jpeg' in content_type or 'jpg' in content_type:
            return 'jpg'
    if url:
        parsed = urlparse(url)
        path = parsed.path
        if '.' in path:
            ext = path.split('.')[-1].split('?')[0].lower()
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'ico']:
                return ext
    return 'jpg'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/profiles')
def get_profiles():
    """Get all profiles including special ones"""
    special_profiles = load_special_profiles()
    return jsonify({
        "success": True,
        "profiles": FACEBOOK_PROFILES,
        "special_profiles": special_profiles
    })

@app.route('/api/special-profiles', methods=['GET', 'POST'])
def handle_special_profiles():
    """Get or add special profiles"""
    if request.method == 'GET':
        return jsonify({
            "success": True,
            "special_profiles": load_special_profiles()
        })
    elif request.method == 'POST':
        data = request.json
        special_profiles = load_special_profiles()
        
        new_profile = {
            "id": data.get('id', f"special_{len(special_profiles)}"),
            "name": data.get('name', 'New Special Profile'),
            "url": data.get('url'),
            "category": "Special"
        }
        
        if not new_profile['url']:
            return jsonify({"success": False, "error": "URL is required"}), 400
        
        for p in special_profiles:
            if p['url'] == new_profile['url']:
                return jsonify({"success": False, "error": "Profile already exists"}), 400
        
        special_profiles.append(new_profile)
        save_special_profiles(special_profiles)
        
        return jsonify({
            "success": True,
            "message": "Special profile added successfully",
            "profile": new_profile
        })

@app.route('/api/special-profiles/<profile_id>', methods=['DELETE'])
def delete_special_profile(profile_id):
    """Delete a special profile"""
    special_profiles = load_special_profiles()
    special_profiles = [p for p in special_profiles if p['id'] != profile_id]
    save_special_profiles(special_profiles)
    return jsonify({
        "success": True,
        "message": "Profile deleted successfully"
    })

@app.route('/api/posts', methods=['POST'])
def get_posts():
    data = request.json
    page_url = data.get('page_url', 'https://www.facebook.com/bbcnews')
    limit = data.get('limit', 3)
    force_refresh = data.get('force_refresh', False)
    
    if limit < 1:
        limit = 1
    if limit > 9:
        limit = 9
    
    print(f"📰 Fetching fresh posts for {page_url} (limit: {limit})")
    
    url = "https://api.socialapis.io/facebook/pages/posts"
    headers = {"x-api-token": API_TOKEN}
    params = {
        "link": page_url,
        "limit": limit
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            meta = result.get('meta', {})
            posts_data = result.get("data", {})
            posts = posts_data.get("posts", [])
            
            if not posts:
                return jsonify({
                    "success": False,
                    "error": "No posts found for this page."
                }), 404
            
            formatted_posts = []
            for post in posts:
                details = post.get("details", {})
                values = post.get("values", {})
                reactions = post.get("reactions", {})
                
                publish_time = values.get("publish_time", "N/A")
                
                dt_obj = parse_time_to_datetime(publish_time)
                formatted_time = format_time_eat(publish_time)
                relative_time = get_relative_time(publish_time)
                
                image_urls = extract_image_urls(post)
                
                formatted_post = {
                    "id": details.get("post_id", "N/A"),
                    "text": values.get("text", "No text"),
                    "time": formatted_time,
                    "relative_time": relative_time,
                    "datetime_obj": dt_obj,
                    "media_type": values.get("is_media", ""),
                    "reactions": {k: v for k, v in reactions.items() if k != "total_reaction_count" and v > 0},
                    "total_reactions": reactions.get("total_reaction_count", 0),
                    "comments": format_number(details.get("comments_count", "0")),
                    "shares": format_number(details.get("share_count", "0")),
                    "post_link": details.get("post_link", ""),
                    "images": image_urls
                }
                formatted_posts.append(formatted_post)
            
            # Sort by datetime_obj (newest first)
            formatted_posts.sort(key=lambda x: x.get('datetime_obj') or datetime.min, reverse=True)
            
            print(f"✅ Fetched {len(formatted_posts)} recent posts")
            
            return jsonify({
                "success": True,
                "posts": formatted_posts,
                "credits_used": meta.get('creditsCharged', 0),
                "credits_remaining": meta.get('creditsRemaining', 0),
                "total_posts": len(formatted_posts),
                "cached": False
            })
        else:
            error_msg = f"API returned status {response.status_code}"
            try:
                error_data = response.json()
                if "message" in error_data:
                    error_msg = error_data["message"]
                elif "error" in error_data:
                    error_msg = error_data["error"]
            except:
                pass
            
            return jsonify({
                "success": False,
                "error": f"API Error: {error_msg}"
            }), response.status_code
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/download-single-image', methods=['POST'])
def download_single_image():
    data = request.json
    image_url = data.get('image_url')
    filename = data.get('filename', 'image')
    
    if not image_url:
        return jsonify({"success": False, "error": "No image URL provided"}), 400
    
    print(f"📥 Downloading single image: {filename}")
    print(f"  🔗 {image_url[:100]}...")
    
    image_data, content_type = download_image_with_retry(image_url)
    
    if image_data:
        ext = get_file_extension(content_type, image_url)
        final_filename = f"{filename}.{ext}"
        print(f"  ✅ Downloaded ({len(image_data)} bytes) as {ext}")
        return send_file(
            io.BytesIO(image_data),
            mimetype=content_type or f'image/{ext}',
            as_attachment=True,
            download_name=final_filename
        )
    else:
        print(f"  ❌ Failed to download")
        return jsonify({
            "success": False,
            "error": "Failed to download image"
        }), 500

@app.route('/api/download-images', methods=['POST'])
def download_images():
    data = request.json
    posts = data.get('posts', [])
    page_name = data.get('page_name', 'facebook-posts')
    
    if not posts:
        return jsonify({"success": False, "error": "No posts provided"}), 400
    
    print(f"📥 Downloading images from {len(posts)} posts")
    
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        image_count = 0
        failed_count = 0
        
        for post_idx, post in enumerate(posts, 1):
            images = post.get('images', [])
            print(f"\n📦 Post {post_idx}: {len(images)} images found")
            
            if not images:
                zip_file.writestr(
                    f"post_{post_idx}/no_images.txt",
                    f"This post has no images.\nPost text: {post.get('text', 'No text')[:200]}"
                )
                continue
            
            folder_name = f"post_{post_idx}"
            post_info = f"Post {post_idx}\n"
            post_info += f"=" * 50 + "\n"
            post_info += f"Time: {post.get('time', 'N/A')}\n"
            post_info += f"Relative: {post.get('relative_time', '')}\n"
            post_info += f"Text: {post.get('text', 'No text')}\n\n"
            post_info += f"Reactions: {post.get('total_reactions', 0)}\n"
            post_info += f"Comments: {post.get('comments', 0)}\n"
            post_info += f"Shares: {post.get('shares', 0)}\n"
            post_info += f"Images found: {len(images)}\n"
            post_info += f"=" * 50 + "\n\n"
            post_info += "Image URLs:\n"
            for idx, img_url in enumerate(images, 1):
                post_info += f"  {idx}. {img_url}\n"
            
            zip_file.writestr(f"{folder_name}/post_info.txt", post_info)
            
            for img_idx, img_url in enumerate(images, 1):
                try:
                    print(f"  📥 Downloading image {img_idx}/{len(images)}...")
                    image_data, content_type = download_image_with_retry(img_url)
                    
                    if image_data:
                        ext = get_file_extension(content_type, img_url)
                        filename = f"{folder_name}/image_{img_idx}.{ext}"
                        zip_file.writestr(filename, image_data)
                        image_count += 1
                        print(f"    ✅ Downloaded ({len(image_data)} bytes) as {ext}")
                    else:
                        failed_count += 1
                        print(f"    ❌ Failed to download")
                        zip_file.writestr(
                            f"{folder_name}/image_{img_idx}_url.txt",
                            f"Image URL (could not download):\n{img_url}"
                        )
                except Exception as e:
                    failed_count += 1
                    print(f"    ❌ Error: {str(e)}")
                    zip_file.writestr(
                        f"{folder_name}/image_{img_idx}_error.txt",
                        f"Error downloading: {img_url}\nError: {str(e)}"
                    )
        
        summary = "📊 Download Summary\n"
        summary += "=" * 60 + "\n"
        summary += f"Page: {page_name}\n"
        summary += f"Posts processed: {len(posts)}\n"
        summary += f"Images downloaded: {image_count}\n"
        summary += f"Failed downloads: {failed_count}\n"
        summary += f"Download Date: {datetime.now().astimezone(TIMEZONE).strftime('%I:%M %p EAT - %B %d, %Y')}\n"
        summary += "=" * 60 + "\n\n"
        
        zip_file.writestr("summary.txt", summary)
    
    zip_buffer.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{page_name}_images_{timestamp}.zip"
    
    print(f"\n✅ ZIP created with {image_count} images ({failed_count} failed)")
    
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        return jsonify({"success": True, "message": "Cache cleared"})
    return jsonify({"success": True, "message": "No cache to clear"})

@app.route('/health')
def health():
    """Health check endpoint for keep-alive"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().astimezone(TIMEZONE).strftime('%I:%M %p EAT - %B %d, %Y'),
        "version": "1.0.0",
        "uptime": "running"
    })

@app.route('/ping')
def ping():
    """Simple ping endpoint"""
    return "pong"

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    
    # Production settings - no debug, no reloader
    print("🚀 Starting Facebook Post Viewer (Production Mode)")
    print("=" * 50)
    print(f"⏰ Timezone: East Africa Time (EAT) - Nairobi, Kenya")
    print(f"📅 Current EAT: {datetime.now().astimezone(TIMEZONE).strftime('%I:%M %p EAT - %B %d, %Y')}")
    print(f"🔌 Port: {port}")
    print("💓 Keep-alive: Enabled (pings every 30 seconds)")
    print("📰 Showing newest posts first (most recent at top)")
    print("=" * 50)
    
    # Run with production settings
    app.run(
        debug=False,           # Disable debug mode
        host='0.0.0.0',        # Listen on all interfaces
        port=port,
        threaded=True,         # Enable threading
        use_reloader=False     # Disable auto-reloader
    )