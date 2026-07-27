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

app = Flask(__name__)
CORS(app)

# Your API token
API_TOKEN = "5ae60cb46979c92bc6454e41ff94ab44a6ffb2d9fca6f4c7afa30fcaf7d05a47"

# Cache file
CACHE_FILE = "posts_cache.json"

def format_number(value):
    """Safely format numbers"""
    if value is None:
        return "0"
    if isinstance(value, (int, float)):
        return f"{value:,}"
    return str(value)

def is_valid_post_image(url):
    """
    Check if a URL is a real post image (not profile or comment)
    Based on patterns we found in the actual data
    """
    if not url or not isinstance(url, str):
        return False
    
    url_lower = url.lower()
    
    # ✅ REAL POST IMAGES have these patterns
    if 'ctp=s1080x1350' in url_lower:
        return True
    if 'ctp=s640x640' in url_lower:
        return True
    if 'ctp=s960x960' in url_lower:
        return True
    if '_nc_sid=127cfc' in url_lower:
        return True
    if 'ctp=mx1080x1350' in url_lower and 'ctp=s1080x1350' in url_lower:
        return True
    
    # Check for any fbcdn.net image that's not a profile/comment
    if 'fbcdn.net' in url_lower:
        # ❌ PROFILE IMAGES have these patterns
        if 'ctp=s80x80' in url_lower:
            return False
        if '_nc_sid=2d3e12' in url_lower:
            return False
        if '/t39.30808-1/' in url_lower and 'ctp=s80x80' in url_lower:
            return False
        if 'stp=cp0_dst-jpg_tt6' in url_lower and 'ctp=s80x80' in url_lower:
            return False
        
        # ❌ COMMENT IMAGES have these patterns
        if 'ctp=s64x64' in url_lower:
            return False
        if '_nc_sid=e99d92' in url_lower:
            return False
        if 'ctp=s128x128' in url_lower:
            return False
        
        # If it has an image extension and not filtered, keep it
        if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return True
        
        # Also keep if it has ctp with reasonable size
        if 'ctp=s' in url_lower:
            return True
    
    return False

def extract_image_urls(post):
    """
    Extract image URLs from a post - filters out profile and comment images
    """
    all_image_urls = []
    
    # Helper to clean and add URL
    def add_url(url):
        if url and isinstance(url, str):
            # Clean up any JSON wrapper
            if url.startswith('{"uri":"'):
                try:
                    parsed = json.loads(url)
                    url = parsed.get('uri', url)
                except:
                    pass
            
            # Only add if it's a valid HTTP URL
            if url.startswith('http'):
                if url not in all_image_urls:
                    all_image_urls.append(url)
    
    # 1. Check photo_image field
    values = post.get("values", {})
    photo_image = values.get("photo_image")
    if photo_image:
        add_url(photo_image)
    
    # 2. Check media in details
    details = post.get("details", {})
    media = details.get("media", [])
    if media and isinstance(media, list):
        for item in media:
            if isinstance(item, dict):
                for field in ['uri', 'image', 'url', 'src', 'thumbnail']:
                    if field in item and item[field]:
                        add_url(item[field])
    
    # 3. Check images field
    images_field = details.get("images", [])
    if images_field and isinstance(images_field, list):
        for img in images_field:
            if isinstance(img, str):
                add_url(img)
            elif isinstance(img, dict):
                for key in ['uri', 'url', 'src']:
                    if key in img and img[key]:
                        add_url(img[key])
    
    # 4. If still no images, scan the raw data
    if not all_image_urls:
        post_str = json.dumps(post)
        
        # Look for fbcdn.net images with post patterns
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
    
    # Filter out profile and comment images
    filtered_images = [url for url in all_image_urls if is_valid_post_image(url)]
    
    # If we filtered out everything but had images, keep the first one as fallback
    if len(filtered_images) == 0 and len(all_image_urls) > 0:
        print(f"⚠️ All images filtered, keeping first as fallback")
        # Try to keep the largest/clearest image
        for url in all_image_urls:
            if 's1080x1350' in url or 's640x640' in url:
                filtered_images.append(url)
                break
        if not filtered_images:
            filtered_images = all_image_urls[:1]
    
    return filtered_images

def download_image_with_retry(url, max_retries=3):
    """Download an image with retry logic and proper headers"""
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
                # Check content type
                content_type = response.headers.get('content-type', '').lower()
                
                # If it's HTML or text, it might be a redirect or viewer page
                if 'text/html' in content_type:
                    print(f"  ⚠️ Got HTML instead of image (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        # Last attempt - try with different headers
                        headers['Accept'] = 'image/jpeg,image/png,image/webp'
                        continue
                
                # Check if it's actually an image
                if any(img_type in content_type for img_type in ['image/', 'application/octet-stream']):
                    return response.content, content_type
                else:
                    print(f"  ⚠️ Unexpected content-type: {content_type}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return None, None
            else:
                print(f"  ⚠️ HTTP {response.status_code} (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    continue
                else:
                    return None, None
                    
        except Exception as e:
            print(f"  ⚠️ Error downloading: {str(e)} (attempt {attempt + 1})")
            if attempt < max_retries - 1:
                continue
            else:
                return None, None
    
    return None, None

def get_file_extension(content_type, url):
    """Get file extension from content-type or URL"""
    # From content-type
    if content_type:
        if 'png' in content_type:
            return 'png'
        elif 'gif' in content_type:
            return 'gif'
        elif 'webp' in content_type:
            return 'webp'
        elif 'jpeg' in content_type or 'jpg' in content_type:
            return 'jpg'
    
    # From URL
    if url:
        parsed = urlparse(url)
        path = parsed.path
        if '.' in path:
            ext = path.split('.')[-1].split('?')[0].lower()
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'ico']:
                return ext
    
    return 'jpg'  # default

def get_cached_posts(page_url, limit):
    """Check if we have cached posts"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
        if cache.get("page_url") == page_url and cache.get("limit") == limit:
            cache_time = datetime.fromisoformat(cache["timestamp"])
            if datetime.now() - cache_time < timedelta(hours=24):
                return cache["posts"]
    return None

def save_to_cache(page_url, limit, posts):
    """Save posts to cache"""
    cache = {
        "timestamp": datetime.now().isoformat(),
        "page_url": page_url,
        "limit": limit,
        "posts": posts
    }
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/posts', methods=['POST'])
def get_posts():
    data = request.json
    page_url = data.get('page_url', 'https://www.facebook.com/bbcnews')
    limit = data.get('limit', 3)
    force_refresh = data.get('force_refresh', False)
    
    # Enforce API limits: min 3, max 9
    if limit < 3:
        limit = 3
    if limit > 9:
        limit = 9
    
    # Check cache
    if not force_refresh:
        cached = get_cached_posts(page_url, limit)
        if cached:
            print(f"📦 Using cached posts for {page_url}")
            return jsonify({
                "success": True,
                "posts": cached,
                "credits_used": 0,
                "credits_remaining": "N/A (cached)",
                "total_posts": len(cached),
                "cached": True
            })
    
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
                if publish_time and publish_time != "N/A":
                    try:
                        if 'T' in str(publish_time):
                            dt = datetime.fromisoformat(str(publish_time).replace('Z', '+00:00'))
                            publish_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        pass
                
                # Extract images - filters out profile and comment images
                image_urls = extract_image_urls(post)
                
                formatted_post = {
                    "id": details.get("post_id", "N/A"),
                    "text": values.get("text", "No text"),
                    "time": publish_time,
                    "media_type": values.get("is_media", ""),
                    "reactions": {k: v for k, v in reactions.items() if k != "total_reaction_count" and v > 0},
                    "total_reactions": reactions.get("total_reaction_count", 0),
                    "comments": format_number(details.get("comments_count", "0")),
                    "shares": format_number(details.get("share_count", "0")),
                    "post_link": details.get("post_link", ""),
                    "images": image_urls
                }
                formatted_posts.append(formatted_post)
            
            # Save to cache
            if formatted_posts:
                save_to_cache(page_url, limit, formatted_posts)
                total_images = sum(len(p['images']) for p in formatted_posts)
                print(f"✅ Cached {len(formatted_posts)} posts with {total_images} images")
            
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
    """Download a single image"""
    data = request.json
    image_url = data.get('image_url')
    filename = data.get('filename', 'image')
    
    if not image_url:
        return jsonify({"success": False, "error": "No image URL provided"}), 400
    
    print(f"📥 Downloading single image: {filename}")
    print(f"  🔗 {image_url[:100]}...")
    
    # Download the image
    image_data, content_type = download_image_with_retry(image_url)
    
    if image_data:
        # Get file extension
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
    """Download all images from posts as a ZIP file"""
    data = request.json
    posts = data.get('posts', [])
    page_name = data.get('page_name', 'facebook-posts')
    
    if not posts:
        return jsonify({"success": False, "error": "No posts provided"}), 400
    
    print(f"📥 Downloading images from {len(posts)} posts")
    
    # Create a ZIP file in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        image_count = 0
        failed_count = 0
        
        for post_idx, post in enumerate(posts, 1):
            images = post.get('images', [])
            
            print(f"\n📦 Post {post_idx}: {len(images)} images found")
            for img in images:
                print(f"  🔗 {img[:100]}...")
            
            if not images:
                # Add a text file indicating no images
                zip_file.writestr(
                    f"post_{post_idx}/no_images.txt",
                    f"This post has no images.\nPost text: {post.get('text', 'No text')[:200]}"
                )
                continue
            
            # Create a folder for each post
            folder_name = f"post_{post_idx}"
            
            # Add a text file with post info
            post_info = f"Post {post_idx}\n"
            post_info += f"=" * 50 + "\n"
            post_info += f"Time: {post.get('time', 'N/A')}\n"
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
            
            # Download and add each image
            for img_idx, img_url in enumerate(images, 1):
                try:
                    print(f"  📥 Downloading image {img_idx}/{len(images)}...")
                    
                    # Download the image with retry logic
                    image_data, content_type = download_image_with_retry(img_url)
                    
                    if image_data:
                        # Get file extension
                        ext = get_file_extension(content_type, img_url)
                        filename = f"{folder_name}/image_{img_idx}.{ext}"
                        zip_file.writestr(filename, image_data)
                        image_count += 1
                        print(f"    ✅ Downloaded ({len(image_data)} bytes) as {ext}")
                    else:
                        failed_count += 1
                        print(f"    ❌ Failed to download")
                        # Try to save the URL as a text file instead
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
        
        # Add summary file
        summary = "📊 Download Summary\n"
        summary += "=" * 60 + "\n"
        summary += f"Page: {page_name}\n"
        summary += f"Posts processed: {len(posts)}\n"
        summary += f"Images downloaded: {image_count}\n"
        summary += f"Failed downloads: {failed_count}\n"
        summary += f"Download Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += "=" * 60 + "\n\n"
        
        # List all posts with their images
        summary += "📁 Posts with images:\n"
        for post_idx, post in enumerate(posts, 1):
            images = post.get('images', [])
            summary += f"\nPost {post_idx}: {len(images)} images\n"
            if images:
                for idx, img in enumerate(images, 1):
                    summary += f"  Image {idx}: {img}\n"
        
        zip_file.writestr("summary.txt", summary)
        
        if image_count == 0 and failed_count > 0:
            zip_file.writestr("README.txt", 
                "⚠️ No images were successfully downloaded.\n\n"
                "Possible reasons:\n"
                "1. Facebook requires authentication to view these images\n"
                "2. The image URLs have expired\n"
                "3. Facebook is blocking the download requests\n\n"
                "Try:\n"
                "- Download individual images from the web interface\n"
                "- Use the image URLs directly in your browser\n"
                "- Check the post_info.txt files for the image URLs\n"
            )
    
    # Prepare the ZIP file for download
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
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)